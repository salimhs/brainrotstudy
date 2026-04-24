"""Stage 4: fetch a stock image for each narrated segment.

Tries Pexels first (best quality, high rate limits), then falls back to
Openverse (CC-licensed, no API key). If neither is reachable we draw a
title-card image so the pipeline still completes.
"""

from __future__ import annotations

import hashlib
import logging
import random
import textwrap
from pathlib import Path

import httpx

from ..config import Settings, get_settings
from ..schemas import NarratedSegment, VisualClip

log = logging.getLogger(__name__)


PALETTE = [
    ((26, 26, 46), (42, 37, 85)),     # midnight
    ((236, 72, 153), (139, 92, 246)), # pink→violet
    ((14, 165, 233), (16, 185, 129)), # sky→emerald
    ((249, 115, 22), (234, 88, 12)),  # orange flame
    ((124, 58, 237), (59, 130, 246)), # violet→blue
]


def fetch_visuals(
    segments: list[NarratedSegment],
    out_dir: Path,
    *,
    title: str,
    settings: Settings | None = None,
    http_client: httpx.Client | None = None,
) -> list[VisualClip]:
    """Return one VisualClip per segment (path is a local image file)."""
    settings = settings or get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=20.0, follow_redirects=True)

    clips: list[VisualClip] = []
    try:
        for idx, seg in enumerate(segments):
            query = seg.visual_query or seg.text.split(".")[0]
            target = out_dir / f"seg_{idx:03d}.jpg"
            clip = _try_pexels(query, target, client=client, api_key=settings.pexels_api_key)
            if clip is None:
                clip = _try_openverse(query, target, client=client)
            if clip is None:
                log.info("no stock image for %r, rendering a title card", query)
                clip = _render_card(
                    text=seg.text,
                    title=title,
                    idx=idx,
                    target=target.with_suffix(".png"),
                )
            clips.append(clip)
    finally:
        if owns_client:
            client.close()
    return clips


# ------- Pexels -----------------------------------------------------------


def _try_pexels(
    query: str, target: Path, *, client: httpx.Client, api_key: str | None
) -> VisualClip | None:
    if not api_key:
        return None
    try:
        resp = client.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "orientation": "portrait", "per_page": 5},
            headers={"Authorization": api_key},
        )
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        if not photos:
            return None
        photo = random.choice(photos)
        src = photo.get("src", {})
        image_url = src.get("portrait") or src.get("large") or src.get("original")
        if not image_url:
            return None
        _download(image_url, target, client=client)
        return VisualClip(
            path=str(target),
            source="pexels",
            attribution=f"Photo by {photo.get('photographer', 'Pexels')} on Pexels",
        )
    except Exception as e:
        log.warning("pexels fetch failed for %r: %s", query, e)
        return None


# ------- Openverse --------------------------------------------------------


def _try_openverse(query: str, target: Path, *, client: httpx.Client) -> VisualClip | None:
    try:
        resp = client.get(
            "https://api.openverse.org/v1/images/",
            params={
                "q": query,
                "license_type": "commercial",
                "page_size": 5,
                "aspect_ratio": "tall",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None
        photo = random.choice(results)
        image_url = photo.get("url")
        if not image_url:
            return None
        _download(image_url, target, client=client)
        return VisualClip(
            path=str(target),
            source="openverse",
            attribution=f"{photo.get('title', 'Image')} by {photo.get('creator', 'Openverse')} "
            f"({photo.get('license', 'CC')})",
        )
    except Exception as e:
        log.warning("openverse fetch failed for %r: %s", query, e)
        return None


def _download(url: str, target: Path, *, client: httpx.Client) -> None:
    resp = client.get(url)
    resp.raise_for_status()
    target.write_bytes(resp.content)


# ------- Title-card fallback ---------------------------------------------


def _render_card(*, text: str, title: str, idx: int, target: Path) -> VisualClip:
    """Draw a branded gradient card with the segment text."""
    from PIL import Image, ImageDraw

    W, H = 1080, 1080
    # deterministic palette per segment
    seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    top, bottom = PALETTE[seed % len(PALETTE)]

    img = Image.new("RGB", (W, H), top)
    for y in range(H):
        t = y / (H - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=(r, g, b))

    draw = ImageDraw.Draw(img)
    font_main = _load_font(72)
    font_title = _load_font(36)

    draw.text((60, 60), title.upper()[:40], font=font_title, fill=(255, 255, 255, 200))

    wrapped = textwrap.fill(text, width=18)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font_main)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.multiline_text(
        ((W - tw) / 2, (H - th) / 2),
        wrapped,
        font=font_main,
        fill="white",
        align="center",
        spacing=12,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target, format="PNG")
    return VisualClip(path=str(target), source="generated", attribution="")


def _load_font(size: int):
    from PIL import ImageFont

    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()
