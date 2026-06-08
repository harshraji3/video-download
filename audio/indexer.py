from __future__ import annotations

import os

from openai import OpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmConfiguration,
    HnswAlgorithmConfiguration,
    HnswParameters,
    VectorSearchProfile,
)
from audio.db import get_db

CHUNK_SIZE = 3
STRIDE = 2
INDEX_NAME = "audio-chunks-v2"

_embed_client: OpenAI | None = None
_search_index_client: SearchIndexClient | None = None


def _get_embed_client() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        base = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "https://<placeholder>").rstrip("/")
        _embed_client = OpenAI(
            api_key=os.environ.get("AZURE_FOUNDRY_API_KEY", "<placeholder>"),
            base_url=f"{base}/openai/v1",
        )
    return _embed_client


def _get_embedding_model() -> str:
    return os.environ.get("AZURE_FOUNDRY_EMBEDDING_MODEL", "text-embedding-3-large")


def _get_search_index_client() -> SearchIndexClient:
    global _search_index_client
    if _search_index_client is None:
        endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "https://<placeholder>.search.windows.net")
        api_key = os.environ.get("AZURE_SEARCH_API_KEY", "<placeholder>")
        _search_index_client = SearchIndexClient(endpoint, AzureKeyCredential(api_key))
    return _search_index_client


def _get_search_client() -> SearchClient:
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "https://<placeholder>.search.windows.net")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY", "<placeholder>")
    return SearchClient(endpoint, INDEX_NAME, AzureKeyCredential(api_key))


def _ensure_index() -> None:
    client = _get_search_index_client()
    try:
        client.get_index(INDEX_NAME)
        return
    except Exception:
        pass

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="audio_file_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True, filterable=False),
        SimpleField(name="sentence_start", type=SearchFieldDataType.Int32),
        SimpleField(name="sentence_end", type=SearchFieldDataType.Int32),
        SimpleField(name="start_time", type=SearchFieldDataType.Double),
        SimpleField(name="end_time", type=SearchFieldDataType.Double),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
                parameters=HnswParameters(
                    m=4,
                    ef_construction=400,
                    ef_search=500,
                    metric="cosine",
                ),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="hnsw-profile",
                algorithm_configuration_name="hnsw-config",
            )
        ],
    )

    index = SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search)
    client.create_index(index)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    resp = _get_embed_client().embeddings.create(input=texts, model=model)
    return [e.embedding for e in resp.data]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def create_chunks(sentences: list[dict]) -> list[dict]:
    chunks = []
    i = 0
    while i < len(sentences):
        window = sentences[i : i + CHUNK_SIZE]
        chunk_text = " ".join(s["content"] for s in window)
        chunks.append({
            "content": chunk_text,
            "sentence_start": i,
            "sentence_end": i + len(window) - 1,
            "sentence_ids": [s["id"] for s in window],
            "start_time": window[0]["start_time"],
            "end_time": window[-1]["end_time"],
        })
        i += STRIDE
    return chunks


def index_audio(audio_file_id: str) -> int:
    db = get_db()

    rows = (
        db.table("transcript_sentences")
        .select("id, content, doc_idx, start_time, end_time")
        .eq("audio_file_id", audio_file_id)
        .order("doc_idx")
        .execute()
    )
    sentences = rows.data
    if not sentences:
        return 0

    chunks = create_chunks(sentences)
    chunk_texts = [c["content"] for c in chunks]
    embeddings = embed_texts(chunk_texts)

    chunk_rows = [
        {
            "audio_file_id": audio_file_id,
            "content": c["content"],
            "sentence_start": c["sentence_start"],
            "sentence_end": c["sentence_end"],
            "sentence_ids": c["sentence_ids"],
            "start_time": c["start_time"],
            "end_time": c["end_time"],
        }
        for c in chunks
    ]

    inserted = db.table("audio_chunks").insert(chunk_rows).execute()
    inserted_chunks = inserted.data

    _ensure_index()
    search_client = _get_search_client()

    docs = []
    for chunk_row, chunk_data, emb in zip(inserted_chunks, chunks, embeddings):
        chunk_id = chunk_row["id"]
        docs.append({
            "id": f"audio_chunk_{chunk_id}",
            "audio_file_id": audio_file_id,
            "content": chunk_data["content"],
            "sentence_start": chunk_data["sentence_start"],
            "sentence_end": chunk_data["sentence_end"],
            "start_time": chunk_data["start_time"],
            "end_time": chunk_data["end_time"],
            "content_vector": emb,
        })

        db.table("audio_chunks").update({"embedding_id": f"audio_chunk_{chunk_id}"}).eq(
            "id", chunk_id
        ).execute()

    search_client.upload_documents(docs)
    return len(chunks)


def search(query: str, top_k: int = 5) -> list[dict]:
    q_emb = embed_text(query)
    _ensure_index()
    search_client = _get_search_client()

    results = search_client.search(
        search_text=query,
        vector_queries=[VectorizedQuery(vector=q_emb, k_nearest_neighbors=top_k, fields="content_vector", kind="vector")],
        select=["id", "audio_file_id", "content", "sentence_start", "sentence_end", "start_time", "end_time"],
        top=top_k,
    )

    evidence_blocks = []
    db = get_db()

    for r in results:
        chunk_id = r["id"]
        audio_file_id = r["audio_file_id"]
        score = r["@search.score"]

        audio = (
            db.table("audio_files")
            .select("id, filename, title, speaker")
            .eq("id", audio_file_id)
            .limit(1)
            .execute()
        )
        if not audio.data:
            continue
        audio_row = audio.data[0]

        sentences = (
            db.table("transcript_sentences")
            .select("id, content, doc_idx, start_time, end_time")
            .eq("audio_file_id", audio_file_id)
            .gte("doc_idx", r["sentence_start"])
            .lte("doc_idx", r["sentence_end"])
            .order("doc_idx")
            .execute()
        )

        context_sentences = (
            db.table("transcript_sentences")
            .select("id, content, doc_idx, start_time, end_time")
            .eq("audio_file_id", audio_file_id)
            .gte("doc_idx", max(0, r["sentence_start"] - 2))
            .lte("doc_idx", r["sentence_end"] + 2)
            .order("doc_idx")
            .execute()
        )

        evidence_blocks.append({
            "chunk_id": chunk_id,
            "source_type": "audio",
            "audio_file_id": audio_file_id,
            "audio_title": audio_row.get("title"),
            "speaker": audio_row.get("speaker"),
            "content": r["content"],
            "sentences": sentences.data,
            "context_window": context_sentences.data,
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "score": score,
        })

    return evidence_blocks
