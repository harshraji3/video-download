import os
from nltk.tokenize import sent_tokenize
from audio.db import get_db
from audio.transcribe import transcribe
from audio.indexer import index_audio

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_files")


def _split_sentences_with_timestamps(segments: list[dict]) -> list[dict]:
    all_sentences = []
    for seg in segments:
        sentences = sent_tokenize(seg["text"])
        seg_duration = seg["end"] - seg["start"]
        total_chars = len(seg["text"]) or 1
        char_start = 0
        for i, s in enumerate(sentences):
            if not s.strip():
                continue
            char_end = char_start + len(s)
            frac_start = char_start / total_chars
            frac_end = char_end / total_chars
            all_sentences.append({
                "content": s.strip(),
                "idx": i,
                "start_time": round(seg["start"] + frac_start * seg_duration, 2),
                "end_time": round(seg["start"] + frac_end * seg_duration, 2),
            })
            char_start = char_end
    return all_sentences


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

    sent_list = _split_sentences_with_timestamps(result["segments"])

    sentence_rows = [
        {
            "transcript_id": transcript_id,
            "audio_file_id": audio_id,
            "doc_idx": doc_idx,
            "idx": s["idx"],
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
