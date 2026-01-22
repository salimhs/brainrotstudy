"""Stage 5: Generate voice narration using TTS."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from shared.models import ScriptPlan, TimelinePlan
from shared.utils import get_job_dir, get_job_logger, load_job_metadata


def run_voice_stage(job_id: str) -> None:
    """
    Generate voice narration from script.
    
    Priority:
    1. ElevenLabs API if key is available
    2. Local Piper TTS
    3. Google TTS (gTTS) as last resort
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    metadata = load_job_metadata(job_id)
    
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    # Check for idempotency
    voice_path = job_dir / "audio" / "voice.wav"
    if voice_path.exists() and voice_path.stat().st_size > 0:
        logger.info("CACHE HIT: voice.wav already exists, skipping")
        return
    
    # Load script for narration text
    script_path = job_dir / "llm" / "script.json"
    if not script_path.exists():
        raise ValueError("script.json not found")
    
    with open(script_path, "r") as f:
        script = ScriptPlan.model_validate(json.load(f))
    
    # Build full narration text
    narration_parts = []
    for line in script.script_lines:
        narration_parts.append(line.line)
    
    narration_text = " ".join(narration_parts)
    
    # Ensure audio directory exists
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    # Try TTS providers in order
    success = False
    
    if os.getenv("ELEVENLABS_API_KEY"):
        success = try_elevenlabs(narration_text, voice_path, metadata.options.voice_id, logger)
    
    if not success:
        success = try_piper(narration_text, voice_path, logger)
    
    if not success:
        success = try_gtts(narration_text, voice_path, logger)
    
    if not success:
        # Create silent audio as absolute fallback
        create_silent_audio(voice_path, 60, logger)
        logger.warning("All TTS providers failed, using silent audio")
    else:
        logger.info("Voice generation completed")


def try_elevenlabs(text: str, output_path: Path, voice_id: str, logger) -> bool:
    """Try ElevenLabs TTS API."""
    try:
        import requests
        
        api_key = os.getenv("ELEVENLABS_API_KEY")
        voice = voice_id if voice_id != "default" else "21m00Tcm4TlvDq8ikWAM"  # Rachel
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5,
            }
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=60)
        
        if response.status_code == 200:
            # Save as MP3 first, then convert to WAV
            mp3_path = output_path.with_suffix(".mp3")
            with open(mp3_path, "wb") as f:
                f.write(response.content)
            
            # Convert to WAV using FFmpeg
            convert_to_wav(mp3_path, output_path, logger)
            mp3_path.unlink()  # Clean up MP3
            
            logger.info("Generated voice using ElevenLabs")
            return True
        else:
            logger.error(f"ElevenLabs API error: {response.status_code}")
            
    except Exception as e:
        logger.error(f"ElevenLabs TTS failed: {e}")
    
    return False


def try_piper(text: str, output_path: Path, logger) -> bool:
    """Try local Piper TTS."""
    try:
        import subprocess
        
        # Check if piper is available
        result = subprocess.run(["which", "piper"], capture_output=True)
        if result.returncode != 0:
            logger.debug("Piper not installed")
            return False
        
        # Write text to temp file
        temp_text = output_path.parent / "temp_text.txt"
        with open(temp_text, "w") as f:
            f.write(text)
        
        # Run piper with proper file handle management
        model = os.getenv("PIPER_MODEL", "en_US-lessac-medium")
        with open(temp_text, "r") as stdin_file:
            result = subprocess.run(
                ["piper", "--model", model, "--output_file", str(output_path)],
                stdin=stdin_file,
                capture_output=True,
                timeout=120,
            )
        
        temp_text.unlink()
        
        if result.returncode == 0 and output_path.exists():
            logger.info("Generated voice using Piper")
            return True
        else:
            logger.error(f"Piper failed: {result.stderr.decode()}")
            
    except Exception as e:
        logger.error(f"Piper TTS failed: {e}")
    
    return False


def try_gtts(text: str, output_path: Path, logger) -> bool:
    """Try Google Text-to-Speech (gTTS)."""
    try:
        from gtts import gTTS
        
        # gTTS outputs MP3
        mp3_path = output_path.with_suffix(".mp3")
        
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(str(mp3_path))
        
        # Convert to WAV
        convert_to_wav(mp3_path, output_path, logger)
        mp3_path.unlink()
        
        logger.info("Generated voice using gTTS")
        return True
        
    except ImportError:
        logger.debug("gTTS not installed")
    except Exception as e:
        logger.error(f"gTTS failed: {e}")
    
    return False


def convert_to_wav(input_path: Path, output_path: Path, logger) -> bool:
    """Convert audio file to WAV using FFmpeg."""
    try:
        import subprocess

        # Stream stderr to avoid memory usage
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "1",
            str(output_path)
        ], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, timeout=60, text=True)

        if result.returncode == 0:
            return True
        else:
            logger.error(f"FFmpeg conversion failed: {result.stderr[:500]}")

    except Exception as e:
        logger.error(f"Audio conversion failed: {e}")

    return False


def create_silent_audio(output_path: Path, duration_sec: int, logger) -> bool:
    """Create silent audio file as fallback."""
    try:
        import subprocess

        # Stream stderr to avoid memory usage
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration_sec),
            "-acodec", "pcm_s16le",
            str(output_path)
        ], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, timeout=30, text=True)

        if result.returncode == 0:
            logger.info(f"Created silent audio: {duration_sec}s")
            return True

    except Exception as e:
        logger.error(f"Silent audio creation failed: {e}")

    return False
