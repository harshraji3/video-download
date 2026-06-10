import azure.functions as func
import json
import os
import tempfile
import shutil
import subprocess

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

from process import (
    extract_all, confidence_score, confidence_label,
    make_file_id, join_list, get_meta, get_transcript,
    FOLDER_MAP, NA
)
from datetime import datetime

# ---------------------------------------------------------------------------
# Azure Function App
# ---------------------------------------------------------------------------

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# ---------------------------------------------------------------------------
# Blob helpers
# ---------------------------------------------------------------------------

def _get_container():
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING not set")
    container_name = os.environ.get("AZURE_STORAGE_CONTAINER", "media-files")
    client = BlobServiceClient.from_connection_string(conn_str)
    container = client.get_container_client(container_name)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    return container


def _read_index(container) -> list:
    try:
        blob = container.get_blob_client("_index/library_database.json")
        return json.loads(blob.download_blob().readall())
    except Exception:
        return []


def _write_index(container, index: list) -> None:
    container.get_blob_client("_index/library_database.json").upload_blob(
        json.dumps(index, indent=2, ensure_ascii=False),
        overwrite=True,
    )


def _update_csv(container, metadata: dict) -> str:
    """Append a row to the master CSV in blob storage."""
    import csv, io
    csv_blob_name = "_index/video_library.csv"
    headers = ["file_id", "title", "url", "description", "category",
               "cancer_indications", "drug_generic_names", "biomarker_context",
               "speakers", "confidence_score", "confidence_label",
               "duration_minutes", "processed_date", "metadata_url"]

    # Read existing CSV if it exists
    existing_rows = []
    try:
        blob = container.get_blob_client(csv_blob_name)
        raw = blob.download_blob().readall().decode("utf-8")
        reader = csv.DictReader(io.StringIO(raw))
        existing_rows = list(reader)
    except Exception:
        pass

    # Remove existing entry for this file_id if reprocessing
    existing_rows = [r for r in existing_rows if r.get("file_id") != metadata["file_id"]]

    # Build new row
    new_row = {
        "file_id":            metadata.get("file_id", ""),
        "title":              metadata.get("title", ""),
        "url":                metadata.get("url", ""),
        "description":        metadata.get("video_summary", ""),
        "category":           metadata.get("content_format", ""),
        "cancer_indications": "|".join(metadata.get("cancer_indications", []) or []),
        "drug_generic_names": "|".join(metadata.get("drug_generic_names", []) or []),
        "biomarker_context":  "|".join(metadata.get("biomarker_context", []) or []),
        "speakers":           "|".join([s.get("name","") for s in (metadata.get("speakers") or [])]),
        "confidence_score":   str(metadata.get("confidence_score", 0)),
        "confidence_label":   metadata.get("confidence_label", ""),
        "duration_minutes":   str(metadata.get("duration_minutes", 0)),
        "processed_date":     metadata.get("processed_date", ""),
        "metadata_url":       metadata.get("metadata_url", ""),
    }
    existing_rows.append(new_row)

    # Write back to blob
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(existing_rows)

    blob = container.get_blob_client(csv_blob_name)
    blob.upload_blob(output.getvalue().encode("utf-8"), overwrite=True)
    return blob.url


def _upload_json(container, data: dict, blob_name: str) -> str:
    blob = container.get_blob_client(blob_name)
    blob.upload_blob(json.dumps(data, indent=2, ensure_ascii=False), overwrite=True)
    return blob.url


def _upload_file(container, local_path: str, blob_name: str) -> str:
    blob = container.get_blob_client(blob_name)
    with open(local_path, "rb") as f:
        blob.upload_blob(f, overwrite=True)
    return blob.url


def _download_video(url: str, file_id: str, tmpdir: str) -> str | None:
    template = os.path.join(tmpdir, f"{file_id}.%(ext)s")
    cmd = [
        "yt-dlp", "-f", "best[height<=720]/best",
        "-o", template, "--no-warnings", "--no-playlist",
        "--merge-output-format", "mp4", url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=True)
    except Exception:
        return None
    for fname in os.listdir(tmpdir):
        if fname.startswith(file_id) and not fname.endswith((".part", ".ytdl")):
            return os.path.join(tmpdir, fname)
    return None


# ---------------------------------------------------------------------------
# Helper: build metadata dict from a URL
# ---------------------------------------------------------------------------

def _build_metadata(url: str) -> dict | None:
    meta = get_meta(url)
    if not meta:
        return None

    video_id    = str(meta.get("id", f"unk_{int(datetime.now().timestamp())}"))
    title       = meta.get("title", "Untitled")
    description = meta.get("description", "") or ""
    uploader    = meta.get("uploader", meta.get("channel", "Unknown"))
    file_id     = make_file_id(uploader, video_id, title)

    transcript = ""
    if "youtube.com" in url or "youtu.be" in url:
        transcript = get_transcript(video_id)

    g           = extract_all(title, description, transcript)
    summary     = g.get("video_summary", NA)
    category    = g.get("content_format", "Uncategorized")
    score       = confidence_score(g)
    label       = confidence_label(score)
    speakers    = g.get("speakers", [])
    now         = datetime.now().isoformat(timespec="seconds")

    return {
        "file_id":            file_id,
        "video_id":           video_id,
        "source_platform":    uploader,
        "publication_date":   meta.get("upload_date", NA),
        "duration_minutes":   round((meta.get("duration") or 0) / 60, 1),
        "video_language":     meta.get("language", NA),
        "video_summary":      summary,
        "cancer_indications": g.get("cancer_indications",  []) or [NA],
        "disease_subtypes":   g.get("disease_subtypes",    []) or [NA],
        "treatment_modality": g.get("treatment_modality",  []) or [NA],
        "drug_brand_names":   g.get("drug_brand_names",    []) or [NA],
        "drug_generic_names": g.get("drug_generic_names",  []) or [NA],
        "drug_classes":       g.get("drug_classes",        []) or [NA],
        "drug_combinations":  g.get("drug_combinations",   []) or [NA],
        "speakers":           speakers or [{"name": NA, "affiliation": NA}],
        "trial_names":        g.get("trial_names",         []) or [NA],
        "nct_numbers":        g.get("nct_numbers",         []) or [NA],
        "trial_phase":        g.get("trial_phase",  NA) or NA,
        "key_endpoints":      g.get("key_endpoints",       []) or [NA],
        "biomarker_context":  g.get("biomarker_context",   []) or [NA],
        "content_format":     category,
        "title":              title,
        "url":                url,
        "extraction_engine":  "rule-based",
        "summary_source":     "template",
        "confidence_score":   score,
        "confidence_label":   label,
        "processed_date":     now,
    }


# ---------------------------------------------------------------------------
# ENDPOINT 1: POST /api/process
# ---------------------------------------------------------------------------

@app.route(route="process", methods=["POST"])
def process_video(req: func.HttpRequest) -> func.HttpResponse:
    """
    Process a video URL — extract metadata, upload to blob.
    Body: { "url": "https://...", "metadata_only": false }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    url = body.get("url", "").strip()
    if not url:
        return func.HttpResponse(
            json.dumps({"error": "url is required"}),
            status_code=400,
            mimetype="application/json"
        )

    metadata_only = body.get("metadata_only", False)

    # Build metadata
    metadata = _build_metadata(url)
    if not metadata:
        return func.HttpResponse(
            json.dumps({"error": "Could not fetch video metadata from URL"}),
            status_code=400,
            mimetype="application/json"
        )

    container  = _get_container()
    file_id    = metadata["file_id"]
    category   = metadata["content_format"]
    sub_path   = FOLDER_MAP.get(category, "_Uncategorized")

    # Upload metadata JSON to blob
    meta_blob_name = f"metadata/{file_id}.json"
    metadata_url   = _upload_json(container, metadata, meta_blob_name)
    metadata["metadata_url"] = metadata_url

    # Download and upload video file (unless metadata_only)
    video_url = None
    if not metadata_only:
        tmpdir = tempfile.mkdtemp()
        try:
            local_path = _download_video(url, file_id, tmpdir)
            if local_path:
                ext = os.path.splitext(local_path)[1]
                vid_blob_name = f"videos/{sub_path}/{file_id}{ext}"
                video_url = _upload_file(container, local_path, vid_blob_name)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    metadata["video_url"] = video_url

    # Update library index in blob
    index = _read_index(container)
    # Remove existing entry if reprocessing same file_id
    index = [v for v in index if v.get("file_id") != file_id]
    index.append({
        "file_id":          file_id,
        "title":            metadata["title"],
        "url":              url,
        "category":         category,
        "confidence_score": metadata["confidence_score"],
        "processed_date":   metadata["processed_date"],
        "metadata_url":     metadata_url,
        "video_url":        video_url,
    })
    _write_index(container, index)

    # Update CSV library
    csv_url = _update_csv(container, metadata)
    metadata["csv_url"] = csv_url

    return func.HttpResponse(
        json.dumps(metadata, ensure_ascii=False),
        status_code=200,
        mimetype="application/json"
    )


# ---------------------------------------------------------------------------
# ENDPOINT 2: GET /api/videos
# ---------------------------------------------------------------------------

@app.route(route="videos", methods=["GET"])
def list_videos(req: func.HttpRequest) -> func.HttpResponse:
    """
    List all processed videos.
    Query params: category (filter), limit (default 50)
    """
    category = req.params.get("category")
    try:
        limit = int(req.params.get("limit", 50))
    except ValueError:
        limit = 50

    try:
        container = _get_container()
        index     = _read_index(container)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

    if category:
        index = [v for v in index if v.get("category") == category]

    return func.HttpResponse(
        json.dumps(index[:limit], ensure_ascii=False),
        status_code=200,
        mimetype="application/json"
    )


# ---------------------------------------------------------------------------
# ENDPOINT 3: GET /api/videos/{file_id}
# ---------------------------------------------------------------------------

@app.route(route="videos/{file_id}", methods=["GET"])
def get_video(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get full metadata for a specific video by file_id.
    """
    file_id = req.route_params.get("file_id", "")
    try:
        container = _get_container()
        blob      = container.get_blob_client(f"metadata/{file_id}.json")
        data      = json.loads(blob.download_blob().readall())
        return func.HttpResponse(
            json.dumps(data, ensure_ascii=False),
            status_code=200,
            mimetype="application/json"
        )
    except Exception:
        # Fall back to index entry
        try:
            index = _read_index(container)
            entry = next((v for v in index if v.get("file_id") == file_id), None)
            if entry:
                return func.HttpResponse(
                    json.dumps(entry, ensure_ascii=False),
                    status_code=200,
                    mimetype="application/json"
                )
        except Exception:
            pass
        return func.HttpResponse(
            json.dumps({"error": f"Video '{file_id}' not found"}),
            status_code=404,
            mimetype="application/json"
        )


# ---------------------------------------------------------------------------
# ENDPOINT 4: GET /api/health
# ---------------------------------------------------------------------------

@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    try:
        container = _get_container()
        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "blob_container": container.container_name,
                "endpoints": [
                    "POST /api/process",
                    "GET  /api/videos",
                    "GET  /api/videos/{file_id}",
                    "GET  /api/health"
                ]
            }),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"status": "error", "detail": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
