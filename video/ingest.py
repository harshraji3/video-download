import os
from video.db import get_db
from video.content_understanding import transcribe_video
from video.indexer import index_video


def ingest_video(
    file_path: str,
    title: str | None = None,
    speaker: str | None = None,
    speaker_count: int | None = None,
    speaker_names: list[str] | None = None,
    speaker_role: str | None = None,
    organization: str | None = None,
    short_summary: str | None = None,
) -> dict:
    db = get_db()

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    cu_result = transcribe_video(file_path)

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

    video = (
        db.table("video_files")
        .insert({
            "filename": filename,
            "file_path": file_path,
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
            "width": cu_result.get("width"),
            "height": cu_result.get("height"),
            "keyframe_times": cu_result.get("keyframe_times", []),
            "keyframe_text": cu_result.get("keyframe_text"),
            "camera_shot_times": cu_result.get("camera_shot_times", []),
        })
        .execute()
    )
    if not video.data:
        raise RuntimeError("Failed to insert video file")
    video_row = video.data[0]
    video_id = video_row["id"]

    transcript = (
        db.table("video_transcripts")
        .insert({
            "video_file_id": video_id,
            "content": cu_result["content"],
            "segments": cu_result["segments"],
            "model_used": "azure_content_understanding",
        })
        .execute()
    )
    if not transcript.data:
        raise RuntimeError("Failed to insert video transcript")
    transcript_row = transcript.data[0]
    transcript_id = transcript_row["id"]

    duration = cu_result.get("duration", 0)
    db.table("video_files").update({"duration_seconds": round(duration, 2)}).eq(
        "id", video_id
    ).execute()

    sentence_rows = [
        {
            "transcript_id": transcript_id,
            "video_file_id": video_id,
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
        db.table("video_transcript_sentences").insert(sentence_rows).execute()
        sentence_count = len(sentence_rows)

    chunk_count = index_video(video_id)

    video_row["transcript_sentence_count"] = sentence_count
    video_row["chunk_count"] = chunk_count
    return video_row
