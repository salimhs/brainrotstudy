"""Main pipeline orchestration for BrainRotStudy."""

import sys
sys.path.insert(0, "/app")

from shared.models import JobStage
from shared.utils import update_job_status, get_job_logger, load_job_metadata

from stages.extract import run_extract_stage
from stages.script import run_script_stage
from stages.timeline import run_timeline_stage
from stages.assets import run_assets_stage
from stages.voice import run_voice_stage
from stages.captions import run_captions_stage
from stages.render import run_render_stage
from stages.finalize import run_finalize_stage


def run_pipeline(job_id: str):
    """
    Run the complete video generation pipeline.
    
    Each stage:
    1. Checks if its output already exists (idempotency)
    2. Runs processing if needed
    3. Emits progress updates
    """
    logger = get_job_logger(job_id)
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    # Define pipeline stages with their progress percentages
    stages = [
        (JobStage.EXTRACT, run_extract_stage, 10),
        (JobStage.SCRIPT, run_script_stage, 25),
        (JobStage.TIMELINE, run_timeline_stage, 35),
        (JobStage.ASSETS, run_assets_stage, 50),
        (JobStage.VOICE, run_voice_stage, 65),
        (JobStage.CAPTIONS, run_captions_stage, 80),
        (JobStage.RENDER, run_render_stage, 95),
        (JobStage.FINALIZE, run_finalize_stage, 100),
    ]
    
    for stage_enum, stage_func, progress in stages:
        logger.info(f"Starting stage: {stage_enum.value}")
        update_job_status(job_id, stage=stage_enum, progress_pct=progress - 10)
        
        try:
            stage_func(job_id)
            logger.info(f"Completed stage: {stage_enum.value}")
            update_job_status(job_id, progress_pct=progress)
        except Exception as e:
            logger.error(f"Stage {stage_enum.value} failed: {str(e)}")
            raise
    
    logger.info("Pipeline completed successfully")
