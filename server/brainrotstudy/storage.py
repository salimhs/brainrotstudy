"""File-system layout for a single job."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True, slots=True)
class JobPaths:
    job_id: str
    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def extract_path(self) -> Path:
        return self.root / "extracted.json"

    @property
    def script_path(self) -> Path:
        return self.root / "script.json"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def voice_path(self) -> Path:
        return self.audio_dir / "voice.mp3"

    @property
    def timeline_path(self) -> Path:
        return self.root / "timeline.json"

    @property
    def visuals_dir(self) -> Path:
        return self.root / "visuals"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def video_path(self) -> Path:
        return self.output_dir / "video.mp4"

    @property
    def srt_path(self) -> Path:
        return self.output_dir / "captions.srt"

    @property
    def notes_path(self) -> Path:
        return self.output_dir / "notes.md"

    @property
    def anki_path(self) -> Path:
        return self.output_dir / "anki.csv"

    @property
    def log_path(self) -> Path:
        return self.root / "job.log"

    def ensure(self) -> "JobPaths":
        for d in (self.input_dir, self.audio_dir, self.visuals_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def job_paths(job_id: str) -> JobPaths:
    root = get_settings().resolve_storage() / "jobs" / job_id
    return JobPaths(job_id=job_id, root=root)
