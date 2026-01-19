"""Shared utility functions for the BrainRotStudy pipeline."""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.models import JobMetadata, JobStatus, JobStage, SSEEvent, utc_now


# Storage root directory
STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/app/storage")

# In-memory cache for job metadata to reduce file I/O
# Format: {job_id: (metadata, timestamp)}
_metadata_cache: dict[str, tuple[JobMetadata, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 2.0  # Cache entries expire after 2 seconds


def get_job_dir(job_id: str) -> Path:
    """Get the directory path for a job."""
    return Path(STORAGE_ROOT) / "jobs" / job_id


def get_job_subdirs(job_id: str) -> dict[str, Path]:
    """Get all subdirectory paths for a job."""
    base = get_job_dir(job_id)
    return {
        "input": base / "input",
        "extracted": base / "extracted",
        "llm": base / "llm",
        "assets": base / "assets",
        "audio": base / "audio",
        "captions": base / "captions",
        "render": base / "render",
        "output": base / "output",
        "logs": base / "logs",
    }


def ensure_job_dirs(job_id: str) -> dict[str, Path]:
    """Create all job directories if they don't exist."""
    dirs = get_job_subdirs(job_id)
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def load_job_metadata(job_id: str, use_cache: bool = True) -> Optional[JobMetadata]:
    """Load job metadata from disk with optional caching."""
    # Check cache first (thread-safe)
    if use_cache:
        with _cache_lock:
            if job_id in _metadata_cache:
                cached_meta, cached_time = _metadata_cache[job_id]
                if time.time() - cached_time < _CACHE_TTL_SECONDS:
                    return cached_meta

    meta_path = get_job_dir(job_id) / "metadata.json"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r") as f:
            data = json.load(f)
        metadata = JobMetadata.model_validate(data)

        # Update cache (thread-safe)
        if use_cache:
            with _cache_lock:
                _metadata_cache[job_id] = (metadata, time.time())

        return metadata
    except Exception:
        return None


def save_job_metadata(metadata: JobMetadata) -> None:
    """Save job metadata to disk and update cache."""
    job_dir = get_job_dir(metadata.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    meta_path = job_dir / "metadata.json"
    metadata.updated_at = utc_now()
    with open(meta_path, "w") as f:
        json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)

    # Update cache with new metadata (thread-safe)
    with _cache_lock:
        _metadata_cache[metadata.job_id] = (metadata, time.time())


def update_job_status(
    job_id: str,
    status: Optional[JobStatus] = None,
    stage: Optional[JobStage] = None,
    progress_pct: Optional[int] = None,
    title: Optional[str] = None,
    error_message: Optional[str] = None,
) -> JobMetadata:
    """Update job metadata fields."""
    metadata = load_job_metadata(job_id)
    if metadata is None:
        raise ValueError(f"Job {job_id} not found")
    
    if status is not None:
        metadata.status = status
    if stage is not None:
        metadata.stage = stage
    if progress_pct is not None:
        metadata.progress_pct = progress_pct
    if title is not None:
        metadata.title = title
    if error_message is not None:
        metadata.error_message = error_message
    
    save_job_metadata(metadata)
    return metadata


def get_job_logger(job_id: str) -> logging.Logger:
    """Get a logger that writes to the job's log file."""
    logger = logging.getLogger(f"job.{job_id}")
    logger.setLevel(logging.DEBUG)
    
    # File handler for job-specific log
    log_path = get_job_dir(job_id) / "logs" / "job.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if handler already exists
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(log_path):
            return logger
    
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def read_log_tail(job_id: str, lines: int = 10) -> list[str]:
    """Read the last N lines from the job log."""
    log_path = get_job_dir(job_id) / "logs" / "job.log"
    if not log_path.exists():
        return []
    
    try:
        with open(log_path, "r") as f:
            all_lines = f.readlines()
        return [line.strip() for line in all_lines[-lines:]]
    except Exception:
        return []


def create_sse_event(
    job_id: str,
    stage: str,
    progress_pct: int,
    message: str,
) -> SSEEvent:
    """Create an SSE event payload."""
    return SSEEvent(
        job_id=job_id,
        stage=stage,
        progress_pct=progress_pct,
        message=message,
        log_tail=read_log_tail(job_id, 10),
        timestamp=utc_now(),
    )


def artifact_exists(job_id: str, relative_path: str) -> bool:
    """Check if an artifact file exists in the job directory."""
    path = get_job_dir(job_id) / relative_path
    return path.exists() and path.stat().st_size > 0


def estimate_speech_duration(text: str, wpm: int = 165) -> float:
    """Estimate speech duration in seconds based on word count."""
    word_count = len(text.split())
    return (word_count / wpm) * 60


def get_wpm_for_preset(preset: str) -> int:
    """Get words-per-minute based on preset."""
    presets = {
        "FAST": 180,
        "BALANCED": 165,
        "EXAM": 145,
    }
    return presets.get(preset, 165)
