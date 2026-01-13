"""Stage 1: Extract content from PDF/PPTX files."""

import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from shared.models import SlidesExtracted, SlideData
from shared.utils import get_job_dir, get_job_logger, load_job_metadata, artifact_exists


def run_extract_stage(job_id: str) -> None:
    """
    Extract text and images from uploaded PDF/PPTX files.
    
    For topic-only jobs, this stage is skipped.
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    metadata = load_job_metadata(job_id)
    
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    # Check for idempotency
    slides_json_path = job_dir / "extracted" / "slides.json"
    if slides_json_path.exists():
        logger.info("CACHE HIT: slides.json already exists, skipping extraction")
        return
    
    # For topic-only jobs, create empty slides structure
    if metadata.input_type == "topic":
        logger.info("Topic-only job, creating empty slides structure")
        slides = SlidesExtracted(slides=[])
        with open(slides_json_path, "w") as f:
            json.dump(slides.model_dump(), f, indent=2)
        return
    
    # Find the input file
    input_dir = job_dir / "input"
    input_files = list(input_dir.glob("*.pdf")) + list(input_dir.glob("*.pptx"))
    
    if not input_files:
        logger.warning("No input file found, creating empty slides structure")
        slides = SlidesExtracted(slides=[])
        with open(slides_json_path, "w") as f:
            json.dump(slides.model_dump(), f, indent=2)
        return
    
    input_file = input_files[0]
    ext = input_file.suffix.lower()
    
    if ext == ".pdf":
        slides = extract_pdf(job_id, input_file)
    elif ext == ".pptx":
        slides = extract_pptx(job_id, input_file)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    
    # Save extracted slides
    with open(slides_json_path, "w") as f:
        json.dump(slides.model_dump(), f, indent=2)
    
    logger.info(f"Extracted {len(slides.slides)} slides")


def extract_pdf(job_id: str, pdf_path: Path) -> SlidesExtracted:
    """Extract content from a PDF file using PyMuPDF."""
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    extracted_dir = job_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    
    slides = []
    
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(pdf_path)
        
        for page_num, page in enumerate(doc, start=1):
            logger.info(f"Processing PDF page {page_num}")
            
            # Extract text
            text = page.get_text()
            
            # Render page as image
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for quality
            image_path = extracted_dir / f"slide_{page_num:02d}.png"
            pix.save(str(image_path))
            
            # Parse title (first line) and bullets
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            title = lines[0] if lines else f"Slide {page_num}"
            bullets = lines[1:] if len(lines) > 1 else []
            
            slides.append(SlideData(
                index=page_num,
                title=title,
                bullets=bullets[:10],  # Limit bullets
                raw_text=text,
                rendered_image=f"extracted/slide_{page_num:02d}.png",
                images=[],
            ))
        
        doc.close()
        
    except ImportError:
        logger.warning("PyMuPDF not installed, creating placeholder slide")
        slides.append(SlideData(
            index=1,
            title="PDF Content",
            bullets=["Content extracted from PDF"],
            raw_text="PDF content placeholder",
        ))
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        slides.append(SlideData(
            index=1,
            title="PDF Content",
            bullets=[f"Error extracting: {str(e)}"],
            raw_text="",
        ))
    
    return SlidesExtracted(slides=slides)


def extract_pptx(job_id: str, pptx_path: Path) -> SlidesExtracted:
    """Extract content from a PPTX file using python-pptx."""
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    extracted_dir = job_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    
    slides = []
    
    try:
        from pptx import Presentation
        
        prs = Presentation(pptx_path)
        
        for slide_num, slide in enumerate(prs.slides, start=1):
            logger.info(f"Processing PPTX slide {slide_num}")
            
            title = ""
            bullets = []
            raw_text_parts = []
            
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text = shape.text.strip()
                    if text:
                        raw_text_parts.append(text)
                        
                        # First text shape is usually title
                        if not title and hasattr(shape, "is_placeholder"):
                            title = text
                        else:
                            # Split into bullets
                            for line in text.split('\n'):
                                if line.strip():
                                    bullets.append(line.strip())
            
            if not title:
                title = f"Slide {slide_num}"
            
            slides.append(SlideData(
                index=slide_num,
                title=title,
                bullets=bullets[:10],
                raw_text="\n".join(raw_text_parts),
                images=[],
            ))
        
    except ImportError:
        logger.warning("python-pptx not installed, creating placeholder slide")
        slides.append(SlideData(
            index=1,
            title="PPTX Content",
            bullets=["Content extracted from PPTX"],
            raw_text="PPTX content placeholder",
        ))
    except Exception as e:
        logger.error(f"PPTX extraction error: {e}")
        slides.append(SlideData(
            index=1,
            title="PPTX Content",
            bullets=[f"Error extracting: {str(e)}"],
            raw_text="",
        ))
    
    return SlidesExtracted(slides=slides)
