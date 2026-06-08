import os
import uuid as uuid_pkg
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from dotenv import load_dotenv
from webpage.models import IngestRequest, IngestResponse, QueryRequest, QueryResponse, Citation
from webpage.ingest import ingest_web_article
from webpage.indexer import index_document, search as vector_search
from audio.models import IngestResponse as AudioIngestResponse
from audio.ingest import ingest_audio
from audio.indexer import search as audio_search
from video.models import IngestResponse as VideoIngestResponse
from video.ingest import ingest_video
from video.indexer import search as video_search
from generator import generate_answer

load_dotenv()

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_files")
VIDEO_DIR = os.path.join(os.path.dirname(__file__), "video_files")
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

ACTIVE_SOURCES = {
    s.strip()
    for s in os.environ.get("ACTIVE_SOURCES", "audio,video").split(",")
}

app = FastAPI(title="Video Search - Ingestion API")


@app.post("/ingest/web", response_model=IngestResponse)
async def ingest_web(req: IngestRequest):
    try:
        row = ingest_web_article(str(req.url))
        return IngestResponse(
            document_id=row["id"],
            url=row["url"],
            title=row.get("title"),
            paragraph_count=row.get("paragraph_count", 0),
            sentence_count=row.get("sentence_count", 0),
            chunk_count=row.get("chunk_count", 0),
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/documents/{document_id}/index")
async def reindex_document(document_id: str):
    try:
        chunk_count = index_document(document_id)
        return {"document_id": document_id, "chunks_indexed": chunk_count}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/ingest/audio", response_model=AudioIngestResponse)
async def ingest_audio_endpoint(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    speaker: str | None = Form(None),
    speaker_count: int | None = Form(None),
    speaker_names: str | None = Form(None),
    speaker_role: str | None = Form(None),
    organization: str | None = Form(None),
    short_summary: str | None = Form(None),
):
    try:
        ext = os.path.splitext(file.filename or "audio.mp3")[1]
        local_name = f"{uuid_pkg.uuid4()}{ext}"
        local_path = os.path.join(AUDIO_DIR, local_name)

        with open(local_path, "wb") as f:
            f.write(await file.read())

        row = ingest_audio(
            local_path,
            title=title,
            speaker=speaker,
            speaker_count=speaker_count,
            speaker_names=[s.strip() for s in speaker_names.split(",")] if speaker_names else None,
            speaker_role=speaker_role,
            organization=organization,
            short_summary=short_summary,
        )
        return AudioIngestResponse(
            audio_file_id=row["id"],
            filename=row["filename"],
            title=row.get("title"),
            speaker=row.get("speaker"),
            speaker_names=row.get("speaker_names", []),
            speaker_role=row.get("speaker_role"),
            organization=row.get("organization"),
            short_summary=row.get("short_summary"),
            language=row.get("language"),
            speaker_count=row.get("speaker_count"),
            theme=row.get("theme"),
            keywords=row.get("keywords", []),
            duration_seconds=row.get("duration_seconds"),
            transcript_sentence_count=row.get("transcript_sentence_count", 0),
            chunk_count=row.get("chunk_count", 0),
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/ingest/video", response_model=VideoIngestResponse)
async def ingest_video_endpoint(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    speaker: str | None = Form(None),
    speaker_count: int | None = Form(None),
    speaker_names: str | None = Form(None),
    speaker_role: str | None = Form(None),
    organization: str | None = Form(None),
    short_summary: str | None = Form(None),
):
    try:
        ext = os.path.splitext(file.filename or "video.mp4")[1]
        local_name = f"{uuid_pkg.uuid4()}{ext}"
        local_path = os.path.join(VIDEO_DIR, local_name)

        with open(local_path, "wb") as f:
            f.write(await file.read())

        row = ingest_video(
            local_path,
            title=title,
            speaker=speaker,
            speaker_count=speaker_count,
            speaker_names=[s.strip() for s in speaker_names.split(",")] if speaker_names else None,
            speaker_role=speaker_role,
            organization=organization,
            short_summary=short_summary,
        )
        return VideoIngestResponse(
            video_file_id=row["id"],
            filename=row["filename"],
            title=row.get("title"),
            speaker=row.get("speaker"),
            speaker_names=row.get("speaker_names", []),
            speaker_role=row.get("speaker_role"),
            organization=row.get("organization"),
            short_summary=row.get("short_summary"),
            language=row.get("language"),
            speaker_count=row.get("speaker_count"),
            theme=row.get("theme"),
            keywords=row.get("keywords", []),
            duration_seconds=row.get("duration_seconds"),
            width=row.get("width"),
            height=row.get("height"),
            has_keyframe_text=bool(row.get("keyframe_text")),
            transcript_sentence_count=row.get("transcript_sentence_count", 0),
            chunk_count=row.get("chunk_count", 0),
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    try:
        results = []
        if "webpage" in ACTIVE_SOURCES:
            results.extend(vector_search(req.query, top_k=req.top_k))
        if "audio" in ACTIVE_SOURCES:
            results.extend(audio_search(req.query, top_k=req.top_k))
        if "video" in ACTIVE_SOURCES:
            results.extend(video_search(req.query, top_k=req.top_k))

        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[: req.top_k]

        gen = generate_answer(req.query, results)

        return QueryResponse(
            query=req.query,
            results=results,
            answer=gen["answer"],
            insufficient_evidence=gen.get("insufficient_evidence", False),
            citations=[Citation(**c) for c in gen.get("citations", [])],
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}
