#!/usr/bin/env python3
"""
Cleanup script: Delete jobs older than retention period.
Prevents unbounded disk growth by removing old job directories.
"""
import os
import shutil
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/app/storage"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "6"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_job_age_days(job_dir: Path) -> float:
    """Get age of job in days based on metadata.json mtime."""
    metadata_file = job_dir / "metadata.json"
    if not metadata_file.exists():
        # Fallback to directory mtime
        return (time.time() - job_dir.stat().st_mtime) / 86400

    mtime = metadata_file.stat().st_mtime
    age_seconds = time.time() - mtime
    return age_seconds / 86400


def get_job_size_mb(job_dir: Path) -> float:
    """Calculate total size of job directory in MB."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(job_dir):
        for filename in filenames:
            filepath = Path(dirpath) / filename
            try:
                total_size += filepath.stat().st_size
            except (OSError, FileNotFoundError):
                pass
    return total_size / (1024 * 1024)


def cleanup_old_jobs():
    """Remove job directories older than retention period."""
    jobs_dir = STORAGE_ROOT / "jobs"

    if not jobs_dir.exists():
        logger.warning(f"Jobs directory not found: {jobs_dir}")
        return

    cutoff_days = RETENTION_DAYS
    deleted_count = 0
    deleted_size_mb = 0
    total_jobs = 0

    logger.info(f"Starting cleanup: removing jobs older than {cutoff_days} days")

    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue

        total_jobs += 1

        try:
            age_days = get_job_age_days(job_dir)

            if age_days > cutoff_days:
                size_mb = get_job_size_mb(job_dir)
                job_id = job_dir.name

                logger.info(f"Deleting job {job_id} (age: {age_days:.1f} days, size: {size_mb:.1f} MB)")

                shutil.rmtree(job_dir)
                deleted_count += 1
                deleted_size_mb += size_mb

        except Exception as e:
            logger.error(f"Failed to process job {job_dir.name}: {e}")

    logger.info(
        f"Cleanup complete: deleted {deleted_count}/{total_jobs} jobs, "
        f"freed {deleted_size_mb:.1f} MB"
    )


def run_cleanup_loop():
    """Run cleanup in infinite loop with interval."""
    logger.info(f"Cleanup service started (interval: {CLEANUP_INTERVAL_HOURS}h, retention: {RETENTION_DAYS}d)")

    while True:
        try:
            cleanup_old_jobs()
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

        sleep_seconds = CLEANUP_INTERVAL_HOURS * 3600
        logger.info(f"Sleeping for {CLEANUP_INTERVAL_HOURS} hours")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    # Support both one-shot and continuous mode
    if os.getenv("CLEANUP_MODE", "loop") == "once":
        cleanup_old_jobs()
    else:
        run_cleanup_loop()
