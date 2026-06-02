from fastapi import FastAPI, HTTPException
from documents.models import IngestRequest, IngestResponse
from documents.ingest import ingest_web_article

app = FastAPI(title="Video Search - Ingestion API")


@app.post("/ingest/web", response_model=IngestResponse)
async def ingest_web(req: IngestRequest):
    try:
        row = ingest_web_article(str(req.url))
        return IngestResponse(
            document_id=row["id"],
            url=row["url"],
            title=row.get("title"),
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}
