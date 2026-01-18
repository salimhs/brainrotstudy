"""Celery tasks for the BrainRotStudy pipeline."""

import sys
sys.path.insert(0, "/app")

from celery_app import app
from pipeline import run_pipeline
from shared.models import JobStatus, JobStage
from shared.utils import update_job_status, get_job_logger


@app.task(name="worker.tasks.process_job", bind=True)
def process_job(self, job_id: str):
    """
    Main task that runs the complete video generation pipeline.
    """
    logger = get_job_logger(job_id)
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
        update_job_status(
            job_id,
            status=JobStatus.FAILED,
            error_message=str(e),
        )
        raise
