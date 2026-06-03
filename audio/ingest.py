import os
from nltk.tokenize import sent_tokenize
from audio.db import get_db
from audio.transcribe import transcribe
from audio.indexer import index_audio

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_files")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in sent_tokenize(text) if s.strip()]


def assign_timestamps(sentences: list[str], segments: list[dict]) -> list[dict]:
    seg_texts = [seg["text"].strip() for seg in segments]

    char_to_seg: list[int] = []
    for seg_idx, text in enumerate(seg_texts):
        for _ in text:
            char_to_seg.append(seg_idx)
        if seg_idx < len(seg_texts) - 1:
            char_to_seg.append(seg_idx)

    full_text = " ".join(seg_texts)

    result = []
    cursor = 0
    for sent in sentences:
        start = full_text.find(sent, cursor)
        if start == -1:
            continue
        end = start + len(sent) - 1
        cursor = end + 1

        seg_ids = set(char_to_seg[start : end + 1])
        first_seg = min(seg_ids)
        last_seg = max(seg_ids)

        result.append({
            "content": sent,
            "start_time": segments[first_seg]["start"],
            "end_time": segments[last_seg]["end"],
        })

    return result


def ingest_audio(file_path: str, title: str | None = None, speaker: str | None = None) -> dict:
    db = get_db()

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    audio = (
        db.table("audio_files")
        .insert({
            "filename": filename,
            "file_path": file_path,
            "title": title,
            "speaker": speaker,
            "file_size_bytes": file_size,
        })
        .execute()
    )
    if not audio.data:
        raise RuntimeError("Failed to insert audio file")
    audio_row = audio.data[0]
    audio_id = audio_row["id"]

    result = transcribe(file_path)

    transcript = (
        db.table("transcripts")
        .insert({
            "audio_file_id": audio_id,
            "content": result["content"],
            "segments": result["segments"],
            "model_used": "whisper",
        })
        .execute()
    )
    if not transcript.data:
        raise RuntimeError("Failed to insert transcript")
    transcript_row = transcript.data[0]
    transcript_id = transcript_row["id"]

    duration = result["segments"][-1]["end"] if result["segments"] else 0
    db.table("audio_files").update({"duration_seconds": round(duration, 2)}).eq(
        "id", audio_id
    ).execute()

    sentences = split_sentences(result["content"])
    sent_list = assign_timestamps(sentences, result["segments"])

    sentence_rows = [
        {
            "transcript_id": transcript_id,
            "audio_file_id": audio_id,
            "doc_idx": doc_idx,
            "idx": doc_idx,
            "content": s["content"],
            "start_time": s["start_time"],
            "end_time": s["end_time"],
        }
        for doc_idx, s in enumerate(sent_list)
    ]

    sentence_count = 0
    if sentence_rows:
        db.table("transcript_sentences").insert(sentence_rows).execute()
        sentence_count = len(sentence_rows)

    chunk_count = index_audio(audio_id)

    audio_row["transcript_sentence_count"] = sentence_count
    audio_row["chunk_count"] = chunk_count
    return audio_row
