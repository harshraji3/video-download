from __future__ import annotations

import os
import uuid as uuid_pkg

import chromadb
from google import genai
from audio.db import get_db

CHUNK_SIZE = 3
STRIDE = 2
COLLECTION_NAME = "audio_chunks"
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_files")
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

    chroma_ids: list[str] = []
    chroma_embeds: list[list[float]] = []
    chroma_metas: list[dict] = []

    for chunk_row, chunk_data, emb in zip(inserted_chunks, chunks, embeddings):
        chunk_id = chunk_row["id"]
        chroma_ids.append(f"audio_chunk_{chunk_id}")
        chroma_embeds.append(emb)
        chroma_metas.append({
            "chunk_id": chunk_id,
            "audio_file_id": audio_file_id,
            "sentence_start": chunk_data["sentence_start"],
            "sentence_end": chunk_data["sentence_end"],
            "content": chunk_data["content"],
            "start_time": chunk_data["start_time"],
            "end_time": chunk_data["end_time"],
        })

        db.table("audio_chunks").update({"embedding_id": f"audio_chunk_{chunk_id}"}).eq(
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
        audio_file_id = meta["audio_file_id"]
        distance = results["distances"][0][i]

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
            .gte("doc_idx", meta["sentence_start"])
            .lte("doc_idx", meta["sentence_end"])
            .order("doc_idx")
            .execute()
        )

        context_sentences = (
            db.table("transcript_sentences")
            .select("id, content, doc_idx, start_time, end_time")
            .eq("audio_file_id", audio_file_id)
            .gte("doc_idx", max(0, meta["sentence_start"] - 2))
            .lte("doc_idx", meta["sentence_end"] + 2)
            .order("doc_idx")
            .execute()
        )

        evidence_blocks.append({
            "chunk_id": chunk_id,
            "source_type": "audio",
            "audio_file_id": audio_file_id,
            "audio_title": audio_row.get("title"),
            "speaker": audio_row.get("speaker"),
            "content": meta["content"],
            "sentences": sentences.data,
            "context_window": context_sentences.data,
            "start_time": meta["start_time"],
            "end_time": meta["end_time"],
            "score": 1.0 - distance,
        })

    return evidence_blocks
