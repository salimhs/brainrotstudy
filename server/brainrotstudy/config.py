"""Application configuration loaded from environment or .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values can come from env vars or a .env file."""

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    storage_root: Path = Field(
        default=Path("storage"),
        description="Where job artifacts live. Relative paths are resolved from CWD.",
    )
    db_path: Path = Field(
        default=Path("storage/brainrotstudy.db"),
        description="SQLite database file for job metadata.",
    )

    # LLM providers
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    gemini_model: str = "gemini-2.5-flash"
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o-mini"

    llm_provider: Literal["auto", "gemini", "anthropic", "openai"] = "auto"

    # TTS
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel, default ElevenLabs voice
    tts_provider: Literal["auto", "elevenlabs", "gtts"] = "auto"

    # Stock imagery
    pexels_api_key: str | None = None

    # Rendering
    ffmpeg_binary: str = "ffmpeg"
    ffmpeg_preset: str = "veryfast"
    ffmpeg_crf: int = 22
    video_width: int = 1080
    video_height: int = 1920

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Limits
    max_upload_mb: int = 100
    max_concurrent_jobs: int = 2

    def resolve_storage(self) -> Path:
        """Return an absolute, existing storage root."""
        root = self.storage_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def resolve_db(self) -> Path:
        """Return an absolute path to the SQLite database, ensuring its dir exists."""
        db = self.db_path.expanduser().resolve()
        db.parent.mkdir(parents=True, exist_ok=True)
        return db


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
