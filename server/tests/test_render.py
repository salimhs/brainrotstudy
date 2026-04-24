"""Renderer unit tests that don't actually shell out to ffmpeg."""

from __future__ import annotations

from pathlib import Path

from brainrotstudy.pipeline.render import (
    _build_command,
    _escape_for_subtitles,
    _format_ts,
    _format_caption_text,
    write_srt,
)
from brainrotstudy.schemas import CaptionStyle, Timeline, TimelineSegment
from brainrotstudy.config import Settings


def _timeline(voice: Path, img: Path) -> Timeline:
    return Timeline(
        width=1080,
        height=1920,
        duration_sec=8.0,
        voice_path=str(voice),
        segments=[
            TimelineSegment(
                text="Hello world this is a test",
                emphasis=["test"],
                start_sec=0.0,
                end_sec=4.0,
                image_path=str(img),
                caption_style=CaptionStyle.KARAOKE,
            ),
            TimelineSegment(
                text="Second segment here",
                emphasis=[],
                start_sec=4.0,
                end_sec=8.0,
                image_path=str(img),
                caption_style=CaptionStyle.KARAOKE,
            ),
        ],
    )


def test_format_ts() -> None:
    assert _format_ts(0) == "00:00:00,000"
    assert _format_ts(61.5) == "00:01:01,500"
    assert _format_ts(3600 + 62 + 0.125) == "01:01:02,125"


def test_format_caption_text_bolds_emphasis() -> None:
    out = _format_caption_text("Hello world this is a test", ["test"])
    assert "{\\b1}test{\\b0}" in out
    assert "\n" in out  # wrapped


def test_write_srt(tmp_path: Path) -> None:
    tl = _timeline(tmp_path / "v.mp3", tmp_path / "i.jpg")
    out = tmp_path / "c.srt"
    write_srt(tl, out)
    content = out.read_text()
    assert "00:00:00,000 --> 00:00:04,000" in content
    assert "Second segment here" in content


def test_build_command_shape(tmp_path: Path) -> None:
    voice = tmp_path / "voice.mp3"
    voice.write_bytes(b"x")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"x")
    tl = _timeline(voice, img)
    srt = tmp_path / "captions.srt"
    write_srt(tl, srt)
    out = tmp_path / "video.mp4"

    cmd = _build_command(
        ffmpeg="/usr/bin/ffmpeg",
        timeline=tl,
        srt_path=srt,
        out_path=out,
        settings=Settings(),
    )
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-filter_complex" in cmd
    assert any("libx264" in part for part in cmd)
    # filter graph should reference each card once, plus the subtitles filter.
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("zoompan") == 2
    assert "subtitles=" in graph


def test_escape_subtitles_path() -> None:
    result = _escape_for_subtitles(Path("/tmp/has:colon/captions.srt"))
    assert result.startswith("'") and result.endswith("'")
    assert "\\:" in result
