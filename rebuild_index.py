#!/usr/bin/env python3
"""
Rebuild Azure AI Search index with new fields (file_url_ts, source_title).
This script:
1. Deletes the existing index
2. Recreates it with the new schema
3. Re-indexes all existing audio and video chunks from the database
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from services import (
    ensure_index,
    index_docs,
    _get_search_index_client,
    INDEX_NAME,
    embed_texts,
)
from audio.db import get_db as get_audio_db
from video.db import get_db as get_video_db
from urllib.parse import quote


def rebuild_index():
    print(f"Rebuilding index: {INDEX_NAME}")

    # Delete existing index
    client = _get_search_index_client()
    try:
        client.delete_index(INDEX_NAME)
        print(f"Deleted existing index: {INDEX_NAME}")
    except Exception as e:
        print(f"Index deletion skipped (may not exist): {e}")

    # Recreate index with new schema
    ensure_index()
    print(f"Created new index: {INDEX_NAME}")

    # Re-index audio chunks
    audio_db = get_audio_db()
    audio_files = audio_db.table("audio_files").select("id, title, metadata").execute()

    audio_count = 0
    for audio_file in audio_files.data:
        audio_id = audio_file["id"]
        meta = audio_file.get("metadata") or {}
        file_url = meta.get("blob_url") if isinstance(meta, dict) else None
        source_title = audio_file.get("title")

        # Get chunks for this audio file
        chunks = (
            audio_db.table("audio_chunks")
            .select("id, content, sentence_start, sentence_end, start_time, end_time")
            .eq("audio_file_id", audio_id)
            .execute()
        )

        if not chunks.data:
            continue

        # Get embeddings for chunk content
        chunk_texts = [c["content"] for c in chunks.data]
        embeddings = embed_texts(chunk_texts)

        docs = []
        for chunk, emb in zip(chunks.data, embeddings):
            chunk_id = chunk["id"]
            file_url_ts = f"/play?url={quote(file_url)}&t={chunk['start_time']}" if file_url and chunk.get("start_time") is not None else None

            docs.append({
                "id": f"audio_chunk_{chunk_id}",
                "source_type": "audio",
                "source_id": audio_id,
                "source_title": source_title,
                "content": chunk["content"],
                "sentence_start": chunk["sentence_start"],
                "sentence_end": chunk["sentence_end"],
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
                "has_keyframe_text": False,
                "file_url": file_url,
                "file_url_ts": file_url_ts,
                "content_vector": emb,
            })

        if docs:
            index_docs(docs)
            audio_count += len(docs)
            print(f"  Indexed {len(docs)} audio chunks for file {audio_id}")

    # Re-index video chunks
    video_db = get_video_db()
    video_files = video_db.table("video_files").select("id, title, metadata").execute()

    video_count = 0
    for video_file in video_files.data:
        video_id = video_file["id"]
        meta = video_file.get("metadata") or {}
        file_url = meta.get("blob_url") if isinstance(meta, dict) else None
        source_title = video_file.get("title")

        # Get chunks for this video file
        chunks = (
            video_db.table("video_chunks")
            .select("id, content, sentence_start, sentence_end, start_time, end_time, has_keyframe_text")
            .eq("video_file_id", video_id)
            .execute()
        )

        if not chunks.data:
            continue

        # Get embeddings for chunk content
        chunk_texts = [c["content"] for c in chunks.data]
        embeddings = embed_texts(chunk_texts)

        docs = []
        for chunk, emb in zip(chunks.data, embeddings):
            chunk_id = chunk["id"]
            file_url_ts = f"/play?url={quote(file_url)}&t={chunk['start_time']}" if file_url and chunk.get("start_time") is not None else None

            docs.append({
                "id": f"video_chunk_{chunk_id}",
                "source_type": "video",
                "source_id": video_id,
                "source_title": source_title,
                "content": chunk["content"],
                "sentence_start": chunk["sentence_start"],
                "sentence_end": chunk["sentence_end"],
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
                "has_keyframe_text": chunk.get("has_keyframe_text", False),
                "file_url": file_url,
                "file_url_ts": file_url_ts,
                "content_vector": emb,
            })

        if docs:
            index_docs(docs)
            video_count += len(docs)
            print(f"  Indexed {len(docs)} video chunks for file {video_id}")

    print(f"\nRebuild complete:")
    print(f"  Audio chunks indexed: {audio_count}")
    print(f"  Video chunks indexed: {video_count}")
    print(f"  Total documents indexed: {audio_count + video_count}")


if __name__ == "__main__":
    rebuild_index()
