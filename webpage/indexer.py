from __future__ import annotations

import os

import chromadb
from google import genai
from webpage.db import get_db

CHUNK_SIZE = 3
STRIDE = 2
COLLECTION_NAME = "document_chunks"
CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")

_genai_client: genai.Client | None = None
_chroma_client: chromadb.PersistentClient | None = None


def _get_embedder() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _genai_client


def _get_chroma() -> chromadb.Collection:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client.get_or_create_collection(COLLECTION_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    result = _get_embedder().models.embed_content(
        model="models/gemini-embedding-001",
        contents=texts,
    )
    return [e.values for e in result.embeddings]


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
        })
        i += STRIDE
    return chunks


def index_document(document_id: str) -> int:
    db = get_db()

    rows = (
        db.table("sentences")
        .select("id, content, doc_idx")
        .eq("document_id", document_id)
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
            "document_id": document_id,
            "content": c["content"],
            "sentence_start": c["sentence_start"],
            "sentence_end": c["sentence_end"],
            "sentence_ids": c["sentence_ids"],
        }
        for c in chunks
    ]

    inserted = db.table("chunks").insert(chunk_rows).execute()
    inserted_chunks = inserted.data

    chroma_ids: list[str] = []
    chroma_embeds: list[list[float]] = []
    chroma_metas: list[dict] = []

    for chunk_row, chunk_data, emb in zip(inserted_chunks, chunks, embeddings):
        chunk_id = chunk_row["id"]
        chroma_ids.append(f"chunk_{chunk_id}")
        chroma_embeds.append(emb)
        chroma_metas.append({
            "chunk_id": chunk_id,
            "document_id": document_id,
            "sentence_start": chunk_data["sentence_start"],
            "sentence_end": chunk_data["sentence_end"],
            "content": chunk_data["content"],
        })

        db.table("chunks").update({"embedding_id": f"chunk_{chunk_id}"}).eq(
            "id", chunk_id
        ).execute()

    collection = _get_chroma()
    collection.add(
        ids=chroma_ids,
        embeddings=chroma_embeds,
        metadatas=chroma_metas,
    )

    return len(chunks)


def search(query: str, top_k: int = 5) -> list[dict]:
    q_emb = embed_text(query)
    collection = _get_chroma()
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
    )

    evidence_blocks = []
    db = get_db()

    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        chunk_id = meta["chunk_id"]
        document_id = meta["document_id"]
        distance = results["distances"][0][i]

        doc = (
            db.table("documents")
            .select("id, url, title")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
        if not doc.data:
            continue
        doc_row = doc.data[0]

        sentences = (
            db.table("sentences")
            .select("id, content, doc_idx")
            .eq("document_id", document_id)
            .gte("doc_idx", meta["sentence_start"])
            .lte("doc_idx", meta["sentence_end"])
            .order("doc_idx")
            .execute()
        )

        context_sentences = (
            db.table("sentences")
            .select("id, content, doc_idx")
            .eq("document_id", document_id)
            .gte("doc_idx", max(0, meta["sentence_start"] - 2))
            .lte("doc_idx", meta["sentence_end"] + 2)
            .order("doc_idx")
            .execute()
        )

        evidence_blocks.append({
            "chunk_id": chunk_id,
            "source_type": "webpage",
            "document_id": document_id,
            "document_url": doc_row.get("url"),
            "document_title": doc_row.get("title"),
            "content": meta["content"],
            "sentences": sentences.data,
            "context_window": context_sentences.data,
            "score": 1.0 - distance,
        })

    return evidence_blocks
