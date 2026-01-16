"""FastAPI backend for BrainRotStudy - Job management and SSE."""

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, "/app")

from shared.models import (
    JobCreate,
    JobMetadata,
    JobOptions,
    JobResponse,
    JobStatus,
    JobArtifacts,
    SSEEvent,
)
from shared.utils import (
    ensure_job_dirs,
    get_job_dir,
    load_job_metadata,
    save_job_metadata,
    read_log_tail,
    create_sse_event,
)


app = FastAPI(
    title="BrainRotStudy API",
    description="API for generating TikTok-style study videos from PDFs, slides, or topics",
    version="1.0.0",
)

# Add GZip compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection for Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# In-memory SSE subscribers (for simple single-instance setup)
job_subscribers: dict[str, list[asyncio.Queue]] = {}


def get_celery():
    """Lazy import Celery to avoid circular imports."""
    from celery import Celery
    return Celery("worker", broker=REDIS_URL, backend=REDIS_URL)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/jobs")
async def create_job(
    file: Optional[UploadFile] = File(None),
    options: Optional[str] = Form(None),
    body: Optional[JobCreate] = None,
):
    """
    Create a new video generation job.
    
    Accepts either:
    - multipart/form-data with file upload and options JSON string
    - application/json with topic and options
    """
    job_id = str(uuid.uuid4())[:8]
    dirs = ensure_job_dirs(job_id)
    
    # Parse options
    job_options = JobOptions()
    topic = None
    outline = None
    input_type = "topic"
    input_filename = None
    
    if file and file.filename:
        # File upload mode
        input_type = "file"
        input_filename = file.filename
        
        # Validate file extension
        ext = Path(file.filename).suffix.lower()
        if ext not in [".pdf", ".pptx"]:
            raise HTTPException(status_code=400, detail="Only PDF and PPTX files are supported")
        
        # Save uploaded file
        input_path = dirs["input"] / file.filename
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Parse options from form data
        if options:
            try:
                opts_dict = json.loads(options)
                job_options = JobOptions.model_validate(opts_dict)
            except Exception:
                pass
    
    elif body:
        # JSON body mode (topic-only)
        topic = body.topic
        outline = body.outline
        job_options = body.options
        
        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required for topic-only jobs")
        
        # Save topic and outline to input dir
        topic_path = dirs["input"] / "topic.json"
        with open(topic_path, "w") as f:
            json.dump({"topic": topic, "outline": outline}, f, indent=2)
    
    else:
        raise HTTPException(status_code=400, detail="Either file upload or topic is required")
    
    # Create job metadata
    title = topic if topic else (input_filename or "Untitled")
    metadata = JobMetadata(
        job_id=job_id,
        status=JobStatus.QUEUED,
        title=title,
        input_type=input_type,
        input_filename=input_filename,
        options=job_options,
    )
    save_job_metadata(metadata)
    
    # Enqueue Celery task
    try:
        celery = get_celery()
        celery.send_task("worker.tasks.process_job", args=[job_id])
    except Exception as e:
        # Log but don't fail - worker might process from metadata
        print(f"Warning: Could not enqueue Celery task: {e}")
    
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job status and metadata."""
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Build artifacts URLs if job succeeded
    artifacts = None
    if metadata.status == JobStatus.SUCCEEDED:
        job_dir = get_job_dir(job_id)
        artifacts = JobArtifacts()
        
        if (job_dir / "output" / "final.mp4").exists():
            artifacts.video_url = f"/jobs/{job_id}/download"
        if (job_dir / "output" / "captions.srt").exists():
            artifacts.srt_url = f"/jobs/{job_id}/download/srt"
        if (job_dir / "output" / "notes.md").exists():
            artifacts.notes_url = f"/jobs/{job_id}/download/notes"
        if (job_dir / "output" / "anki.csv").exists():
            artifacts.anki_url = f"/jobs/{job_id}/download/anki"
    
    return JobResponse(
        job_id=metadata.job_id,
        status=metadata.status,
        stage=metadata.stage,
        progress_pct=metadata.progress_pct,
        title=metadata.title,
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
        artifacts=artifacts,
        error_message=metadata.error_message,
    )


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    """
    SSE endpoint for real-time job updates.
    """
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")
    
    async def event_generator():
        # Create a queue for this subscriber
        queue: asyncio.Queue = asyncio.Queue()
        
        if job_id not in job_subscribers:
            job_subscribers[job_id] = []
        job_subscribers[job_id].append(queue)
        
        try:
            # Send initial state
            event = create_sse_event(
                job_id=job_id,
                stage=metadata.stage.value if metadata.stage else "queued",
                progress_pct=metadata.progress_pct,
                message=f"Job status: {metadata.status.value}",
            )
            yield f"data: {event.model_dump_json()}\n\n"
            
            # Poll for updates (simple approach for MVP)
            last_status = metadata.status
            last_progress = metadata.progress_pct
            
            while True:
                # Check for updates
                current_meta = load_job_metadata(job_id)
                if current_meta:
                    if (current_meta.status != last_status or 
                        current_meta.progress_pct != last_progress):
                        
                        event = create_sse_event(
                            job_id=job_id,
                            stage=current_meta.stage.value if current_meta.stage else "queued",
                            progress_pct=current_meta.progress_pct,
                            message=f"Job status: {current_meta.status.value}",
                        )
                        yield f"data: {event.model_dump_json()}\n\n"
                        
                        last_status = current_meta.status
                        last_progress = current_meta.progress_pct
                    
                    # Stop streaming if job is done
                    if current_meta.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                        break
                
                await asyncio.sleep(1)  # Poll every second
                
        finally:
            # Clean up subscriber
            if job_id in job_subscribers and queue in job_subscribers[job_id]:
                job_subscribers[job_id].remove(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/jobs/{job_id}/download")
async def download_video(job_id: str):
    """Download the final MP4 video."""
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")
    
    video_path = get_job_dir(job_id) / "output" / "final.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not ready")
    
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"{metadata.title.replace(' ', '_')}.mp4",
    )


@app.get("/jobs/{job_id}/download/srt")
async def download_srt(job_id: str):
    """Download the SRT captions file."""
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")
    
    srt_path = get_job_dir(job_id) / "output" / "captions.srt"
    if not srt_path.exists():
        raise HTTPException(status_code=404, detail="SRT file not available")
    
    return FileResponse(
        srt_path,
        media_type="text/plain",
        filename=f"{metadata.title.replace(' ', '_')}.srt",
    )


@app.get("/jobs/{job_id}/download/notes")
async def download_notes(job_id: str):
    """Download the notes markdown file."""
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")
    
    notes_path = get_job_dir(job_id) / "output" / "notes.md"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail="Notes file not available")
    
    return FileResponse(
        notes_path,
        media_type="text/markdown",
        filename=f"{metadata.title.replace(' ', '_')}_notes.md",
    )


@app.get("/jobs/{job_id}/download/anki")
async def download_anki(job_id: str):
    """Download the Anki flashcards CSV."""
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")
    
    anki_path = get_job_dir(job_id) / "output" / "anki.csv"
    if not anki_path.exists():
        raise HTTPException(status_code=404, detail="Anki file not available")
    
    return FileResponse(
        anki_path,
        media_type="text/csv",
        filename=f"{metadata.title.replace(' ', '_')}_anki.csv",
    )


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its directory."""
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        shutil.rmtree(job_dir)
        return {"status": "deleted", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
