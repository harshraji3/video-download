import os
from audio.db import get_db
from audio.content_understanding import transcribe_audio
from audio.indexer import index_audio


def ingest_audio(
    data: bytes,
    filename: str,
    title: str | None = None,
    speaker: str | None = None,
    speaker_count: int | None = None,
    speaker_names: list[str] | None = None,
    speaker_role: str | None = None,
    organization: str | None = None,
    short_summary: str | None = None,
) -> dict:
    db = get_db()

    file_size = len(data)

    cu_result = transcribe_audio(data, filename)

    if speaker_count is None:
        speaker_count = cu_result.get("speaker_count")

    keywords = cu_result.get("keywords", [])
    resolved_short_summary = short_summary or cu_result.get("summary")
    theme = cu_result.get("topics") or None
    resolved_speaker_names = (
        speaker_names
        if speaker_names is not None
        else cu_result.get("speaker_names", [])
    )
    resolved_organization = (
        organization if organization is not None else cu_result.get("company_name")
    )

    if speaker is None and cu_result.get("segments"):
        speaker = cu_result["segments"][0].get("speaker") or None

    if title is None:
        title = os.path.splitext(filename)[0]

    audio = (
        db.table("audio_files")
        .insert({
            "filename": filename,
            "file_path": filename,
            "title": title,
            "speaker": speaker,
            "speaker_names": resolved_speaker_names,
            "speaker_role": speaker_role,
            "organization": resolved_organization,
            "short_summary": resolved_short_summary,
            "speaker_count": speaker_count,
            "language": cu_result["language"],
            "theme": theme,
            "keywords": keywords,
            "drug_names": cu_result.get("drug_names"),
            "cancer_types": cu_result.get("cancer_types"),
            "biomarkers": cu_result.get("biomarkers"),
            "file_size_bytes": file_size,
            "metadata": {"blob_url": cu_result.get("blob_url")},
        })
        .execute()
    )
    if not audio.data:
        raise RuntimeError("Failed to insert audio file")
    audio_row = audio.data[0]
    audio_id = audio_row["id"]

    transcript = (
        db.table("transcripts")
        .insert({
            "audio_file_id": audio_id,
            "content": cu_result["content"],
            "segments": cu_result["segments"],
            "model_used": "azure_content_understanding",
        })
        .execute()
    )
    if not transcript.data:
        raise RuntimeError("Failed to insert transcript")
    transcript_row = transcript.data[0]
    transcript_id = transcript_row["id"]

    duration = cu_result.get("duration", 0)
    db.table("audio_files").update({"duration_seconds": round(duration, 2)}).eq(
        "id", audio_id
    ).execute()

    sentence_rows = [
        {
            "transcript_id": transcript_id,
            "audio_file_id": audio_id,
            "doc_idx": idx,
            "idx": idx,
            "content": s["text"],
            "start_time": s["start"],
            "end_time": s["end"],
        }
        for idx, s in enumerate(cu_result["segments"])
    ]

    sentence_count = 0
    if sentence_rows:
        db.table("transcript_sentences").insert(sentence_rows).execute()
        sentence_count = len(sentence_rows)

    chunk_count = index_audio(audio_id)

    audio_row["transcript_sentence_count"] = sentence_count
    audio_row["chunk_count"] = chunk_count
    return audio_row
