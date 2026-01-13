"""Stage 3: Build timeline plan from script."""

import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from shared.models import (
    ScriptPlan, TimelinePlan, TimelineSegment, 
    CaptionStyle, MotionStyle, Preset
)
from shared.utils import (
    get_job_dir, get_job_logger, load_job_metadata,
    estimate_speech_duration, get_wpm_for_preset
)


def run_timeline_stage(job_id: str) -> None:
    """
    Convert ScriptPlan to TimelinePlan with segment timings.
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    metadata = load_job_metadata(job_id)
    
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    # Check for idempotency
    timeline_json_path = job_dir / "render" / "timeline.json"
    if timeline_json_path.exists():
        logger.info("CACHE HIT: timeline.json already exists, skipping")
        return
    
    # Load script
    script_path = job_dir / "llm" / "script.json"
    if not script_path.exists():
        raise ValueError("script.json not found - script stage must run first")
    
    with open(script_path, "r") as f:
        script = ScriptPlan.model_validate(json.load(f))
    
    # Build timeline
    timeline = build_timeline(script, metadata.options, logger)
    
    # Save timeline
    timeline_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(timeline_json_path, "w") as f:
        json.dump(timeline.model_dump(), f, indent=2)
    
    logger.info(f"Built timeline with {len(timeline.segments)} segments, "
                f"total duration: {timeline.total_duration_sec:.1f}s")


def build_timeline(script: ScriptPlan, options, logger) -> TimelinePlan:
    """Convert script lines to timeline segments."""
    segments = []
    current_time = 0.0
    target_duration = options.length_sec
    
    # Get preset-specific parameters
    preset = script.style_preset
    wpm = get_wpm_for_preset(preset.value)
    
    # Motion styles based on preset
    motion_styles = get_motion_styles_for_preset(preset)
    
    for i, line in enumerate(script.script_lines):
        # Calculate duration based on word count
        duration = estimate_speech_duration(line.line, wpm)
        duration = max(duration, 2.0)  # Minimum 2 seconds per segment
        
        # Don't exceed target duration
        if current_time + duration > target_duration:
            duration = target_duration - current_time
            if duration < 1.0:
                break
        
        # Find visual cue for this time
        visual_asset = None
        slide_frame = None
        
        for cue in script.visual_cues:
            if current_time <= cue.t < current_time + duration:
                # Will be resolved in assets stage
                visual_asset = f"assets/cue_{cue.t:.0f}.png"
                break
        
        # Check for slide reference
        if line.source_slide_indices:
            slide_frame = line.source_slide_indices[0]
        
        segment = TimelineSegment(
            index=i,
            start_sec=current_time,
            end_sec=current_time + duration,
            narration_text=line.line,
            emphasis_words=line.emphasis,
            visual_asset_path=visual_asset,
            slide_frame_index=slide_frame,
            caption_style=options.caption_style,
            motion_style=motion_styles[i % len(motion_styles)],
        )
        segments.append(segment)
        current_time += duration
    
    # Ensure we reach target duration
    if segments and current_time < target_duration - 1:
        # Extend last segment
        segments[-1].end_sec = target_duration
    
    return TimelinePlan(
        segments=segments,
        total_duration_sec=segments[-1].end_sec if segments else target_duration,
    )


def get_motion_styles_for_preset(preset: Preset) -> list[MotionStyle]:
    """Get motion style rotation based on preset."""
    if preset == Preset.FAST:
        return [
            MotionStyle.ZOOM_IN,
            MotionStyle.PAN_SLOW,
            MotionStyle.ZOOM_OUT,
            MotionStyle.STATIC,
        ]
    elif preset == Preset.EXAM:
        return [
            MotionStyle.STATIC,
            MotionStyle.STATIC,
            MotionStyle.PAN_SLOW,
        ]
    else:  # BALANCED
        return [
            MotionStyle.PAN_SLOW,
            MotionStyle.STATIC,
            MotionStyle.ZOOM_IN,
            MotionStyle.STATIC,
        ]
