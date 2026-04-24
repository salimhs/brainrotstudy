"""Visuals tests — stub out HTTP so we can verify provider logic."""

from __future__ import annotations

from pathlib import Path

import httpx

from brainrotstudy.config import Settings
from brainrotstudy.pipeline.visuals import fetch_visuals
from brainrotstudy.schemas import NarratedSegment


def _seg(idx: int, query: str = "") -> NarratedSegment:
    return NarratedSegment(
        text=f"line {idx}",
        emphasis=[],
        visual_query=query,
        audio_path="x",
        start_sec=float(idx),
        end_sec=float(idx) + 1,
    )


def test_fetch_visuals_uses_pexels(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "pexels" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "photos": [
                        {
                            "photographer": "Ada",
                            "src": {"portrait": "https://example.com/p.jpg"},
                        }
                    ]
                },
            )
        if request.url.host == "example.com":
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\n")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = Settings(pexels_api_key="abc")
    client = httpx.Client(transport=transport)

    clips = fetch_visuals(
        [_seg(0, "cells")], tmp_path, title="Cells", settings=settings, http_client=client
    )
    assert len(clips) == 1
    assert clips[0].source == "pexels"
    assert Path(clips[0].path).exists()
    assert "Ada" in clips[0].attribution


def test_fetch_visuals_falls_back_to_title_card(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    settings = Settings()
    client = httpx.Client(transport=transport)

    clips = fetch_visuals(
        [_seg(0, "cells")], tmp_path, title="Cells", settings=settings, http_client=client
    )
    assert clips[0].source == "generated"
    assert Path(clips[0].path).exists()
    assert Path(clips[0].path).stat().st_size > 1000  # real PNG
