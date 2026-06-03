from pydantic import BaseModel


class IngestResponse(BaseModel):
    audio_file_id: str
    filename: str
    title: str | None = None
    speaker: str | None = None
    speaker_names: list[str] = []
    speaker_role: str | None = None
    organization: str | None = None
    short_summary: str | None = None
    language: str | None = None
    speaker_count: int | None = None
    theme: str | None = None
    keywords: list[str] = []
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
