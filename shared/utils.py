"""Shared utility functions for the BrainRotStudy pipeline."""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from shared.models import JobMetadata, JobStatus, JobStage, SSEEvent, utc_now

# Optional Redis client for pub/sub (lazy loaded)
_redis_pubsub_client = None


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


def get_redis_pubsub_client():
    """Get Redis client for pub/sub (lazy initialization)."""
    global _redis_pubsub_client
    if _redis_pubsub_client is None:
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_pubsub_client = redis.from_url(redis_url, decode_responses=True)
        except Exception:
            # Redis not available, pub/sub disabled
            _redis_pubsub_client = False
    return _redis_pubsub_client if _redis_pubsub_client else None


def save_job_metadata(metadata: JobMetadata) -> None:
    """Save job metadata to disk, update cache, and publish to Redis."""
    job_dir = get_job_dir(metadata.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    meta_path = job_dir / "metadata.json"
    metadata.updated_at = utc_now()
    with open(meta_path, "w") as f:
        json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)

    # Update cache with new metadata (thread-safe)
    with _cache_lock:
        _metadata_cache[metadata.job_id] = (metadata, time.time())

    # Publish metadata update to Redis pub/sub for real-time SSE updates
    try:
        redis_client = get_redis_pubsub_client()
        if redis_client:
            channel = f"job:{metadata.job_id}"
            message = json.dumps({
                "job_id": metadata.job_id,
                "status": metadata.status.value,
                "stage": metadata.stage.value if metadata.stage else None,
                "progress_pct": metadata.progress_pct,
                "error_message": metadata.error_message,
            })
            redis_client.publish(channel, message)
    except Exception:
        # Redis pub/sub failed, fall back to polling
        pass


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


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "job_id"):
            log_data["job_id"] = record.job_id
        if hasattr(record, "stage"):
            log_data["stage"] = record.stage

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_job_logger(job_id: str) -> logging.Logger:
    """
    Get a logger that writes structured JSON logs to the job's log file.
    Uses rotating file handler to prevent unbounded log growth.
    """
    logger = logging.getLogger(f"job.{job_id}")
    logger.setLevel(logging.DEBUG)

    # File handler for job-specific log
    log_path = get_job_dir(job_id) / "logs" / "job.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if handler already exists
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(log_path):
            return logger

    # Use rotating file handler to prevent unbounded growth
    # Max 10MB per file, keep 3 backups (30MB total per job)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)

    # Use JSON formatter for structured logging
    formatter = JSONFormatter()
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Add job_id as default extra field
    logger = logging.LoggerAdapter(logger, {"job_id": job_id})

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
