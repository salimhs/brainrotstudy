"""Stage 3: synthesize narration audio and measure per-segment timing.

We synthesize each segment separately so each segment's duration is known
exactly, without needing Whisper for forced alignment.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import wave
from pathlib import Path

from ..config import Settings, get_settings
from ..schemas import NarratedSegment, Script
from ..storage import JobPaths

log = logging.getLogger(__name__)


def narrate(
    script: Script,
    paths: JobPaths,
    *,
    language: str = "en",
    settings: Settings | None = None,
) -> tuple[list[NarratedSegment], Path]:
    """Return per-segment NarratedSegment list + the concatenated voice file."""
    settings = settings or get_settings()
    paths.audio_dir.mkdir(parents=True, exist_ok=True)

    provider = _pick_provider(settings)
    log.info("synthesizing %d segments with %s", len(script.segments), provider)

    segments: list[NarratedSegment] = []
    cursor = 0.0
    segment_files: list[Path] = []
    for idx, seg in enumerate(script.segments):
        out_path = paths.audio_dir / f"seg_{idx:03d}.mp3"
        _synthesize(seg.text, out_path, provider=provider, language=language, settings=settings)
        duration = _duration_seconds(out_path)
        segments.append(
            NarratedSegment(
                text=seg.text,
                emphasis=seg.emphasis,
                visual_query=seg.visual_query,
                audio_path=str(out_path),
                start_sec=cursor,
                end_sec=cursor + duration,
            )
        )
        cursor += duration
        segment_files.append(out_path)

    voice_path = paths.voice_path
    _concat(segment_files, voice_path, settings=settings)
    return segments, voice_path


# ------- Provider selection -----------------------------------------------


def _pick_provider(settings: Settings) -> str:
    if settings.tts_provider != "auto":
        if settings.tts_provider == "elevenlabs" and not settings.elevenlabs_api_key:
            raise RuntimeError("TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is not set.")
        return settings.tts_provider
    if settings.elevenlabs_api_key:
        return "elevenlabs"
    return "gtts"


def _synthesize(
    text: str,
    out_path: Path,
    *,
    provider: str,
    language: str,
    settings: Settings,
) -> None:
    if provider == "elevenlabs":
        _synth_elevenlabs(text, out_path, settings=settings)
        return
    _synth_gtts(text, out_path, language=language)


def _synth_gtts(text: str, out_path: Path, *, language: str) -> None:
    from gtts import gTTS

    gTTS(text=text, lang=language, slow=False).save(str(out_path))


def _synth_elevenlabs(text: str, out_path: Path, *, settings: Settings) -> None:
    import httpx

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key or "",
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.4},
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)


# ------- Duration and concatenation ---------------------------------------


def _duration_seconds(path: Path) -> float:
    """Measure the duration of an audio file with ffprobe, falling back to wave."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())

    # Last-resort: wave stdlib (only works on .wav)
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except wave.Error as e:
        raise RuntimeError(
            f"Cannot measure duration of {path}: ffprobe is not installed "
            "(install ffmpeg) and the file is not a .wav"
        ) from e


def _concat(files: list[Path], out_path: Path, *, settings: Settings) -> None:
    if not files:
        raise RuntimeError("no audio segments to concatenate")
    if len(files) == 1:
        out_path.write_bytes(files[0].read_bytes())
        return
    ffmpeg = shutil.which(settings.ffmpeg_binary) or settings.ffmpeg_binary
    list_file = out_path.with_suffix(".concat.txt")
    list_file.write_text("\n".join(f"file '{f.resolve()}'" for f in files))
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_path),
        ],
        check=True,
    )
    list_file.unlink(missing_ok=True)
