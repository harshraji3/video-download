from dotenv import load_dotenv
load_dotenv()

import os, json, tempfile, subprocess, shutil, uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

from process import (
    extract_all, confidence_score, confidence_label,
    make_file_id, join_list, get_meta, get_transcript,
    FOLDER_MAP, NA
)
import csv
import io


# ---------------------------------------------------------------------------
# Blob
# ---------------------------------------------------------------------------

_conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
if not _conn_str:
    raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING environment variable is required")

_container_name = os.environ.get("AZURE_STORAGE_CONTAINER", "media-files")
CONTAINER = BlobServiceClient.from_connection_string(_conn_str).get_container_client(_container_name)
try:
    CONTAINER.create_container()
except ResourceExistsError:
    pass


def _read_index() -> list[dict]:
    try:
        blob = CONTAINER.get_blob_client("_index/library_database.json")
        return json.loads(blob.download_blob().readall())
    except Exception:
        return []


def _write_index(index: list[dict]) -> None:
    CONTAINER.get_blob_client("_index/library_database.json").upload_blob(
        json.dumps(index, indent=2, ensure_ascii=False),
        overwrite=True,
    )


def _upload_json(data: dict, blob_name: str) -> str:
    blob = CONTAINER.get_blob_client(blob_name)
    blob.upload_blob(json.dumps(data, indent=2, ensure_ascii=False), overwrite=True)
    return blob.url


def _upload_file(local_path: str, blob_name: str) -> str:
    blob = CONTAINER.get_blob_client(blob_name)
    with open(local_path, "rb") as f:
        blob.upload_blob(f, overwrite=True)
    return blob.url


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="Oncology Video Processor", version="1.0.0")

# ─── CORS Configuration ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (change to specific domains in production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    url: str
    metadata_only: bool = False


class ProcessResponse(BaseModel):
    file_id: str
    title: str
    category: str
    confidence_score: float
    confidence_label: str
    metadata_url: str
    video_url: str | None = None
    metadata: dict


class VideoListItem(BaseModel):
    file_id: str
    title: str
    url: str
    category: str
    confidence_score: float
    processed_date: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download_video(url: str, file_id: str, tmpdir: str) -> str | None:
    template = os.path.join(tmpdir, f"{file_id}.%(ext)s")
    cmd = [
        "yt-dlp", "-f", "best[height<=720]/best",
        "-o", template, "--no-warnings", "--no-playlist",
        "--merge-output-format", "mp4", url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(502, f"yt-dlp download failed: {e.stderr[:200]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Video download timed out")
    for fname in os.listdir(tmpdir):
        if fname.startswith(file_id) and not fname.endswith((".part", ".ytdl")):
            return os.path.join(tmpdir, fname)
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/process", response_model=ProcessResponse)
def process_video(req: ProcessRequest):
    url = req.url

    meta = get_meta(url)
    if not meta:
        raise HTTPException(400, "Could not fetch video metadata")

    video_id    = str(meta.get("id", f"unk_{int(datetime.now().timestamp())}"))
    title       = meta.get("title", "Untitled")
    description = meta.get("description", "") or ""
    uploader    = meta.get("uploader", meta.get("channel", "Unknown"))
    file_id     = make_file_id(uploader, video_id, title)

    transcript = ""
    if "youtube.com" in url or "youtu.be" in url:
        transcript = get_transcript(video_id)

    g = extract_all(title, description, transcript)

    summary        = g.get("video_summary", NA)
    category       = g.get("content_format", "Uncategorized")
    score          = confidence_score(g)
    label          = confidence_label(score)
    speakers       = g.get("speakers", [])
    spkr_names     = join_list([s.get("name", "") for s in speakers if s.get("name")])
    spkr_affs      = join_list([s.get("affiliation", "") for s in speakers if s.get("affiliation")])

    sub_path = FOLDER_MAP.get(category, "_Uncategorized")
    now      = datetime.now().isoformat(timespec="seconds")

    metadata = {
        "file_id":             file_id,
        "video_id":            video_id,
        "source_platform":     uploader,
        "publication_date":    meta.get("upload_date", NA),
        "duration_minutes":    round((meta.get("duration") or 0) / 60, 1),
        "video_language":      meta.get("language", NA),
        "video_summary":       summary,
        "cancer_indications":  g.get("cancer_indications",  []) or [NA],
        "disease_subtypes":    g.get("disease_subtypes",    []) or [NA],
        "treatment_modality":  g.get("treatment_modality",  []) or [NA],
        "drug_brand_names":    g.get("drug_brand_names",    []) or [NA],
        "drug_generic_names":  g.get("drug_generic_names",  []) or [NA],
        "drug_classes":        g.get("drug_classes",        []) or [NA],
        "drug_combinations":   g.get("drug_combinations",   []) or [NA],
        "speakers":            speakers or [{"name": NA, "affiliation": NA}],
        "trial_names":         g.get("trial_names",         []) or [NA],
        "nct_numbers":         g.get("nct_numbers",         []) or [NA],
        "trial_phase":         g.get("trial_phase",  NA) or NA,
        "key_endpoints":       g.get("key_endpoints",       []) or [NA],
        "biomarker_context":   g.get("biomarker_context",   []) or [NA],
        "content_format":      category,
        "title":               title,
        "url":                 url,
        "extraction_engine":   "rule-based",
        "summary_source":      "template",
        "confidence_score":    score,
        "processed_date":      now,
    }

    metablob_name = f"metadata/{file_id}.json"
    metadata_url  = _upload_json(metadata, metablob_name)

    video_url = None
    if not req.metadata_only:
        tmpdir = tempfile.mkdtemp()
        try:
            local_path = _download_video(url, file_id, tmpdir)
            if local_path:
                ext = os.path.splitext(local_path)[1]
                vidblob_name = f"videos/{sub_path}/{file_id}{ext}"
                video_url = _upload_file(local_path, vidblob_name)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    index = _read_index()
    index.append({
        "file_id":           file_id,
        "title":             title,
        "url":               url,
        "category":          category,
        "confidence_score":  score,
        "processed_date":    now,
        "metadata_url":      metadata_url,
        "video_url":         video_url,
    })
    _write_index(index)

    return ProcessResponse(
        file_id=file_id,
        title=title,
        category=category,
        confidence_score=score,
        confidence_label=label,
        metadata_url=metadata_url,
        video_url=video_url,
        metadata=metadata,
    )


@app.get("/videos", response_model=list[VideoListItem])
def list_videos(
    category: str | None = Query(None, description="Filter by content category"),
    limit: int = Query(50, ge=1, le=500),
):
    index = _read_index()
    if category:
        index = [v for v in index if v.get("category") == category]
    return index[:limit]


@app.get("/videos/{file_id}")
def get_video(file_id: str):
    index = _read_index()
    entry = next((v for v in index if v["file_id"] == file_id), None)
    if not entry:
        raise HTTPException(404, "Video not found")
    blob = CONTAINER.get_blob_client(entry["metadata_url"].split("/")[-1])
    try:
        data = json.loads(blob.download_blob().readall())
    except Exception:
        data = entry
    return JSONResponse(content=data)


@app.get("/health")
def health():
    return {"status": "ok", "blob": CONTAINER.container_name}


@app.post("/update-csv")
def update_csv_endpoint(metadata: dict):
    """Update the master CSV index in blob storage with new video metadata."""
    csv_blob_name = "_index/video_library.csv"
    headers = [
        "file_id", "title", "url", "description", "category",
        "cancer_indications", "drug_generic_names", "biomarker_context",
        "speakers", "confidence_score", "confidence_label",
        "duration_minutes", "processed_date", "metadata_url"
    ]

    # Read existing CSV if it exists
    existing_rows = []
    try:
        blob = CONTAINER.get_blob_client(csv_blob_name)
        raw = blob.download_blob().readall().decode("utf-8")
        reader = csv.DictReader(io.StringIO(raw))
        # Only keep the fields we care about
        existing_rows = [{k: row.get(k, "") for k in headers} for row in reader]
    except Exception as e:
        print(f"Error reading CSV: {e}")
        pass

    # Remove existing entry for this file_id if reprocessing
    existing_rows = [r for r in existing_rows if r.get("file_id") != metadata.get("file_id")]

    # Build new row - ONLY include fields in headers
    new_row = {
        "file_id":            metadata.get("file_id", ""),
        "title":              metadata.get("title", ""),
        "url":                metadata.get("url", ""),
        "description":        metadata.get("video_summary", ""),
        "category":           metadata.get("content_format", ""),
        "cancer_indications": "|".join([str(x) for x in (metadata.get("cancer_indications", []) or []) if x]),
        "drug_generic_names": "|".join([str(x) for x in (metadata.get("drug_generic_names", []) or []) if x]),
        "biomarker_context":  "|".join([str(x) for x in (metadata.get("biomarker_context", []) or []) if x]),
        "speakers":           "|".join([s.get("name", "") for s in (metadata.get("speakers") or []) if s.get("name")]),
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
    
    blob = CONTAINER.get_blob_client(csv_blob_name)
    blob.upload_blob(output.getvalue(), overwrite=True)
    
    return {"status": "success", "file_id": metadata.get("file_id")}
