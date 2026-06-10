import json
import csv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import process as p

app = FastAPI(title="Oncology Video Library API")


@app.on_event("startup")
def startup():
    p.setup()


class ProcessRequest(BaseModel):
    url: str


@app.post("/process")
def process_video(req: ProcessRequest, metadata_only: bool = Query(False)):
    meta = p.get_meta(req.url)
    if not meta:
        raise HTTPException(422, detail="Failed to fetch video metadata")

    video_id = str(meta.get("id", ""))
    uploader = meta.get("uploader", meta.get("channel", "Unknown"))
    title = meta.get("title", "Untitled")
    file_id = p.make_file_id(uploader, video_id, title)

    success = p.process(req.url, skip_download=metadata_only)
    if not success:
        raise HTTPException(422, detail="Failed to process video")

    desc_file = p.DESCS / f"{file_id}.json"
    if desc_file.exists():
        return json.loads(desc_file.read_text(encoding="utf-8"))
    return {"file_id": file_id, "status": "processed"}


@app.get("/videos")
def list_videos(q: str = Query("", description="Filter by title or file_id")):
    if not p.DB.exists():
        return []
    results = []
    with open(p.DB, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if q and q.lower() not in row.get("title", "").lower() and q.lower() not in row.get("file_id", "").lower():
                continue
            results.append(row)
    return results


@app.get("/videos/{file_id}")
def get_video(file_id: str):
    desc_file = p.DESCS / f"{file_id}.json"
    if not desc_file.exists():
        raise HTTPException(404, detail="Video not found")
    return json.loads(desc_file.read_text(encoding="utf-8"))
