"""Pipeline orchestrator: run all stages for one job and stream progress."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..config import get_settings
from ..db import get_job, update_job
from ..events import bus
from ..schemas import (
    JobStage,
    JobStatus,
    ProgressEvent,
    Script,
    Timeline,
    TimelineSegment,
)
from ..storage import JobPaths
from . import exports, extract, narrate, render, script, visuals

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage plan: each stage advertises a progress range so SSE has smooth forward
# motion regardless of how much wall-clock each actually takes.


STAGES: list[tuple[JobStage, int, int]] = [
    (JobStage.EXTRACT, 1, 10),
    (JobStage.SCRIPT, 10, 30),
    (JobStage.NARRATE, 30, 60),
    (JobStage.VISUALS, 60, 75),
    (JobStage.RENDER, 75, 95),
    (JobStage.EXPORTS, 95, 100),
]


async def run_job(job_id: str) -> None:
    """Run the full pipeline for a job and publish progress events."""
    settings = get_settings()
    job = get_job(job_id)
    if job is None:
        raise RuntimeError(f"job {job_id} not found")

    paths = JobPaths(job_id=job_id, root=settings.resolve_storage() / "jobs" / job_id)
    paths.ensure()

    opts = job.options
    loop = asyncio.get_running_loop()

    async def emit(stage: JobStage, pct: int, message: str) -> None:
        update_job(job_id, status=JobStatus.RUNNING, stage=stage, progress=pct)
        await bus.publish(
            ProgressEvent(id=job_id, status=JobStatus.RUNNING, stage=stage, progress=pct, message=message)
        )

    try:
        await emit(JobStage.EXTRACT, 2, "Parsing source material…")
        content = await loop.run_in_executor(None, _do_extract, paths, job.input_filename, job.title, None)
        if opts is not None and getattr(opts, "language", None):
            pass  # reserved for i18n later
        await emit(JobStage.EXTRACT, 10, f"Extracted {len(content.sections)} sections.")

        await emit(JobStage.SCRIPT, 15, "Writing your script…")
        script_obj = await loop.run_in_executor(None, script.generate_script, content, opts)
        update_job(job_id, title=script_obj.title)
        paths.script_path.write_text(script_obj.model_dump_json(indent=2), encoding="utf-8")
        await emit(JobStage.SCRIPT, 30, f"Script: {len(script_obj.segments)} segments.")

        await emit(JobStage.NARRATE, 35, "Synthesizing narration…")
        narrated, voice_path = await loop.run_in_executor(
            None, _do_narrate, script_obj, paths, opts.language
        )
        await emit(JobStage.NARRATE, 60, f"Voice: {narrated[-1].end_sec:.1f}s of audio.")

        await emit(JobStage.VISUALS, 65, "Hunting for visuals…")
        clips = await loop.run_in_executor(
            None,
            lambda: visuals.fetch_visuals(narrated, paths.visuals_dir, title=script_obj.title),
        )
        await emit(JobStage.VISUALS, 75, f"{len(clips)} visuals ready.")

        timeline = _build_timeline(
            narrated=narrated,
            clips=clips,
            voice_path=voice_path,
            opts=opts,
            settings=settings,
        )
        paths.timeline_path.write_text(timeline.model_dump_json(indent=2), encoding="utf-8")

        await emit(JobStage.RENDER, 80, "Rendering video…")
        await loop.run_in_executor(None, render.render_video, timeline, paths)
        await emit(JobStage.RENDER, 95, "Video rendered.")

        if opts.export_extras:
            await emit(JobStage.EXPORTS, 97, "Writing study notes…")
            await loop.run_in_executor(
                None,
                lambda: (
                    exports.write_notes(script_obj, paths.notes_path),
                    exports.write_anki(script_obj, paths.anki_path),
                ),
            )

        update_job(job_id, status=JobStatus.SUCCEEDED, progress=100)
        await bus.publish(
            ProgressEvent(
                id=job_id,
                status=JobStatus.SUCCEEDED,
                stage=JobStage.EXPORTS,
                progress=100,
                message="Video ready.",
            )
        )
    except Exception as e:
        log.exception("job %s failed", job_id)
        err = f"{type(e).__name__}: {e}"
        update_job(job_id, status=JobStatus.FAILED, error=err)
        await bus.publish(
            ProgressEvent(
                id=job_id,
                status=JobStatus.FAILED,
                stage=None,
                progress=100,
                message=err,
            )
        )
    finally:
        await bus.close(job_id)


# ---------------------------------------------------------------------------
# Extraction dispatcher — selects between topic and file-based flows.


def _do_extract(paths: JobPaths, input_filename: str | None, title: str, _placeholder):
    input_dir = paths.input_dir
    files = sorted(p for p in input_dir.iterdir() if p.is_file()) if input_dir.exists() else []
    topic_file = input_dir / "topic.txt"
    if topic_file in files:
        text = topic_file.read_text(encoding="utf-8")
        topic_line, _, outline = text.partition("\n")
        content = extract.extract_from_topic(topic_line.strip() or title, outline.strip() or None)
    elif files:
        content = extract.extract_from_path(files[0])
    else:
        content = extract.extract_from_topic(title)
    paths.extract_path.write_text(content.model_dump_json(indent=2), encoding="utf-8")
    return content


def _do_narrate(script_obj: Script, paths: JobPaths, language: str):
    return narrate.narrate(script_obj, paths, language=language)


# ---------------------------------------------------------------------------


def _build_timeline(*, narrated, clips, voice_path: Path, opts, settings) -> Timeline:
    segments = [
        TimelineSegment(
            text=n.text,
            emphasis=n.emphasis,
            start_sec=n.start_sec,
            end_sec=n.end_sec,
            image_path=clips[i].path if i < len(clips) else None,
            caption_style=opts.caption_style,
        )
        for i, n in enumerate(narrated)
    ]
    total = narrated[-1].end_sec if narrated else float(opts.length_sec)
    return Timeline(
        width=settings.video_width,
        height=settings.video_height,
        duration_sec=total,
        segments=segments,
        voice_path=str(voice_path),
    )


# ---------------------------------------------------------------------------
# Job submission + concurrency limiter


_semaphore: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrent_jobs)
    return _semaphore


async def _run_with_limit(job_id: str) -> None:
    async with _sem():
        await run_job(job_id)


def submit_job(job_id: str, *, loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task:
    """Schedule ``run_job`` on the running loop and return the Task."""
    loop = loop or asyncio.get_event_loop()
    return loop.create_task(_run_with_limit(job_id), name=f"job:{job_id}")
