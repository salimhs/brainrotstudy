"""Stage 4: Fetch assets from Openverse and fallbacks."""

import json
import os
import sys
import uuid
import hashlib
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/app")

from shared.models import (
    ScriptPlan, AssetsManifest, AssetItem, SlidesExtracted
)
from shared.utils import get_job_dir, get_job_logger

# Module-level HTTP session for connection pooling
_http_session = None


def _get_session():
    """Get or create a reusable HTTP session with connection pooling."""
    global _http_session
    if _http_session is None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        _http_session = requests.Session()
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


def run_assets_stage(job_id: str) -> None:
    """
    Fetch visual assets for the video.
    
    Priority:
    1. Openverse/Wikimedia for CC images
    2. Slide screenshots from extracted content
    3. Generated title cards
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    
    # Check for idempotency
    manifest_path = job_dir / "assets" / "assets_manifest.json"
    if manifest_path.exists():
        logger.info("CACHE HIT: assets_manifest.json already exists, skipping")
        return
    
    # Load script for visual cues
    script_path = job_dir / "llm" / "script.json"
    script = None
    if script_path.exists():
        with open(script_path, "r") as f:
            script = ScriptPlan.model_validate(json.load(f))
    
    # Load extracted slides for fallback
    slides_path = job_dir / "extracted" / "slides.json"
    slides = None
    if slides_path.exists():
        with open(slides_path, "r") as f:
            slides = SlidesExtracted.model_validate(json.load(f))
    
    assets_dir = job_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    manifest = AssetsManifest(items=[])
    
    # Process visual cues in parallel for faster fetching
    if script and script.visual_cues:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(
                    fetch_asset_for_cue, job_id, cue.query, cue.t, slides, assets_dir, logger
                ): cue for cue in script.visual_cues
            }
            for future in as_completed(futures):
                try:
                    asset = future.result()
                    if asset:
                        manifest.items.append(asset)
                except Exception as e:
                    logger.warning(f"Asset fetch failed: {e}")
    
    # Add background video selection
    bg_asset = select_background_video(job_id, script, logger)
    if bg_asset:
        manifest.items.append(bg_asset)
    
    # Add music selection
    music_asset = select_music(job_id, script, logger)
    if music_asset:
        manifest.items.append(music_asset)
    
    # Save manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest.model_dump(), f, indent=2)
    
    logger.info(f"Fetched {len(manifest.items)} assets")


def fetch_asset_for_cue(
    job_id: str,
    query: str,
    time: float,
    slides: Optional[SlidesExtracted],
    assets_dir: Path,
    logger
) -> Optional[AssetItem]:
    """Fetch a single asset for a visual cue."""
    asset_id = f"cue_{time:.0f}"
    asset_path = assets_dir / f"{asset_id}.png"
    
    # Try Openverse first
    openverse_asset = try_openverse(query, asset_path, logger)
    if openverse_asset:
        openverse_asset.id = asset_id
        return openverse_asset
    
    # Fallback to slide screenshot
    if slides and slides.slides:
        slide = slides.slides[0]  # Use first available slide
        if slide.rendered_image:
            job_dir = get_job_dir(job_id)
            slide_path = job_dir / slide.rendered_image
            if slide_path.exists():
                import shutil
                shutil.copy(slide_path, asset_path)
                logger.info(f"Using slide screenshot for cue at t={time}")
                return AssetItem(
                    id=asset_id,
                    type="image",
                    path=f"assets/{asset_id}.png",
                    title="Slide screenshot",
                    license="Original content",
                )
    
    # Last resort: generate title card
    title_card = generate_title_card(query, asset_path, logger)
    if title_card:
        title_card.id = asset_id
        return title_card
    
    return None


def try_openverse(query: str, save_path: Path, logger) -> Optional[AssetItem]:
    """Try to fetch an image from Openverse API."""
    try:
        session = _get_session()

        # Openverse API
        api_url = "https://api.openverse.org/v1/images/"
        params = {
            "q": query,
            "license_type": "all-cc",
            "page_size": 1,
        }

        headers = {}
        openverse_token = os.getenv("OPENVERSE_API_TOKEN")
        if openverse_token:
            headers["Authorization"] = f"Bearer {openverse_token}"

        response = session.get(api_url, params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("results"):
                result = data["results"][0]
                image_url = result.get("url")

                if image_url:
                    # Download image using pooled session
                    img_response = session.get(image_url, timeout=15)
                    if img_response.status_code == 200:
                        with open(save_path, "wb") as f:
                            f.write(img_response.content)

                        logger.info(f"Downloaded image from Openverse: {query}")

                        return AssetItem(
                            id="",
                            type="image",
                            path=f"assets/{save_path.name}",
                            source_url=result.get("url", ""),
                            title=result.get("title", ""),
                            author=result.get("creator", "Unknown"),
                            license=result.get("license", "CC"),
                            attribution=f"{result.get('title', '')} by {result.get('creator', 'Unknown')} ({result.get('license', 'CC')})",
                        )

    except Exception as e:
        logger.debug(f"Openverse fetch failed: {e}")
    
    # Try Pexels as fallback
    pexels_asset = try_pexels(query, save_path, logger)
    if pexels_asset:
        return pexels_asset
    
    return None


def try_pexels(query: str, save_path: Path, logger) -> Optional[AssetItem]:
    """Try to fetch an image from Pexels API."""
    pexels_key = os.getenv("PEXELS_API_KEY")
    if not pexels_key:
        return None

    try:
        session = _get_session()

        # Pexels API
        api_url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": pexels_key}
        params = {
            "query": query,
            "per_page": 1,
            "orientation": "portrait",  # Better for vertical videos
        }

        response = session.get(api_url, headers=headers, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("photos"):
                photo = data["photos"][0]
                image_url = photo["src"]["large"]  # Use large size

                # Download image using pooled session
                img_response = session.get(image_url, timeout=15)
                if img_response.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(img_response.content)

                    logger.info(f"Downloaded image from Pexels: {query}")

                    return AssetItem(
                        id="",
                        type="image",
                        path=f"assets/{save_path.name}",
                        source_url=photo["url"],
                        title=photo.get("alt", query),
                        author=photo["photographer"],
                        license="Pexels License",
                        attribution=f"Photo by {photo['photographer']} on Pexels",
                    )

    except Exception as e:
        logger.debug(f"Pexels fetch failed: {e}")

    return None


def generate_title_card(text: str, save_path: Path, logger) -> Optional[AssetItem]:
    """Generate a simple title card image as fallback."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        # Create gradient background
        width, height = 1080, 960  # Top half of vertical video

        # Optimized gradient using numpy (vectorized, ~100x faster than pixel loop)
        y_indices = np.linspace(0, 1, height).reshape(height, 1)
        r = (30 + y_indices * 20).astype(np.uint8)
        g = (30 + y_indices * 30).astype(np.uint8)
        b = (60 + y_indices * 40).astype(np.uint8)

        # Broadcast to full width and stack RGB channels
        gradient = np.zeros((height, width, 3), dtype=np.uint8)
        gradient[:, :, 0] = np.broadcast_to(r, (height, width))
        gradient[:, :, 1] = np.broadcast_to(g, (height, width))
        gradient[:, :, 2] = np.broadcast_to(b, (height, width))

        img = Image.fromarray(gradient, 'RGB')
        
        draw = ImageDraw.Draw(img)
        
        # Try to use a nice font, fallback to default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        except (OSError, IOError):
            font = ImageFont.load_default()
        
        # Wrap text
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            current_line.append(word)
            line = " ".join(current_line)
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
            except AttributeError:
                line_width = len(line) * 25
            
            if line_width > width - 100:
                if len(current_line) > 1:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(line)
                    current_line = []
        
        if current_line:
            lines.append(" ".join(current_line))
        
        # Draw centered text
        y_offset = height // 2 - len(lines) * 30
        for line in lines[:4]:  # Max 4 lines
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
            except AttributeError:
                line_width = len(line) * 25
            x = (width - line_width) // 2
            draw.text((x, y_offset), line, fill=(255, 255, 255), font=font)
            y_offset += 60
        
        img.save(save_path)
        logger.info(f"Generated title card: {text[:30]}...")
        
        return AssetItem(
            id="",
            type="image",
            path=f"assets/{save_path.name}",
            title="Generated title card",
            license="Generated",
        )
        
    except ImportError:
        logger.warning("Pillow not installed, cannot generate title card")
    except Exception as e:
        logger.error(f"Title card generation failed: {e}")
    
    return None


def select_background_video(job_id: str, script: Optional[ScriptPlan], logger) -> Optional[AssetItem]:
    """Select a background video loop based on preset."""
    # Check for bundled background loops
    bg_loops_dir = Path("/app/assets/bg_loops")
    
    if not bg_loops_dir.exists():
        logger.info("No background loops directory found")
        return None
    
    loops = list(bg_loops_dir.glob("*.mp4"))
    if not loops:
        logger.info("No background loops found")
        return None
    
    # Select based on preset
    preset = script.style_preset.value if script else "BALANCED"
    
    # For now, just use the first available loop
    selected = loops[0]
    
    return AssetItem(
        id="bg_video",
        type="bg_video",
        path=str(selected),
        title=selected.stem,
        license="Bundled asset",
    )


def select_music(job_id: str, script: Optional[ScriptPlan], logger) -> Optional[AssetItem]:
    """Select background music based on preset."""
    music_dir = Path("/app/assets/music")
    
    if not music_dir.exists():
        logger.info("No music directory found")
        return None
    
    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))
    if not tracks:
        logger.info("No music tracks found")
        return None
    
    # For now, just use the first available track
    selected = tracks[0]
    
    return AssetItem(
        id="music",
        type="music",
        path=str(selected),
        title=selected.stem,
        license="Bundled asset",
    )
