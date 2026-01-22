"""Celery tasks for the BrainRotStudy pipeline."""

import sys
sys.path.insert(0, "/app")

from celery_app import app
from pipeline import run_pipeline
from shared.models import JobStatus, JobStage
from shared.utils import update_job_status, get_job_logger


# Define transient exceptions that should trigger retries
TRANSIENT_EXCEPTIONS = (
    # Network errors
    ConnectionError,
    TimeoutError,
    # HTTP errors (often transient)
    Exception,  # Will be filtered below
)


def is_transient_error(exc: Exception) -> bool:
    """
    Determine if an exception is transient and should be retried.
    Only retry on network/API timeouts, not on validation or permanent errors.
    """
    exc_str = str(exc).lower()

    # Transient indicators
    transient_keywords = [
        'timeout',
        'connection',
        'network',
        'temporary',
        'rate limit',
        'throttle',
        'unavailable',
        'service unavailable',
        '429',
        '500',
        '502',
        '503',
        '504',
    ]

    # Don't retry on these permanent error keywords
    permanent_keywords = [
        'not found',
        'invalid',
        'validation',
        'unauthorized',
        '401',
        '403',
        '404',
    ]

    # Check for permanent errors first
    if any(keyword in exc_str for keyword in permanent_keywords):
        return False

    # Check for transient errors
    if any(keyword in exc_str for keyword in transient_keywords):
        return True

    # Check exception types
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    return False


@app.task(
    name="worker.tasks.process_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # Start with 60 seconds
)
def process_job(self, job_id: str):
    """
    Main task that runs the complete video generation pipeline.
    Automatically retries on transient failures with exponential backoff.
    """
    logger = get_job_logger(job_id)
    retry_num = self.request.retries

    if retry_num > 0:
        logger.info(f"Starting job {job_id} (retry {retry_num}/3)")
    else:
        logger.info(f"Starting job {job_id}")

    try:
        # Update status to running
        update_job_status(job_id, status=JobStatus.RUNNING, progress_pct=0)

        # Run the pipeline
        run_pipeline(job_id)

        # Mark as succeeded
        update_job_status(job_id, status=JobStatus.SUCCEEDED, progress_pct=100)
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")

        # Check if this is a transient error that should be retried
        if is_transient_error(e) and self.request.retries < self.max_retries:
            # Exponential backoff: 60s, 120s, 240s
            countdown = 60 * (2 ** self.request.retries)
            logger.warning(
                f"Transient error detected, retrying in {countdown}s "
                f"(attempt {self.request.retries + 1}/{self.max_retries})"
            )

            # Update status to show it's retrying
            update_job_status(
                job_id,
                status=JobStatus.QUEUED,  # Back to queued while retrying
                error_message=f"Retrying after error: {str(e)}"
            )

            # Retry the task
            raise self.retry(exc=e, countdown=countdown)

        # If not transient or max retries reached, mark as failed
        update_job_status(
            job_id,
            status=JobStatus.FAILED,
            error_message=str(e),
        )
        raise
