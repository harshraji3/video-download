from pydantic import BaseModel, HttpUrl


class IngestRequest(BaseModel):
    url: HttpUrl


class IngestResponse(BaseModel):
    document_id: str
    url: str
    title: str | None = None
