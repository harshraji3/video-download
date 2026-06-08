from pydantic import BaseModel


class IngestResponse(BaseModel):
    video_file_id: str
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
    width: int | None = None
    height: int | None = None
    has_keyframe_text: bool = False
    transcript_sentence_count: int = 0
    chunk_count: int = 0


class VideoEvidenceSentence(BaseModel):
    id: str
    content: str
    doc_idx: int
    start_time: float
    end_time: float
    keyframe_text: str | None = None


class VideoEvidenceBlock(BaseModel):
    chunk_id: str
    video_file_id: str
    video_title: str | None
    speaker: str | None
    content: str
    sentences: list[VideoEvidenceSentence]
    context_window: list[VideoEvidenceSentence]
    start_time: float
    end_time: float
    has_keyframe_text: bool = False
    keyframe_text: str | None = None
    score: float
