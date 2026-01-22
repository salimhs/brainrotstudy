"""Stage 7: Render final video using FFmpeg."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/app")

from shared.models import (
    TimelinePlan, CaptionsWordLevel, AssetsManifest, MotionStyle
)
from shared.utils import get_job_dir, get_job_logger, load_job_metadata


def run_render_stage(job_id: str) -> None:
    """
    Render the final video using FFmpeg.
    
    Creates a 1080x1920 vertical video with:
    - Top half: slides/visuals with Ken Burns effect
    - Bottom half: background video loop
    - Captions overlay
    - Voice + music audio mix
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    metadata = load_job_metadata(job_id)
    
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    # Check for idempotency
    raw_video_path = job_dir / "render" / "video_raw.mp4"
    if raw_video_path.exists() and raw_video_path.stat().st_size > 0:
        logger.info("CACHE HIT: video_raw.mp4 already exists, skipping")
        return
    
    # Load required data
    timeline_path = job_dir / "render" / "timeline.json"
    if not timeline_path.exists():
        raise ValueError("timeline.json not found")
    
    with open(timeline_path, "r") as f:
        timeline = TimelinePlan.model_validate(json.load(f))
    
    captions_path = job_dir / "captions" / "captions.json"
    captions = None
    if captions_path.exists():
        with open(captions_path, "r") as f:
            captions = CaptionsWordLevel.model_validate(json.load(f))
    
    manifest_path = job_dir / "assets" / "assets_manifest.json"
    manifest = None
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            manifest = AssetsManifest.model_validate(json.load(f))
    
    voice_path = job_dir / "audio" / "voice.wav"
    
    render_dir = job_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Try full render first
        render_full_video(
            job_id, timeline, captions, manifest, 
            voice_path, raw_video_path, logger
        )
    except Exception as e:
        logger.warning(f"Full render failed: {e}, trying simple render")
        render_simple_video(
            job_id, timeline, voice_path, raw_video_path, logger
        )
    
    logger.info("Video rendering completed")


def render_full_video(
    job_id: str,
    timeline: TimelinePlan,
    captions: Optional[CaptionsWordLevel],
    manifest: Optional[AssetsManifest],
    voice_path: Path,
    output_path: Path,
    logger
) -> None:
    """Render video with visuals, captions, and audio mix."""
    job_dir = get_job_dir(job_id)
    duration = timeline.total_duration_sec
    
    # Video dimensions (vertical)
    width, height = 1080, 1920
    top_height = 960
    
    # Find background video
    bg_video_path = None
    music_path = None
    
    if manifest:
        for item in manifest.items:
            if item.type == "bg_video" and Path(item.path).exists():
                bg_video_path = Path(item.path)
            elif item.type == "music" and Path(item.path).exists():
                music_path = Path(item.path)
    
    # Create SRT for subtitles
    srt_path = job_dir / "captions" / "captions.srt"
    if not srt_path.exists() and captions:
        from worker.stages.captions import generate_srt
        generate_srt(captions, srt_path)
    
    # Build FFmpeg command
    inputs = []
    filter_complex = []
    
    # Input 0: Color background
    inputs.extend(["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s={width}x{height}:d={duration}"])
    
    # Input 1: Voice audio
    if voice_path.exists():
        inputs.extend(["-i", str(voice_path)])
    else:
        inputs.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration}"])
    
    # Input 2: Background video (if exists)
    if bg_video_path and bg_video_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(bg_video_path)])
        has_bg = True
    else:
        has_bg = False
    
    # Input 3: Music (if exists)
    if music_path and music_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])
        has_music = True
    else:
        has_music = False
    
    # Build filter graph
    filters = []
    
    # Scale and position background video
    if has_bg:
        bg_input = "2:v"
        filters.append(f"[{bg_input}]scale={width}:{top_height}:force_original_aspect_ratio=increase,crop={width}:{top_height},setsar=1[bg_scaled]")
        filters.append(f"[0:v][bg_scaled]overlay=0:{top_height}:shortest=1[with_bg]")
        video_stream = "[with_bg]"
    else:
        video_stream = "[0:v]"
    
    # Add subtitles if available
    if srt_path.exists():
        # Escape path for FFmpeg
        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        subtitle_style = get_subtitle_style(timeline.segments[0].caption_style if timeline.segments else None)
        filters.append(f"{video_stream}subtitles='{srt_escaped}':force_style='{subtitle_style}'[with_subs]")
        video_stream = "[with_subs]"
    
    # Audio mixing
    audio_filters = []
    if voice_path.exists():
        voice_input = "1:a"
    else:
        voice_input = "1:a"
    
    if has_music:
        music_input = "3:a" if has_bg else "2:a"
        # Duck music under voice
        audio_filters.append(f"[{music_input}]volume=0.15[music_quiet]")
        audio_filters.append(f"[{voice_input}][music_quiet]amix=inputs=2:duration=first[audio_out]")
        audio_stream = "[audio_out]"
    else:
        audio_stream = f"[{voice_input}]"
        audio_filters.append(f"{audio_stream}acopy[audio_out]")
        audio_stream = "[audio_out]"
    
    # Combine filters
    all_filters = filters + audio_filters
    filter_complex_str = ";".join(all_filters) if all_filters else None
    
    # Build full command
    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs)
    
    if filter_complex_str:
        cmd.extend(["-filter_complex", filter_complex_str])
        cmd.extend(["-map", video_stream.strip("[]")])
        cmd.extend(["-map", audio_stream.strip("[]")])
    
    # Use configurable FFmpeg preset (veryfast is 20-30% faster than fast)
    ffmpeg_preset = os.getenv("FFMPEG_PRESET", "veryfast")

    cmd.extend([
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", ffmpeg_preset,
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ])
    
    logger.info(f"Running FFmpeg: {' '.join(cmd)}")

    # Stream stderr to log file instead of capturing in memory
    ffmpeg_log = job_dir / "logs" / "ffmpeg_render.log"
    ffmpeg_log.parent.mkdir(parents=True, exist_ok=True)

    with open(ffmpeg_log, "w") as log_file:
        result = subprocess.run(
            cmd,
            stderr=log_file,
            stdout=subprocess.DEVNULL,
            timeout=600
        )

    if result.returncode != 0:
        # Read last 500 chars from log file for error context
        with open(ffmpeg_log, "r") as log_file:
            log_file.seek(0, 2)  # Go to end
            file_size = log_file.tell()
            log_file.seek(max(0, file_size - 500))
            error_tail = log_file.read()

        logger.error(f"FFmpeg error (see {ffmpeg_log})")
        raise RuntimeError(f"FFmpeg failed: {error_tail}")


def render_simple_video(
    job_id: str,
    timeline: TimelinePlan,
    voice_path: Path,
    output_path: Path,
    logger
) -> None:
    """Simple fallback render with just color background and audio."""
    job_dir = get_job_dir(job_id)
    duration = timeline.total_duration_sec
    width, height = 1080, 1920
    
    srt_path = job_dir / "captions" / "captions.srt"
    
    cmd = ["ffmpeg", "-y"]
    
    # Color background
    cmd.extend(["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s={width}x{height}:d={duration}"])
    
    # Audio input
    if voice_path.exists():
        cmd.extend(["-i", str(voice_path)])
        audio_map = ["-map", "0:v", "-map", "1:a"]
    else:
        cmd.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration}"])
        audio_map = ["-map", "0:v", "-map", "1:a"]
    
    # Add subtitles if available
    if srt_path.exists():
        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        cmd.extend(["-vf", f"subtitles='{srt_escaped}'"])
    
    cmd.extend(audio_map)
    cmd.extend([
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ])
    
    logger.info(f"Running simple FFmpeg render")

    # Stream stderr to log file instead of capturing in memory
    ffmpeg_log = job_dir / "logs" / "ffmpeg_simple.log"
    ffmpeg_log.parent.mkdir(parents=True, exist_ok=True)

    with open(ffmpeg_log, "w") as log_file:
        result = subprocess.run(
            cmd,
            stderr=log_file,
            stdout=subprocess.DEVNULL,
            timeout=300
        )

    if result.returncode != 0:
        # Read last 500 chars from log file for error context
        with open(ffmpeg_log, "r") as log_file:
            log_file.seek(0, 2)  # Go to end
            file_size = log_file.tell()
            log_file.seek(max(0, file_size - 500))
            error_tail = log_file.read()

        logger.error(f"Simple render failed (see {ffmpeg_log})")
        raise RuntimeError(f"Simple render failed: {error_tail}")


def get_subtitle_style(caption_style) -> str:
    """Get FFmpeg ASS subtitle style based on caption style."""
    from shared.models import CaptionStyle
    
    if caption_style == CaptionStyle.MINIMAL:
        return "FontName=Arial,FontSize=20,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=1,MarginV=50"
    else:  # BOLD (default)
        return "FontName=Arial,FontSize=28,Bold=1,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,MarginV=60"
