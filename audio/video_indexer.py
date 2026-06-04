import os
import time
import httpx

API_BASE = "https://api.videoindexer.ai"


def _get_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"{key} is not set")
    return val


def _get_access_token() -> str:
    api_key = _get_env("AZURE_VIDEO_INDEXER_API_KEY")
    account_id = _get_env("AZURE_VIDEO_INDEXER_ACCOUNT_ID")
    location = os.environ.get("AZURE_VIDEO_INDEXER_LOCATION", "trial")

    url = f"{API_BASE}/auth/{location}/Accounts/{account_id}/AccessToken?allowEdit=true"
    resp = httpx.get(url, headers={"Ocp-Apim-Subscription-Key": api_key})
    if not resp.is_success:
        raise RuntimeError(
            f"VI auth failed ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.text.strip('"')


def _upload_audio(file_path: str) -> str:
    account_id = _get_env("AZURE_VIDEO_INDEXER_ACCOUNT_ID")
    location = os.environ.get("AZURE_VIDEO_INDEXER_LOCATION", "trial")
    token = _get_access_token()
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as f:
        files = {"file": (filename, f, "audio/mpeg")}
        url = f"{API_BASE}/{location}/Accounts/{account_id}/Videos"
        params = {
            "name": filename,
            "indexingPreset": "AdvancedAudio",
            "privacy": "Private",
        }
        resp = httpx.post(
            url,
            params=params,
            files=files,
            headers={"Authorization": f"Bearer {token}"},
        )
    if not resp.is_success:
        raise RuntimeError(
            f"VI upload failed ({resp.status_code}): {resp.text[:500]}"
        )
    data = resp.json()
    video_id = data.get("id")
    if not video_id:
        raise RuntimeError(f"VI upload returned no video ID: {data}")
    return video_id


def _wait_for_index(video_id: str, max_wait: int = 600, poll_interval: int = 5) -> dict:
    account_id = _get_env("AZURE_VIDEO_INDEXER_ACCOUNT_ID")
    location = os.environ.get("AZURE_VIDEO_INDEXER_LOCATION", "trial")

    start = time.time()
    while True:
        token = _get_access_token()
        url = f"{API_BASE}/{location}/Accounts/{account_id}/Videos/{video_id}/Index"
        resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        data = resp.json()

        state = data.get("state")
        if state == "Processed":
            return data
        if state == "Failed":
            msg = data.get("failureMessage", "unknown")
            raise RuntimeError(f"VI indexing failed: {msg}")

        if time.time() - start > max_wait:
            raise TimeoutError(f"VI indexing did not complete within {max_wait}s")

        time.sleep(poll_interval)


def _parse_timestamp(ts: str) -> float:
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def transcribe_audio(file_path: str) -> dict:
    video_id = _upload_audio(file_path)
    index_data = _wait_for_index(video_id)

    videos = index_data.get("videos", [])
    if not videos:
        raise RuntimeError("No videos in VI index response")

    insights = videos[0].get("insights", {})

    transcript_segments = []
    for entry in insights.get("transcript", []):
        instances = entry.get("instances", [])
        if not instances:
            continue
        inst = instances[0]
        transcript_segments.append({
            "start": _parse_timestamp(inst.get("adjustedStart", inst.get("start", "0"))),
            "end": _parse_timestamp(inst.get("adjustedEnd", inst.get("end", "0"))),
            "text": entry.get("text", "").strip(),
        })

    content = " ".join(s["text"] for s in transcript_segments)
    keywords = [kw["text"] for kw in insights.get("keywords", [])]
    speakers = insights.get("speakers", [])
    language = videos[0].get("sourceLanguage", "en-US")
    duration = index_data.get("durationInSeconds", 0)
    if not duration and transcript_segments:
        duration = transcript_segments[-1]["end"]

    return {
        "content": content,
        "segments": transcript_segments,
        "language": language,
        "speaker_count": len(speakers),
        "keywords": keywords,
        "duration": float(duration),
    }
