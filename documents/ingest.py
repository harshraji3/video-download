import httpx
from documents.db import get_db


def ingest_web_article(url: str) -> dict:
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    doc = (
        get_db()
        .table("documents")
        .insert({"url": url, "raw_html": resp.text})
        .execute()
    )

    if not doc.data:
        raise RuntimeError("Failed to insert document")

    return doc.data[0]
