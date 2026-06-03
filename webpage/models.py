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
    start_time: float | None = None
    end_time: float | None = None


class EvidenceBlock(BaseModel):
    chunk_id: str
    source_type: str
    content: str
    sentences: list[EvidenceSentence]
    context_window: list[EvidenceSentence]
    score: float

    document_id: str | None = None
    document_url: str | None = None
    document_title: str | None = None

    audio_file_id: str | None = None
    audio_title: str | None = None
    speaker: str | None = None
    start_time: float | None = None
    end_time: float | None = None


class QueryResponse(BaseModel):
    query: str
    results: list[EvidenceBlock]
