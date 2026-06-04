import os
import json
import re
from google import genai
from nltk.tokenize import sent_tokenize
from audio.db import get_db
from audio.video_indexer import transcribe_audio
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


_METADATA_FIELDS = {
    "theme": "2-3 word theme",
    "speaker_names": '["Name1", "Name2"] or [] if none',
    "speaker_role": "role if clear from transcript or null",
    "organization": "organization if mentioned or null",
    "short_summary": "1-2 sentence summary",
}


def _extract_llm_metadata(text: str, fields: list[str]) -> dict:
    schema_lines = []
    for f in fields:
        hint = _METADATA_FIELDS[f]
        schema_lines.append(f'  "{f}": {hint},')
    schema = "\n".join(schema_lines)

    try:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        resp = client.models.generate_content(
            model="models/gemma-4-31b-it",
            contents=(
                "Extract the following fields from this transcript. "
                "Return ONLY valid JSON, no markdown, no code fences, no explanation.\n"
                "{\n"
                f"{schema}\n"
                "}\n\n"
                f"Transcript: {text[:2500]}"
            ),
        )
        raw = resp.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[_extract_llm_metadata] Error: {e}")
        return {}


def ingest_audio(
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

    vi_result = transcribe_audio(file_path)

    if speaker_count is None:
        speaker_count = vi_result.get("speaker_count")

    keywords = vi_result.get("keywords", [])

    known = {
        "speaker_names": speaker_names,
        "speaker_role": speaker_role,
        "organization": organization,
        "short_summary": short_summary,
    }
    missing = [f for f, v in known.items() if v is None]
    missing.append("theme")

    llm_meta = _extract_llm_metadata(vi_result["content"], missing)

    theme = llm_meta.get("theme")
    resolved_speaker_names = speaker_names if speaker_names is not None else (llm_meta.get("speaker_names") or [])
    resolved_speaker_role = speaker_role if speaker_role is not None else llm_meta.get("speaker_role")
    resolved_organization = organization if organization is not None else llm_meta.get("organization")
    resolved_short_summary = short_summary if short_summary is not None else llm_meta.get("short_summary")

    audio = (
        db.table("audio_files")
        .insert({
            "filename": filename,
            "file_path": file_path,
            "title": title,
            "speaker": speaker,
            "speaker_names": resolved_speaker_names,
            "speaker_role": resolved_speaker_role,
            "organization": resolved_organization,
            "short_summary": resolved_short_summary,
            "speaker_count": speaker_count,
            "language": vi_result["language"],
            "theme": theme,
            "keywords": keywords,
            "file_size_bytes": file_size,
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
            "content": vi_result["content"],
            "segments": vi_result["segments"],
            "model_used": "azure_video_indexer",
        })
        .execute()
    )
    if not transcript.data:
        raise RuntimeError("Failed to insert transcript")
    transcript_row = transcript.data[0]
    transcript_id = transcript_row["id"]

    duration = vi_result.get("duration", 0)
    db.table("audio_files").update({"duration_seconds": round(duration, 2)}).eq(
        "id", audio_id
    ).execute()

    sentences = split_sentences(vi_result["content"])
    sent_list = assign_timestamps(sentences, vi_result["segments"])

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
