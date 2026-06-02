from pydantic import BaseModel, HttpUrl


class IngestRequest(BaseModel):
    url: HttpUrl


class IngestResponse(BaseModel):
    document_id: str
    url: str
    title: str | None = None
    paragraph_count: int = 0
    sentence_count: int = 0
