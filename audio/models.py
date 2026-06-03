from pydantic import BaseModel


class IngestResponse(BaseModel):
    audio_file_id: str
    filename: str
    title: str | None = None
    speaker: str | None = None
    duration_seconds: float | None = None
    transcript_sentence_count: int = 0
    chunk_count: int = 0


class AudioEvidenceSentence(BaseModel):
    id: str
    content: str
    doc_idx: int
    start_time: float
    end_time: float


class AudioEvidenceBlock(BaseModel):
    chunk_id: str
    audio_file_id: str
    audio_title: str | None
    speaker: str | None
    content: str
    sentences: list[AudioEvidenceSentence]
    context_window: list[AudioEvidenceSentence]
    start_time: float
    end_time: float
    score: float
