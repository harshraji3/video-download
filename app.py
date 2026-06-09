import os
import html
import json
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from dotenv import load_dotenv
from audio.models import IngestResponse as AudioIngestResponse
from audio.ingest import ingest_audio
from audio.indexer import search as audio_search
from video.models import IngestResponse as VideoIngestResponse
from video.ingest import ingest_video
from video.indexer import search as video_search
from models import QueryRequest, QueryResponse, Citation, HistoryResponse, HistoryMessage
from generator import generate_answer, generate_answer_stream
from mongo_db import save_message, get_history

load_dotenv()

ACTIVE_SOURCES = {
    s.strip()
    for s in os.environ.get("ACTIVE_SOURCES", "audio,video").split(",")
}

STREAMING_ENABLED = os.environ.get("STREAMING_ENABLED", "false").lower() in ("true", "1", "yes")

app = FastAPI(title="Video Search - Ingestion API")



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
        data = await file.read()
        filename = file.filename or "audio.mp3"

        row = ingest_audio(
            data, filename,
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
        data = await file.read()
        filename = file.filename or "video.mp4"

        row = ingest_video(
            data, filename,
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
        if "audio" in ACTIVE_SOURCES:
            results.extend(audio_search(req.query, top_k=req.top_k))
        if "video" in ACTIVE_SOURCES:
            results.extend(video_search(req.query, top_k=req.top_k))

        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[: req.top_k]

        # Fetch conversation history from MongoDB (last 10 messages)
        history = []
        if req.session_id:
            raw = get_history(req.session_id, limit=10)
            history = [{"role": m["role"], "text": m["text"]} for m in raw]

        gen = generate_answer(req.query, results, history=history)

        # Save to MongoDB
        if req.session_id:
            save_message(req.session_id, "user", req.query)
            save_message(req.session_id, "assistant", gen["answer"], gen.get("citations", []))

        return QueryResponse(
            query=req.query,
            results=results,
            answer=gen["answer"],
            insufficient_evidence=gen.get("insufficient_evidence", False),
            citations=[Citation(**c) for c in gen.get("citations", [])],
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    if not STREAMING_ENABLED:
        raise HTTPException(404, "Streaming is not enabled")

    try:
        results = []
        if "audio" in ACTIVE_SOURCES:
            results.extend(audio_search(req.query, top_k=req.top_k))
        if "video" in ACTIVE_SOURCES:
            results.extend(video_search(req.query, top_k=req.top_k))

        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[: req.top_k]

        history = []
        if req.session_id:
            raw = get_history(req.session_id, limit=10)
            history = [{"role": m["role"], "text": m["text"]} for m in raw]

        async def stream():
            full_answer = ""
            full_citations = []
            insufficient_evidence = False

            if req.session_id:
                save_message(req.session_id, "user", req.query)

            for sse_data in generate_answer_stream(req.query, results, history=history):
                yield sse_data
                prefix = "data: "
                if sse_data.startswith(prefix):
                    try:
                        evt = json.loads(sse_data[len(prefix):].strip())
                        if evt.get("type") == "done":
                            full_answer = evt["answer"]
                            full_citations = evt.get("citations", [])
                            insufficient_evidence = evt.get("insufficient_evidence", False)
                    except json.JSONDecodeError:
                        pass

            if req.session_id and full_answer:
                save_message(req.session_id, "assistant", full_answer, full_citations)

        return StreamingResponse(stream(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/history", response_model=HistoryResponse)
async def get_chat_history(session_id: str):
    try:
        raw = get_history(session_id, limit=50)
        messages = [
            HistoryMessage(
                role=m["role"],
                text=m["text"],
                citations=[Citation(**c) for c in (m.get("citations") or [])] if m["role"] == "assistant" else None,
            )
            for m in raw
        ]
        return HistoryResponse(session_id=session_id, messages=messages)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/play")
async def play_video(url: str, t: float = 0):
    safe_url = html.escape(url).replace(" ", "%20")
    content_type = "video/mp4"
    if ".wav" in url or ".mp3" in url:
        content_type = "audio/mpeg"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Player</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #000; display: flex; justify-content: center; align-items: center; height: 100vh; }}
</style>
</head>
<body>
<video id="v" controls preload="auto" style="max-width:100vw;max-height:100vh">
  <source src="{safe_url}" type="{content_type}">
</video>
<script>
  (function() {{
    var v = document.getElementById("v");
    var target = {t};
    var retries = 0;
    function seek() {{
      if (v.readyState >= 1) {{
        v.currentTime = target;
        v.play();
      }} else if (retries < 50) {{
        retries++;
        setTimeout(seek, 100);
      }}
    }}
    seek();
  }})();
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health():
    return {"status": "ok"}
