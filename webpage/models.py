from pydantic import BaseModel, HttpUrl


class IngestRequest(BaseModel):
    url: HttpUrl


class IngestResponse(BaseModel):
    document_id: str
    url: str
    title: str | None = None
    paragraph_count: int = 0
    sentence_count: int = 0
    chunk_count: int = 0


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class EvidenceSentence(BaseModel):
    id: str
    content: str
    doc_idx: int


class EvidenceBlock(BaseModel):
    chunk_id: str
    document_id: str
    document_url: str | None
    document_title: str | None
    content: str
    sentences: list[EvidenceSentence]
    context_window: list[EvidenceSentence]
    score: float


class QueryResponse(BaseModel):
    query: str
    results: list[EvidenceBlock]
