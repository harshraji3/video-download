import os
import re
import subprocess
import tempfile
from collections import Counter
import numpy as np
import soundfile as sf
from scipy.cluster.hierarchy import fcluster, linkage
from google import genai
from nltk.tokenize import sent_tokenize, word_tokenize
from audio.db import get_db
from audio.transcribe import transcribe
from audio.indexer import index_audio

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_files")

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "over", "after",
    "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "shall", "can", "need", "dare", "ought", "used",
    "it", "its", "it's", "i", "you", "he", "she", "we", "they",
    "me", "him", "her", "us", "them", "my", "your", "his", "its",
    "our", "their", "this", "that", "these", "those", "what", "which",
    "who", "whom", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "because", "as", "if", "then", "else", "also",
    "like", "well", "really", "actually", "basically", "literally",
    "here", "there", "get", "got", "go", "going", "went", "come",
    "came", "take", "took", "make", "made", "know", "knows", "think",
    "thinks", "say", "says", "see", "seen", "want", "wants", "let",
    "sure", "right", "way", "thing", "things", "something", "nothing",
    "everything", "one", "two", "first", "last", "next", "new", "old",
    "good", "great", "big", "little", "long", "much", "many",
}


def _estimate_speaker_count(file_path: str) -> int | None:
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-ar", "16000", "-ac", "1",
             "-sample_fmt", "s16", tmp_path],
            capture_output=True, check=True,
        )

        y, sr = sf.read(tmp_path)
        os.unlink(tmp_path)

        import librosa

        if len(y.shape) > 1:
            y = y.mean(axis=1)

        intervals = librosa.effects.split(y, top_db=30)

        features = []
        for start, end in intervals:
            segment = y[start:end]
            if len(segment) < sr:
                continue
            mfcc = librosa.feature.mfcc(y=segment, sr=sr, n_mfcc=13)
            features.append(mfcc.mean(axis=1))

        if len(features) < 3:
            return None

        Z = linkage(features, method="ward")
        clusters = fcluster(Z, t=1.5, criterion="distance")
        return int(clusters.max())
    except Exception:
        return None


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    words = word_tokenize(text)
    words = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    return [w for w, _ in Counter(words).most_common(top_n)]


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


def _extract_llm_metadata(text: str) -> dict:
    try:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        resp = client.models.generate_content(
            model="models/gemma-4-31b-it",
            contents=(
                "Extract metadata from this transcript. Return ONLY valid JSON, no markdown, no code fences, no explanation.\n"
                "{\n"
                '  "theme": "2-3 word theme",\n'
                '  "speaker_names": ["Name1", "Name2"] or [] if none,\n'
                '  "speaker_role": "role if clear from transcript" or null,\n'
                '  "organization": "organization if mentioned" or null,\n'
                '  "short_summary": "1-2 sentence summary"\n'
                "}\n\n"
                f"Transcript: {text[:2500]}"
            ),
        )
        import re, json
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

    raw_result = transcribe(file_path)

    if speaker_count is None:
        speaker_count = _estimate_speaker_count(file_path)

    keywords = _extract_keywords(raw_result["content"])
    llm_meta = _extract_llm_metadata(raw_result["content"])

    theme = llm_meta.get("theme")
    resolved_speaker_names = llm_meta.get("speaker_names") or []
    resolved_speaker_role = llm_meta.get("speaker_role")
    resolved_organization = llm_meta.get("organization")
    resolved_short_summary = llm_meta.get("short_summary")

    if speaker_names is not None:
        resolved_speaker_names = speaker_names
    if speaker_role is not None:
        resolved_speaker_role = speaker_role
    if organization is not None:
        resolved_organization = organization
    if short_summary is not None:
        resolved_short_summary = short_summary

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
            "language": raw_result["language"],
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
            "content": raw_result["content"],
            "segments": raw_result["segments"],
            "model_used": "whisper",
        })
        .execute()
    )
    if not transcript.data:
        raise RuntimeError("Failed to insert transcript")
    transcript_row = transcript.data[0]
    transcript_id = transcript_row["id"]

    duration = raw_result["segments"][-1]["end"] if raw_result["segments"] else 0
    db.table("audio_files").update({"duration_seconds": round(duration, 2)}).eq(
        "id", audio_id
    ).execute()

    sentences = split_sentences(raw_result["content"])
    sent_list = assign_timestamps(sentences, raw_result["segments"])

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
