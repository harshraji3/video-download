from __future__ import annotations

from urllib.parse import quote
from audio.db import get_db
from services import (
    create_chunks,
    embed_texts,
    embed_text,
    ensure_index,
    index_docs,
    search as base_search,
    INDEX_NAME,
)


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

    ensure_index()
    docs = []
    audio_row = db.table("audio_files").select("metadata, title").eq("id", audio_file_id).limit(1).execute()
    file_url = None
    source_title = None
    if audio_row.data:
        meta = audio_row.data[0].get("metadata") or {}
        file_url = meta.get("blob_url") if isinstance(meta, dict) else None
        source_title = audio_row.data[0].get("title")

    for chunk_row, chunk_data, emb in zip(inserted_chunks, chunks, embeddings):
        chunk_id = chunk_row["id"]
        file_url_ts = f"/play?url={quote(file_url)}&t={chunk_data['start_time']}" if file_url and chunk_data.get("start_time") is not None else None
        docs.append({
            "id": f"audio_chunk_{chunk_id}",
            "source_type": "audio",
            "source_id": audio_file_id,
            "source_title": source_title,
            "content": chunk_data["content"],
            "sentence_start": chunk_data["sentence_start"],
            "sentence_end": chunk_data["sentence_end"],
            "start_time": chunk_data["start_time"],
            "end_time": chunk_data["end_time"],
            "has_keyframe_text": False,
            "file_url": file_url,
            "file_url_ts": file_url_ts,
            "content_vector": emb,
        })

        db.table("audio_chunks").update({"embedding_id": f"audio_chunk_{chunk_id}"}).eq(
            "id", chunk_id
        ).execute()

    index_docs(docs)
    return len(chunks)


def search(query: str, top_k: int = 5) -> list[dict]:
    raw = base_search(query, top_k=top_k, source_type="audio")
    if not raw:
        return []

    evidence_blocks = []
    db = get_db()

    for r in raw:
        source_id = r["source_id"]

        audio = (
            db.table("audio_files")
            .select("id, filename, title, speaker")
            .eq("id", source_id)
            .limit(1)
            .execute()
        )
        if not audio.data:
            continue
        audio_row = audio.data[0]

        sentences = (
            db.table("transcript_sentences")
            .select("id, content, doc_idx, start_time, end_time")
            .eq("audio_file_id", source_id)
            .gte("doc_idx", r["sentence_start"])
            .lte("doc_idx", r["sentence_end"])
            .order("doc_idx")
            .execute()
        )

        context_sentences = (
            db.table("transcript_sentences")
            .select("id, content, doc_idx, start_time, end_time")
            .eq("audio_file_id", source_id)
            .gte("doc_idx", max(0, r["sentence_start"] - 2))
            .lte("doc_idx", r["sentence_end"] + 2)
            .order("doc_idx")
            .execute()
        )

        evidence_blocks.append({
            "chunk_id": r["chunk_id"],
            "source_type": "audio",
            "audio_file_id": source_id,
            "audio_title": audio_row.get("title") or r.get("source_title"),
            "speaker": audio_row.get("speaker"),
            "file_url": r.get("file_url"),
            "file_url_ts": r.get("file_url_ts"),
            "content": r["content"],
            "sentences": sentences.data,
            "context_window": context_sentences.data,
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "score": r["score"],
        })

    return evidence_blocks
