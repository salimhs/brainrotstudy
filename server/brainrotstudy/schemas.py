"""Public Pydantic schemas for the API and internal pipeline types."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStage(str, Enum):
    EXTRACT = "extract"
    SCRIPT = "script"
    NARRATE = "narrate"
    VISUALS = "visuals"
    RENDER = "render"
    EXPORTS = "exports"


class Pacing(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    CHILL = "chill"


class Vibe(str, Enum):
    STANDARD = "standard"
    UNHINGED = "unhinged"
    ASMR = "asmr"
    GOSSIP = "gossip"
    PROFESSOR = "professor"


class CaptionStyle(str, Enum):
    KARAOKE = "karaoke"   # highlight the active word
    POP = "pop"           # whole phrase pops in
    MINIMAL = "minimal"   # small, understated


class JobOptions(BaseModel):
    length_sec: int = Field(default=60, ge=20, le=180)
    pacing: Pacing = Pacing.BALANCED
    vibe: Vibe = Vibe.STANDARD
    caption_style: CaptionStyle = CaptionStyle.KARAOKE
    export_extras: bool = True
    language: str = "en"


class JobCreate(BaseModel):
    topic: str | None = None
    outline: str | None = None
    options: JobOptions = Field(default_factory=JobOptions)


class Artifacts(BaseModel):
    video_url: str | None = None
    srt_url: str | None = None
    notes_url: str | None = None
    anki_url: str | None = None


class JobView(BaseModel):
    """What the API returns to clients."""

    id: str
    status: JobStatus
    stage: JobStage | None = None
    progress: int = 0
    title: str = ""
    input_kind: Literal["topic", "file"] = "topic"
    input_filename: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    artifacts: Artifacts | None = None
    options: JobOptions


class ProgressEvent(BaseModel):
    """SSE payload."""

    id: str
    status: JobStatus
    stage: JobStage | None = None
    progress: int
    message: str = ""
    at: datetime = Field(default_factory=utc_now)


# ------- Internal pipeline types -------


class ExtractedContent(BaseModel):
    """Normalized content extracted from a PDF/PPTX/topic/notes."""

    title: str
    source: Literal["topic", "pdf", "pptx", "text"]
    sections: list["ExtractedSection"] = Field(default_factory=list)


class ExtractedSection(BaseModel):
    heading: str = ""
    bullets: list[str] = Field(default_factory=list)
    body: str = ""


class ScriptSegment(BaseModel):
    """One spoken line / beat of the video."""

    text: str
    emphasis: list[str] = Field(default_factory=list)
    visual_query: str = Field(
        default="",
        description="Search query for Pexels/Openverse to illustrate this beat.",
    )


class Script(BaseModel):
    title: str
    hook: str
    segments: list[ScriptSegment]
    takeaways: list[str] = Field(default_factory=list)


class NarratedSegment(BaseModel):
    """A ScriptSegment plus its synthesized audio file and timing."""

    text: str
    emphasis: list[str]
    visual_query: str
    audio_path: str
    start_sec: float
    end_sec: float

    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec


class VisualClip(BaseModel):
    """An image file that illustrates a segment, with attribution."""

    path: str
    source: str = ""
    attribution: str = ""


class Timeline(BaseModel):
    width: int
    height: int
    duration_sec: float
    segments: list["TimelineSegment"] = Field(default_factory=list)
    voice_path: str


class TimelineSegment(BaseModel):
    text: str
    emphasis: list[str]
    start_sec: float
    end_sec: float
    image_path: str | None = None
    caption_style: CaptionStyle = CaptionStyle.KARAOKE


ExtractedContent.model_rebuild()
Timeline.model_rebuild()
