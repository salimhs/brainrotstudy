"""FastAPI backend for BrainRotStudy - Job management and SSE."""

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import redis

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

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

# SSE Configuration
MAX_SUBSCRIBERS_PER_JOB = 10
MAX_QUEUE_SIZE = 100
SSE_TIMEOUT_SECONDS = 300  # 5 minutes

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_JOBS_PER_HOUR = int(os.getenv("RATE_LIMIT_JOBS_PER_HOUR", "10"))
RATE_LIMIT_DOWNLOADS_PER_HOUR = int(os.getenv("RATE_LIMIT_DOWNLOADS_PER_HOUR", "100"))

# In-memory SSE subscribers (for simple single-instance setup)
job_subscribers: dict[str, list[asyncio.Queue]] = {}

# Cached Celery app instance
_celery_app = None

# Cached Redis client for rate limiting
_redis_client = None

# Prometheus Metrics
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"

# Counters
jobs_created_total = Counter(
    'brainrotstudy_jobs_created_total',
    'Total number of jobs created',
    ['input_type']
)

jobs_completed_total = Counter(
    'brainrotstudy_jobs_completed_total',
    'Total number of jobs completed',
    ['status']
)

# Gauges
sse_connections_active = Gauge(
    'brainrotstudy_sse_connections_active',
    'Number of active SSE connections',
    ['job_id']
)

jobs_by_status = Gauge(
    'brainrotstudy_jobs_by_status',
    'Number of jobs by status',
    ['status']
)

# Histograms
job_duration_seconds = Histogram(
    'brainrotstudy_job_duration_seconds',
    'Job processing duration in seconds',
    buckets=(30, 60, 120, 300, 600, 1200, 1800, 3600)
)

api_request_duration_seconds = Histogram(
    'brainrotstudy_api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10)
)


def get_celery():
    """Get cached Celery app instance (lazy initialization)."""
    global _celery_app
    if _celery_app is None:
        from celery import Celery
        _celery_app = Celery("worker", broker=REDIS_URL, backend=REDIS_URL)
    return _celery_app


def get_redis():
    """Get cached Redis client instance (lazy initialization)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def get_redis_async():
    """Get async Redis client for pub/sub."""
    try:
        import redis.asyncio as aioredis
        return aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None


def check_rate_limit(request: Request, limit_per_hour: int, resource: str) -> None:
    """
    Check if client has exceeded rate limit.
    Uses Redis to track request counts per IP address.
    Raises HTTPException(429) if limit exceeded.
    """
    if not RATE_LIMIT_ENABLED:
        return

    try:
        client_ip = request.client.host if request.client else "unknown"
        redis_client = get_redis()

        # Redis key format: ratelimit:{resource}:{ip}
        key = f"ratelimit:{resource}:{client_ip}"

        # Get current count
        count = redis_client.get(key)

        if count is None:
            # First request in this hour window
            redis_client.setex(key, 3600, 1)  # Expire after 1 hour
        elif int(count) >= limit_per_hour:
            # Rate limit exceeded
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {limit_per_hour} {resource} requests per hour"
            )
        else:
            # Increment counter
            redis_client.incr(key)

    except HTTPException:
        raise
    except Exception as e:
        # If Redis fails, log but don't block the request
        print(f"Rate limit check failed: {e}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Exposes application metrics for monitoring and alerting.
    """
    if not METRICS_ENABLED:
        raise HTTPException(status_code=404, detail="Metrics endpoint disabled")

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/jobs")
async def create_job(request: Request):
    """
    Create a new video generation job.

    Accepts either:
    - multipart/form-data with file upload and options JSON string
    - application/json with topic and options

    Rate limited to prevent abuse.
    """
    # Check rate limit
    check_rate_limit(request, RATE_LIMIT_JOBS_PER_HOUR, "jobs")

    try:
        job_id = str(uuid.uuid4())[:8]
        dirs = ensure_job_dirs(job_id)
        
        # Parse options
        job_options = JobOptions()
        topic = None
        outline = None
        input_type = "topic"
        input_filename = None
        file = None
        
        # Check Content-Type to determine how to parse the request
        content_type = request.headers.get("content-type", "")
        
        if "multipart/form-data" in content_type:
            # File upload mode
            try:
                form = await request.form()
                file = form.get("file")
                options_str = form.get("options")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse form data: {str(e)}")
            
            if file and hasattr(file, 'filename') and file.filename:
                input_type = "file"
                input_filename = file.filename
                
                # Validate file extension
                ext = Path(file.filename).suffix.lower()
                if ext not in [".pdf", ".pptx"]:
                    raise HTTPException(status_code=400, detail="Only PDF and PPTX files are supported")
                
                # Validate file size (max 100MB)
                file_content = await file.read()
                if len(file_content) > 100 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="File size exceeds 100MB limit")
                
                # Save uploaded file
                try:
                    input_path = dirs["input"] / file.filename
                    with open(input_path, "wb") as f:
                        f.write(file_content)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")
                
                # Parse options from form data
                if options_str:
                    try:
                        opts_dict = json.loads(options_str)
                        job_options = JobOptions.model_validate(opts_dict)
                    except json.JSONDecodeError as e:
                        print(f"Warning: Invalid options JSON, using defaults: {e}")
                    except Exception as e:
                        print(f"Warning: Failed to validate options, using defaults: {e}")
            else:
                raise HTTPException(status_code=400, detail="File is required for multipart upload")
        
        elif "application/json" in content_type:
            # JSON body mode (topic-only)
            try:
                body_data = await request.json()
                body = JobCreate.model_validate(body_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON body: {str(e)}")
            
            topic = body.topic
            outline = body.outline
            job_options = body.options
            
            if not topic:
                raise HTTPException(status_code=400, detail="Topic is required for topic-only jobs")
            
            # Save topic and outline to input dir
            try:
                topic_path = dirs["input"] / "topic.json"
                with open(topic_path, "w") as f:
                    json.dump({"topic": topic, "outline": outline}, f, indent=2)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to save topic data: {str(e)}")
        
        else:
            raise HTTPException(status_code=400, detail="Content-Type must be multipart/form-data or application/json")
        
        # Create job metadata
        title = topic if topic else (input_filename or "Untitled")
        try:
            metadata = JobMetadata(
                job_id=job_id,
                status=JobStatus.QUEUED,
                title=title,
                input_type=input_type,
                input_filename=input_filename,
                options=job_options,
            )
            save_job_metadata(metadata)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save job metadata: {str(e)}")
        
        # Enqueue Celery task
        try:
            celery = get_celery()
            celery.send_task("worker.tasks.process_job", args=[job_id])
        except Exception as e:
            # Log but don't fail - worker might process from metadata
            print(f"Warning: Could not enqueue Celery task: {e}")

        # Track metrics
        if METRICS_ENABLED:
            jobs_created_total.labels(input_type=input_type).inc()
            jobs_by_status.labels(status="queued").inc()

        return {"job_id": job_id}
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any unexpected errors
        print(f"Unexpected error in create_job: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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
    SSE endpoint for real-time job updates with connection pooling and backpressure.
    """
    metadata = load_job_metadata(job_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check subscriber limit
    if job_id in job_subscribers and len(job_subscribers[job_id]) >= MAX_SUBSCRIBERS_PER_JOB:
        raise HTTPException(
            status_code=429,
            detail=f"Too many concurrent connections for this job (max {MAX_SUBSCRIBERS_PER_JOB})"
        )

    async def event_generator():
        # Create a bounded queue for this subscriber
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        start_time = asyncio.get_event_loop().time()

        if job_id not in job_subscribers:
            job_subscribers[job_id] = []
        job_subscribers[job_id].append(queue)

        # Track SSE connection metric
        if METRICS_ENABLED:
            sse_connections_active.labels(job_id=job_id).inc()

        # Try to use Redis pub/sub for real-time updates
        redis_client = get_redis_async()
        use_pubsub = redis_client is not None

        try:
            # Send SSE retry header (client should reconnect after 2 seconds if disconnected)
            yield f"retry: 2000\n\n"

            # Send initial state
            event = create_sse_event(
                job_id=job_id,
                stage=metadata.stage.value if metadata.stage else "queued",
                progress_pct=metadata.progress_pct,
                message=f"Job status: {metadata.status.value}",
            )
            yield f"data: {event.model_dump_json()}\n\n"

            if use_pubsub:
                # Redis pub/sub mode: Event-driven updates
                pubsub = redis_client.pubsub()
                channel = f"job:{job_id}"
                await pubsub.subscribe(channel)

                try:
                    keepalive_task = None
                    last_keepalive = asyncio.get_event_loop().time()

                    while True:
                        # Check connection timeout
                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed > SSE_TIMEOUT_SECONDS:
                            print(f"SSE connection timeout for job {job_id}")
                            break

                        # Listen for pub/sub messages with timeout
                        try:
                            message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=5.0)

                            if message and message["type"] == "message":
                                # Parse message and send SSE event
                                data = json.loads(message["data"])
                                current_meta = load_job_metadata(job_id)

                                if current_meta:
                                    event = create_sse_event(
                                        job_id=job_id,
                                        stage=current_meta.stage.value if current_meta.stage else "queued",
                                        progress_pct=current_meta.progress_pct,
                                        message=f"Job status: {current_meta.status.value}",
                                    )
                                    yield f"data: {event.model_dump_json()}\n\n"

                                    # Stop if job is done
                                    if current_meta.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                                        break

                        except asyncio.TimeoutError:
                            # No message received, send keepalive if needed
                            current_time = asyncio.get_event_loop().time()
                            if current_time - last_keepalive > 30:
                                yield ": keepalive\n\n"
                                last_keepalive = current_time

                finally:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()

            else:
                # Fallback to polling mode
                last_status = metadata.status
                last_progress = metadata.progress_pct
                poll_count = 0

                while True:
                    # Check connection timeout
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > SSE_TIMEOUT_SECONDS:
                        print(f"SSE connection timeout for job {job_id}")
                        break

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

                            # Use try/except for backpressure handling
                            try:
                                # Non-blocking put (fails if queue is full)
                                queue.put_nowait(event)
                                yield f"data: {event.model_dump_json()}\n\n"
                            except asyncio.QueueFull:
                                print(f"SSE queue full for job {job_id}, dropping event")
                                # Drop event rather than blocking (backpressure)

                            last_status = current_meta.status
                            last_progress = current_meta.progress_pct

                        # Stop streaming if job is done
                        if current_meta.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                            break

                    # Send keepalive comment every 30 seconds to prevent timeout
                    poll_count += 1
                    if poll_count % 30 == 0:
                        yield ": keepalive\n\n"

                    await asyncio.sleep(1)  # Poll every second

        finally:
            # Clean up subscriber
            if job_id in job_subscribers and queue in job_subscribers[job_id]:
                job_subscribers[job_id].remove(queue)

                # Clean up empty subscriber lists
                if not job_subscribers[job_id]:
                    del job_subscribers[job_id]

            # Decrement SSE connection metric
            if METRICS_ENABLED:
                sse_connections_active.labels(job_id=job_id).dec()

            # Close Redis connection if used
            if use_pubsub and redis_client:
                try:
                    await redis_client.close()
                except Exception:
                    pass

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
async def download_video(job_id: str, request: Request):
    """Download the final MP4 video. Rate limited to prevent abuse."""
    check_rate_limit(request, RATE_LIMIT_DOWNLOADS_PER_HOUR, "downloads")

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
