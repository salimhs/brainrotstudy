"""Stage 6: Generate word-level captions."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/app")

from shared.models import (
    CaptionsWordLevel, WordTiming, LineTiming, TimelinePlan
)
from shared.utils import get_job_dir, get_job_logger


def run_captions_stage(job_id: str) -> None:
    """
    Generate captions with timing information.
    
    Priority:
    1. WhisperX for word-level timestamps
    2. Whisper for word-level timestamps
    3. Segment-level fallback from timeline
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    
    # Check for idempotency
    captions_path = job_dir / "captions" / "captions.json"
    if captions_path.exists():
        logger.info("CACHE HIT: captions.json already exists, skipping")
        return
    
    # Load voice audio
    voice_path = job_dir / "audio" / "voice.wav"
    if not voice_path.exists():
        raise ValueError("voice.wav not found")
    
    # Load timeline for fallback
    timeline_path = job_dir / "render" / "timeline.json"
    timeline = None
    if timeline_path.exists():
        with open(timeline_path, "r") as f:
            timeline = TimelinePlan.model_validate(json.load(f))
    
    captions_dir = job_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    
    # Try transcription methods
    captions = None
    
    captions = try_whisperx(voice_path, logger)
    
    if not captions:
        captions = try_whisper(voice_path, logger)
    
    if not captions:
        captions = create_fallback_captions(timeline, logger)
    
    # Save captions
    with open(captions_path, "w") as f:
        json.dump(captions.model_dump(), f, indent=2)
    
    # Also generate SRT file
    srt_path = job_dir / "captions" / "captions.srt"
    generate_srt(captions, srt_path)
    
    logger.info(f"Generated captions: {len(captions.words)} words, {len(captions.lines)} lines")


def try_whisperx(audio_path: Path, logger) -> Optional[CaptionsWordLevel]:
    """Try WhisperX for word-level transcription."""
    try:
        import whisperx
        import torch
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        # Load model
        model = whisperx.load_model(
            os.getenv("WHISPERX_MODEL", "base"),
            device,
            compute_type=compute_type
        )
        
        # Transcribe
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio, batch_size=16)
        
        # Align
        model_a, metadata = whisperx.load_align_model(
            language_code="en", 
            device=device
        )
        result = whisperx.align(
            result["segments"], 
            model_a, 
            metadata, 
            audio, 
            device
        )
        
        # Extract word-level timings
        words = []
        for segment in result.get("segments", []):
            for word in segment.get("words", []):
                words.append(WordTiming(
                    text=word.get("word", ""),
                    start=word.get("start", 0),
                    end=word.get("end", 0),
                ))
        
        # Build line-level from segments
        lines = []
        for segment in result.get("segments", []):
            lines.append(LineTiming(
                text=segment.get("text", "").strip(),
                start=segment.get("start", 0),
                end=segment.get("end", 0),
            ))
        
        logger.info("Generated word-level captions using WhisperX")
        return CaptionsWordLevel(words=words, lines=lines)
        
    except ImportError:
        logger.debug("WhisperX not installed")
    except Exception as e:
        logger.error(f"WhisperX failed: {e}")
    
    return None


def try_whisper(audio_path: Path, logger) -> Optional[CaptionsWordLevel]:
    """Try OpenAI Whisper for transcription."""
    try:
        import whisper
        
        model = whisper.load_model(os.getenv("WHISPER_MODEL", "base"))
        result = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            language="en",
        )
        
        words = []
        lines = []
        
        for segment in result.get("segments", []):
            # Line-level
            lines.append(LineTiming(
                text=segment.get("text", "").strip(),
                start=segment.get("start", 0),
                end=segment.get("end", 0),
            ))
            
            # Word-level if available
            for word in segment.get("words", []):
                words.append(WordTiming(
                    text=word.get("word", ""),
                    start=word.get("start", 0),
                    end=word.get("end", 0),
                ))
        
        # If no word-level, approximate from segments
        if not words and lines:
            for line in lines:
                word_list = line.text.split()
                if word_list:
                    duration_per_word = (line.end - line.start) / len(word_list)
                    current_time = line.start
                    for word_text in word_list:
                        words.append(WordTiming(
                            text=word_text,
                            start=current_time,
                            end=current_time + duration_per_word,
                        ))
                        current_time += duration_per_word
        
        logger.info("Generated captions using Whisper")
        return CaptionsWordLevel(words=words, lines=lines)
        
    except ImportError:
        logger.debug("Whisper not installed")
    except Exception as e:
        logger.error(f"Whisper failed: {e}")
    
    return None


def create_fallback_captions(timeline: Optional[TimelinePlan], logger) -> CaptionsWordLevel:
    """Create segment-level captions from timeline as fallback."""
    words = []
    lines = []
    
    if timeline:
        for segment in timeline.segments:
            # Add line-level
            lines.append(LineTiming(
                text=segment.narration_text,
                start=segment.start_sec,
                end=segment.end_sec,
            ))
            
            # Approximate word-level
            word_list = segment.narration_text.split()
            if word_list:
                duration = segment.end_sec - segment.start_sec
                duration_per_word = duration / len(word_list)
                current_time = segment.start_sec
                
                for word_text in word_list:
                    words.append(WordTiming(
                        text=word_text,
                        start=current_time,
                        end=current_time + duration_per_word,
                    ))
                    current_time += duration_per_word
    
    logger.info("Created fallback segment-level captions")
    return CaptionsWordLevel(words=words, lines=lines)


def generate_srt(captions: CaptionsWordLevel, output_path: Path) -> None:
    """Generate SRT subtitle file from captions."""
    def format_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    srt_content = []
    
    for i, line in enumerate(captions.lines, start=1):
        start = format_timestamp(line.start)
        end = format_timestamp(line.end)
        srt_content.append(f"{i}")
        srt_content.append(f"{start} --> {end}")
        srt_content.append(line.text)
        srt_content.append("")
    
    with open(output_path, "w") as f:
        f.write("\n".join(srt_content))
