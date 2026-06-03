from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from webpage.models import IngestRequest, IngestResponse, QueryRequest, QueryResponse
from webpage.ingest import ingest_web_article
from webpage.indexer import index_document, search as vector_search

load_dotenv()

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


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    try:
        results = vector_search(req.query, top_k=req.top_k)
        return QueryResponse(query=req.query, results=results)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}
