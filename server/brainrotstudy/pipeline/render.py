"""Stage 5: compose the final vertical video with FFmpeg.

Design:
- 1080x1920 vertical, 30 fps.
- Animated gradient background fills the frame (rotating hue wash).
- Each segment's visual is center-cropped to a 1080x960 card with a slow
  Ken Burns zoom; cards cross-fade between segments.
- Captions burn in via the subtitles filter using a per-segment SRT that we
  generate here (karaoke-ish by pulsing the active line).
- Voice audio is mapped on top of a silent-safe fallback.

This module produces the final MP4. It requires `ffmpeg` to be on PATH.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from ..config import Settings, get_settings
from ..schemas import CaptionStyle, Timeline
from ..storage import JobPaths

log = logging.getLogger(__name__)


def render_video(timeline: Timeline, paths: JobPaths, *, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    ffmpeg = shutil.which(settings.ffmpeg_binary) or settings.ffmpeg_binary
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    srt_path = paths.srt_path
    write_srt(timeline, srt_path)

    cmd = _build_command(
        ffmpeg=ffmpeg,
        timeline=timeline,
        srt_path=srt_path,
        out_path=paths.video_path,
        settings=settings,
    )
    log.info("ffmpeg command: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return paths.video_path


# -------- Command construction --------------------------------------------


def _build_command(
    *,
    ffmpeg: str,
    timeline: Timeline,
    srt_path: Path,
    out_path: Path,
    settings: Settings,
) -> list[str]:
    """Return the full ffmpeg argv."""
    W, H = timeline.width, timeline.height
    duration = max(1.0, timeline.duration_sec)
    top_h = int(H * 0.54)  # image fills top 54%
    cards = [seg for seg in timeline.segments if seg.image_path]

    inputs: list[str] = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:d={duration}:r=30"]
    inputs += ["-i", timeline.voice_path]
    for seg in cards:
        inputs += ["-loop", "1", "-i", seg.image_path or ""]

    # Animated background: scrolling gradient via hue rotation
    filters: list[str] = []
    filters.append(
        f"color=c=0x1a1a2e:s={W}x{H}:d={duration}:r=30[bgbase];"
        f"[bgbase]format=yuv420p,hue=h='10*t':s=1[bg]"
    )

    # Per-card: scale/crop to top strip, fade in/out, Ken Burns via zoompan
    card_labels: list[str] = []
    for i, seg in enumerate(cards):
        dur = max(0.2, seg.end_sec - seg.start_sec)
        fade_dur = min(0.35, dur / 3)
        # Input index: lavfi(0) + voice(1) + first card(2)
        src = f"{2 + i}:v"
        frames = max(1, int(dur * 30))
        filters.append(
            f"[{src}]"
            f"scale={W * 2}:-1,"
            f"zoompan=z='min(zoom+0.0012,1.2)':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':"
            f"d={frames}:s={W}x{top_h}:fps=30,"
            f"format=yuva420p,"
            f"fade=t=in:st=0:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={dur - fade_dur:.3f}:d={fade_dur}:alpha=1,"
            f"setpts=PTS-STARTPTS+{seg.start_sec:.3f}/TB"
            f"[card{i}]"
        )
        card_labels.append(f"[card{i}]")

    # Overlay cards onto the animated bg
    prev = "[bg]"
    card_top = int(H * 0.08)
    for i, label in enumerate(card_labels):
        seg = cards[i]
        out = f"[ov{i}]"
        filters.append(
            f"{prev}{label}overlay=0:{card_top}:"
            f"enable='between(t,{seg.start_sec:.3f},{seg.end_sec:.3f})'{out}"
        )
        prev = out

    # Burn subtitles
    style = _subtitle_style(timeline.segments[0].caption_style if timeline.segments else CaptionStyle.KARAOKE)
    srt_escaped = _escape_for_subtitles(srt_path)
    filters.append(f"{prev}subtitles=filename={srt_escaped}:force_style='{style}'[vout]")

    filter_graph = ";".join(filters)

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        filter_graph,
        "-map",
        "[vout]",
        "-map",
        "1:a",
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        settings.ffmpeg_preset,
        "-crf",
        str(settings.ffmpeg_crf),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    return cmd


def _subtitle_style(style: CaptionStyle) -> str:
    if style == CaptionStyle.MINIMAL:
        return (
            "FontName=DejaVu Sans,FontSize=20,PrimaryColour=&HFFFFFFFF,"
            "OutlineColour=&H80000000,BorderStyle=1,Outline=1,Shadow=0,"
            "Alignment=2,MarginV=180"
        )
    if style == CaptionStyle.POP:
        return (
            "FontName=DejaVu Sans,FontSize=34,Bold=1,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&HFF000000,BorderStyle=1,Outline=3,Shadow=0,"
            "Alignment=2,MarginV=220,Spacing=1"
        )
    # KARAOKE
    return (
        "FontName=DejaVu Sans,FontSize=38,Bold=1,PrimaryColour=&H00FFFFFF,"
        "SecondaryColour=&H00F1C40F,OutlineColour=&HFF000000,"
        "BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=240,Spacing=2"
    )


def _escape_for_subtitles(path: Path) -> str:
    """Escape a filesystem path for ffmpeg's subtitles filter."""
    raw = str(path.resolve())
    # Escape colons and commas per filter-escaping rules, then single-quote.
    raw = raw.replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'")
    return f"'{raw}'"


# -------- SRT writer ------------------------------------------------------


def write_srt(timeline: Timeline, out_path: Path) -> None:
    """Write per-segment SRT captions. Each segment gets ONE cue with the full line."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for idx, seg in enumerate(timeline.segments, 1):
        lines.append(str(idx))
        lines.append(f"{_format_ts(seg.start_sec)} --> {_format_ts(seg.end_sec)}")
        lines.append(_format_caption_text(seg.text, seg.emphasis))
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _format_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ss += 1
        ms = 0
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _format_caption_text(text: str, emphasis: list[str]) -> str:
    """Wrap to ~2 lines and bold emphasis words (ASS override tags)."""
    max_line = 22
    words = text.split()
    out: list[str] = []
    line: list[str] = []
    for word in words:
        prospective = " ".join(line + [word])
        if line and len(prospective) > max_line and len(out) < 1:
            out.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        out.append(" ".join(line))
    result = "\n".join(out)
    # Bold emphasis words via ASS tags
    for word in sorted(set(emphasis), key=len, reverse=True):
        if not word.strip():
            continue
        result = _replace_word_case_insensitive(result, word, lambda w: f"{{\\b1}}{w}{{\\b0}}")
    return result


def _replace_word_case_insensitive(text: str, word: str, wrap) -> str:
    import re

    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    return pattern.sub(lambda m: wrap(m.group(0)), text)
