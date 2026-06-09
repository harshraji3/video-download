from pydantic import BaseModel


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
    file_url: str | None = None
    file_url_ts: str | None = None


class Citation(BaseModel):
    source_number: int
    source_type: str
    source_title: str | None = None
    url: str | None = None
    speaker: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    supporting_text: str
    file_url: str | None = None
    file_url_ts: str | None = None


class QueryResponse(BaseModel):
    query: str
    results: list[EvidenceBlock]
    answer: str | None = None
    insufficient_evidence: bool | None = None
    citations: list[Citation] | None = None
