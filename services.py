from __future__ import annotations

import os
import time

import httpx
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
    HnswAlgorithmConfiguration,
    HnswParameters,
    VectorSearchProfile,
)
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from datetime import datetime, timedelta, timezone

CHUNK_SIZE = 3
STRIDE = 2
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "media-chunks")

_HTTP = httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0))
_embed_client: OpenAI | None = None
_search_index_client: SearchIndexClient | None = None


def _get_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"{key} is not set")
    return val


# --- Blob Storage ---

def upload_bytes_to_blob(data: bytes, blob_name: str) -> tuple[str, str, str, str]:
    conn_str = _get_env("AZURE_STORAGE_CONNECTION_STRING")
    container = _get_env("AZURE_STORAGE_CONTAINER")

    client = BlobServiceClient.from_connection_string(conn_str)
    container_client = client.get_container_client(container)

    try:
        container_client.create_container()
    except Exception:
        pass

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_disposition="inline"))

    parts = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
    sas_token = generate_blob_sas(
        account_name=parts["AccountName"],
        container_name=container,
        blob_name=blob_name,
        account_key=parts["AccountKey"],
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    permanent_url = blob_client.url
    return f"{permanent_url}?{sas_token}", permanent_url, container, blob_name, conn_str


def set_blob_metadata(conn_str: str, container: str, blob_name: str, data: dict, meta_keys: list[str]) -> None:
    client = BlobServiceClient.from_connection_string(conn_str)
    blob_client = client.get_container_client(container).get_blob_client(blob_name)
    meta = {}
    for k in meta_keys:
        v = data.get(k)
        if v:
            meta[k] = str(v)
    if meta:
        blob_client.set_blob_metadata(metadata=meta)


# --- Content Understanding ---

def start_analysis(url: str, analyzer_id: str) -> tuple[str, str]:
    endpoint = _get_env("AZURE_CONTENT_UNDERSTANDING_ENDPOINT").rstrip("/")
    api_key = _get_env("AZURE_CONTENT_UNDERSTANDING_API_KEY")

    full_url = f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze?api-version=2025-11-01"
    body = {"inputs": [{"url": url}]}

    resp = _HTTP.post(
        full_url,
        json=body,
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/json",
        },
    )
    if not resp.is_success:
        raise RuntimeError(
            f"CU analysis start failed ({resp.status_code}) for analyzer {analyzer_id}: {resp.text[:500]}"
        )

    op = resp.json()
    op_id = op.get("id")
    if not op_id:
        raise RuntimeError(f"CU analysis returned no operation ID: {op}")

    op_url = resp.headers.get("Operation-Location")
    if not op_url:
        raise RuntimeError("CU analysis response missing Operation-Location header")
    return op_id, op_url


def _get_operation(op_url: str, api_key: str) -> dict:
    resp = _HTTP.get(op_url, headers={"Ocp-Apim-Subscription-Key": api_key})
    resp.raise_for_status()
    return resp.json()


def wait_for_analysis(op_url: str, max_wait: int = 600, poll_interval: int = 3) -> dict:
    api_key = _get_env("AZURE_CONTENT_UNDERSTANDING_API_KEY")
    start = time.time()
    while True:
        data = _get_operation(op_url, api_key)
        status = data.get("status")

        if status == "Succeeded":
            return data.get("result", {})
        if status == "Failed":
            err = data.get("error", {})
            msg = err.get("message", "unknown")
            details = err.get("details", [])
            raise RuntimeError(
                f"CU analysis failed: {msg} | details: {details} | full: {data}"
            )
        if time.time() - start > max_wait:
            raise TimeoutError(f"CU analysis did not complete within {max_wait}s")
        time.sleep(poll_interval)


def parse_csv(val: str | None) -> list[str]:
    if not val:
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


# --- Embeddings ---

def _get_embed_client() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        base = _get_env("AZURE_FOUNDRY_ENDPOINT").rstrip("/")
        _embed_client = OpenAI(
            api_key=_get_env("AZURE_FOUNDRY_API_KEY"),
            base_url=f"{base}/openai/v1",
        )
    return _embed_client


def _get_embedding_model() -> str:
    return os.environ.get("AZURE_FOUNDRY_EMBEDDING_MODEL", "text-embedding-3-large")


def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = _get_embed_client().embeddings.create(input=texts, model=_get_embedding_model())
    return [e.embedding for e in resp.data]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


# --- Chunking ---

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


# --- AI Search ---

def _get_search_index_client() -> SearchIndexClient:
    global _search_index_client
    if _search_index_client is None:
        _search_index_client = SearchIndexClient(
            _get_env("AZURE_SEARCH_ENDPOINT"),
            AzureKeyCredential(_get_env("AZURE_SEARCH_API_KEY")),
        )
    return _search_index_client


def _get_search_client() -> SearchClient:
    return SearchClient(
        _get_env("AZURE_SEARCH_ENDPOINT"),
        INDEX_NAME,
        AzureKeyCredential(_get_env("AZURE_SEARCH_API_KEY")),
    )


def ensure_index() -> None:
    client = _get_search_index_client()
    try:
        client.get_index(INDEX_NAME)
        return
    except Exception:
        pass

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="source_type", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="source_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SimpleField(name="sentence_start", type=SearchFieldDataType.Int32),
        SimpleField(name="sentence_end", type=SearchFieldDataType.Int32),
        SimpleField(name="start_time", type=SearchFieldDataType.Double),
        SimpleField(name="end_time", type=SearchFieldDataType.Double),
        SimpleField(name="has_keyframe_text", type=SearchFieldDataType.Boolean),
        SimpleField(name="file_url", type=SearchFieldDataType.String),
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
                parameters=HnswParameters(m=4, ef_construction=400, ef_search=500, metric="cosine"),
            )
        ],
        profiles=[
            VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")
        ],
    )

    client.create_index(SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search))


def index_docs(docs: list[dict]) -> None:
    ensure_index()
    _get_search_client().upload_documents(docs)


def search(query: str, top_k: int = 5, source_type: str | None = None) -> list[dict]:
    q_emb = embed_text(query)
    ensure_index()
    client = _get_search_client()

    filter_expr = f"source_type eq '{source_type}'" if source_type else None

    results = client.search(
        search_text=query,
        vector_queries=[VectorizedQuery(vector=q_emb, k_nearest_neighbors=top_k, fields="content_vector")],
        select=[
            "id", "source_type", "source_id", "content",
            "sentence_start", "sentence_end", "start_time", "end_time",
            "has_keyframe_text", "file_url",
        ],
        filter=filter_expr,
        top=top_k,
    )

    blocks = []
    for r in results:
        blocks.append({
            "chunk_id": r["id"],
            "source_type": r.get("source_type", "unknown"),
            "source_id": r.get("source_id"),
            "content": r["content"],
            "sentence_start": r.get("sentence_start"),
            "sentence_end": r.get("sentence_end"),
            "start_time": r.get("start_time"),
            "end_time": r.get("end_time"),
            "has_keyframe_text": r.get("has_keyframe_text", False),
            "file_url": r.get("file_url"),
            "score": r["@search.score"],
        })

    return blocks
