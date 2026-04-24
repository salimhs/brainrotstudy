"""FastAPI application: HTTP + SSE."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from . import db
from .config import get_settings
from .events import bus
from .pipeline.runner import submit_job
from .schemas import (
    Artifacts,
    JobCreate,
    JobOptions,
    JobStatus,
    JobView,
    ProgressEvent,
)
from .storage import job_paths

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_settings = get_settings()

app = FastAPI(title="BrainRotStudy", version="2.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    db._connect()
    log.info("brainrotstudy ready; storage=%s", _settings.resolve_storage())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
async def config() -> dict[str, object]:
    """Expose which providers are usable so the frontend can set expectations."""
    s = get_settings()
    return {
        "llm": {
            "gemini": bool(s.google_api_key),
            "anthropic": bool(s.anthropic_api_key),
            "openai": bool(s.openai_api_key),
        },
        "tts": {"elevenlabs": bool(s.elevenlabs_api_key), "gtts": True},
        "images": {"pexels": bool(s.pexels_api_key), "openverse": True},
        "ffmpeg": bool(shutil.which(s.ffmpeg_binary)),
        "max_upload_mb": s.max_upload_mb,
    }


@app.get("/jobs", response_model=list[JobView])
async def list_jobs() -> list[JobView]:
    return _with_artifacts(db.list_jobs())


@app.post("/jobs", response_model=JobView)
async def create_job(request: Request) -> JobView:
    content_type = request.headers.get("content-type", "")
    job_id = uuid.uuid4().hex[:10]
    paths = job_paths(job_id).ensure()

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        options_json = form.get("options") or "{}"
        if upload is None or not hasattr(upload, "read") or not hasattr(upload, "filename"):
            raise HTTPException(400, "Expected 'file' field.")
        options = _parse_options(options_json)
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in {".pdf", ".pptx", ".txt", ".md"}:
            raise HTTPException(400, "File must be one of: pdf, pptx, txt, md")
        target = paths.input_dir / (upload.filename or f"upload{ext}")
        data = await upload.read()
        if len(data) > _settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"File exceeds {_settings.max_upload_mb} MB limit.")
        target.write_bytes(data)
        view = db.create_job(
            job_id,
            title=target.stem.replace("_", " "),
            input_kind="file",
            input_filename=target.name,
            options=options,
        )
    else:
        body = await request.json()
        payload = JobCreate.model_validate(body)
        if not payload.topic or not payload.topic.strip():
            raise HTTPException(400, "Topic is required.")
        topic_file = paths.input_dir / "topic.txt"
        text = payload.topic.strip()
        if payload.outline:
            text = f"{text}\n{payload.outline.strip()}"
        topic_file.write_text(text, encoding="utf-8")
        view = db.create_job(
            job_id,
            title=payload.topic.strip()[:120],
            input_kind="topic",
            input_filename=None,
            options=payload.options,
        )

    submit_job(job_id)
    return _with_artifacts([view])[0]


@app.get("/jobs/{job_id}", response_model=JobView)
async def get_job(job_id: str) -> JobView:
    view = db.get_job(job_id)
    if view is None:
        raise HTTPException(404, "Job not found.")
    return _with_artifacts([view])[0]


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict[str, str]:
    view = db.get_job(job_id)
    if view is None:
        raise HTTPException(404, "Job not found.")
    db.delete_job(job_id)
    root = job_paths(job_id).root
    if root.exists():
        shutil.rmtree(root)
    return {"id": job_id, "deleted": "true"}


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    view = db.get_job(job_id)
    if view is None:
        raise HTTPException(404, "Job not found.")

    async def gen():
        yield "retry: 2000\n\n"
        view_now = db.get_job(job_id)
        if view_now is None:
            return
        snapshot = ProgressEvent(
            id=job_id,
            status=view_now.status,
            stage=view_now.stage,
            progress=view_now.progress,
            message=f"snapshot:{view_now.status.value}",
        )
        yield _sse(snapshot)
        if view_now.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return
        async for evt in bus.subscribe(job_id):
            yield _sse(evt)
            if evt.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/jobs/{job_id}/download/{asset}")
async def download(job_id: str, asset: str) -> FileResponse:
    view = db.get_job(job_id)
    if view is None:
        raise HTTPException(404, "Job not found.")
    paths = job_paths(job_id)
    mapping = {
        "video": (paths.video_path, "video/mp4", ".mp4"),
        "srt": (paths.srt_path, "application/x-subrip", ".srt"),
        "notes": (paths.notes_path, "text/markdown", ".md"),
        "anki": (paths.anki_path, "text/csv", ".csv"),
    }
    if asset not in mapping:
        raise HTTPException(404, "Unknown asset.")
    path, mime, ext = mapping[asset]
    if not path.exists():
        raise HTTPException(404, f"{asset} not ready.")
    safe = _safe_stem(view.title) or job_id
    return FileResponse(path, media_type=mime, filename=f"{safe}{ext}")


# ---------------------------------------------------------------------------


def _safe_stem(title: str) -> str:
    keep = [c if c.isalnum() or c in {"-", "_"} else "_" for c in title.strip()]
    return "".join(keep)[:80].strip("_")


def _parse_options(raw: object) -> JobOptions:
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        data = {}
    return JobOptions.model_validate(data)


def _sse(event: ProgressEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def _with_artifacts(views: list[JobView]) -> list[JobView]:
    for v in views:
        if v.status != JobStatus.SUCCEEDED:
            continue
        paths = job_paths(v.id)
        arts = Artifacts()
        if paths.video_path.exists():
            arts.video_url = f"/jobs/{v.id}/download/video"
        if paths.srt_path.exists():
            arts.srt_url = f"/jobs/{v.id}/download/srt"
        if paths.notes_path.exists():
            arts.notes_url = f"/jobs/{v.id}/download/notes"
        if paths.anki_path.exists():
            arts.anki_url = f"/jobs/{v.id}/download/anki"
        v.artifacts = arts
    return views
