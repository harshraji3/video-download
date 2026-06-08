import os
import time
import uuid
import httpx
from datetime import datetime, timedelta, timezone
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions


def _get_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"{key} is not set")
    return val


def _upload_to_blob(file_path: str) -> tuple[str, str, str]:
    conn_str = _get_env("AZURE_STORAGE_CONNECTION_STRING")
    container = _get_env("AZURE_STORAGE_CONTAINER")
    blob_name = os.path.basename(file_path)

    client = BlobServiceClient.from_connection_string(conn_str)
    container_client = client.get_container_client(container)
    blob_client = container_client.get_blob_client(blob_name)

    with open(file_path, "rb") as f:
        blob_client.upload_blob(f,overwrite=True)

    parts = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
    sas_token = generate_blob_sas(
        account_name=parts["AccountName"],
        container_name=container,
        blob_name=blob_name,
        account_key=parts["AccountKey"],
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    return f"{blob_client.url}?{sas_token}", container, blob_name, conn_str


_HTTP = httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0))


def _start_analysis(audio_url: str) -> str:
    endpoint = _get_env("AZURE_CONTENT_UNDERSTANDING_ENDPOINT").rstrip("/")
    api_key = _get_env("AZURE_CONTENT_UNDERSTANDING_API_KEY")
    analyzer_id = _get_env("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID_AUDIO")

    url = f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze?api-version=2025-11-01"
    body = {
        "inputs": [
            {
                "url": audio_url,
            }
        ]
    }

    resp = _HTTP.post(
        url,
        json=body,
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/json",
        },
    )
    if not resp.is_success:
        raise RuntimeError(
            f"CU analysis start failed ({resp.status_code}): {resp.text[:500]}"
        )

    op = resp.json()
    op_id = op.get("id")
    if not op_id:
        raise RuntimeError(f"CU analysis returned no operation ID: {op}")

    op_url = resp.headers.get("Operation-Location")
    if not op_url:
        raise RuntimeError("CU analysis response missing Operation-Location header")
    return op_id, op_url


def _get_operation(op_url: str, api_key: str) -> dict:
    resp = _HTTP.get(op_url, headers={"Ocp-Apim-Subscription-Key": api_key})
    resp.raise_for_status()
    return resp.json()


def _wait_for_analysis(
    op_url: str, max_wait: int = 600, poll_interval: int = 3
) -> dict:
    api_key = _get_env("AZURE_CONTENT_UNDERSTANDING_API_KEY")
    start = time.time()
    while True:
        data = _get_operation(op_url, api_key)
        status = data.get("status")

        if status == "Succeeded":
            return data.get("result", {})
        if status == "Failed":
            error = data.get("error", {}).get("message", "unknown")
            raise RuntimeError(f"CU analysis failed: {error}")

        if time.time() - start > max_wait:
            raise TimeoutError(f"CU analysis did not complete within {max_wait}s")

        time.sleep(poll_interval)


def _parse_csv(val: str | None) -> list[str]:
    if not val:
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


def _parse_result(result: dict) -> dict:
    contents = result.get("contents", [])
    if not contents:
        raise RuntimeError("CU analysis returned no contents")

    content = contents[0]
    phrases = content.get("transcriptPhrases", [])
    fields = content.get("fields", {})

    segments = [
        {
            "start": round(p["startTimeMs"] / 1000.0, 2),
            "end": round(p["endTimeMs"] / 1000.0, 2),
            "text": p["text"].strip(),
            "speaker": p.get("speaker", ""),
            "confidence": round(p.get("confidence", 0), 4),
        }
        for p in phrases
    ]

    full_text = " ".join(s["text"] for s in segments)
    language = phrases[0].get("locale", "en-US") if phrases else "en-US"

    duration = content.get("endTimeMs", 0) / 1000.0

    def _f(key: str) -> str:
        v = fields.get(key, {})
        return v.get("valueString", "") if isinstance(v, dict) else ""

    return {
        "content": full_text,
        "segments": segments,
        "language": language,
        "speaker_count": int(_f("speaker_count")) if _f("speaker_count") else 0,
        "speaker_names": _parse_csv(_f("speaker_names")),
        "keywords": _parse_csv(_f("keywords")),
        "duration": duration,
        "summary": _f("summary"),
        "topics": _f("topics"),
        "drug_names": _parse_csv(_f("drug_name")),
        "cancer_types": _parse_csv(_f("cancer")),
        "biomarkers": _parse_csv(_f("biomaker_name")),
        "company_name": _f("company_name") or None,
    }


def _set_blob_metadata(
    conn_str: str, container: str, blob_name: str, data: dict
) -> None:
    client = BlobServiceClient.from_connection_string(conn_str)
    blob_client = client.get_container_client(container).get_blob_client(blob_name)

    meta = {}
    for k in (
        "summary", "topics", "keywords", "speaker_count", "speaker_names",
        "drug_names", "cancer_types", "biomarkers", "company_name",
    ):
        v = data.get(k)
        if v:
            meta[k] = str(v)

    blob_client.set_blob_metadata(metadata=meta)


def transcribe_audio(file_path: str) -> dict:
    audio_url, container, blob_name, conn_str = _upload_to_blob(file_path)
    _, op_url = _start_analysis(audio_url)
    result = _wait_for_analysis(op_url)
    parsed = _parse_result(result)
    _set_blob_metadata(conn_str, container, blob_name, parsed)
    return parsed
