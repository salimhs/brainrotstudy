"""Stage 8: Finalize output and generate extras."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/app")

from shared.models import ScriptPlan, SlidesExtracted, TimelinePlan
from shared.utils import get_job_dir, get_job_logger, load_job_metadata


def run_finalize_stage(job_id: str) -> None:
    """
    Finalize the job:
    - Copy rendered video to output folder
    - Generate metadata
    - Generate export extras if requested
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    metadata = load_job_metadata(job_id)
    
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    final_video_path = output_dir / "final.mp4"
    
    # Check for idempotency
    if final_video_path.exists() and final_video_path.stat().st_size > 0:
        logger.info("CACHE HIT: final.mp4 already exists, skipping")
        return
    
    # Copy rendered video to output
    raw_video_path = job_dir / "render" / "video_raw.mp4"
    if not raw_video_path.exists():
        raise ValueError("video_raw.mp4 not found")
    
    shutil.copy(raw_video_path, final_video_path)
    logger.info("Copied video to output folder")
    
    # Generate metadata
    video_metadata = get_video_metadata(final_video_path, logger)
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(video_metadata, f, indent=2)
    
    # Generate export extras if requested
    if metadata.options.export_extras:
        generate_extras(job_id, logger)
    
    # Copy SRT to output
    srt_source = job_dir / "captions" / "captions.srt"
    if srt_source.exists():
        shutil.copy(srt_source, output_dir / "captions.srt")

    # Cleanup intermediate artifacts to save disk space
    cleanup_artifacts(job_id, logger)

    logger.info("Finalization completed")


def get_video_metadata(video_path: Path, logger) -> dict:
    """Get video metadata using FFprobe."""
    try:
        result = subprocess.run([
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ], capture_output=True, timeout=30)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            format_info = data.get("format", {})
            
            return {
                "duration_sec": float(format_info.get("duration", 0)),
                "size_bytes": int(format_info.get("size", 0)),
                "format": format_info.get("format_name", "mp4"),
                "bitrate": format_info.get("bit_rate", ""),
            }
    except Exception as e:
        logger.warning(f"Could not get video metadata: {e}")
    
    # Fallback to file size only
    return {
        "duration_sec": 0,
        "size_bytes": video_path.stat().st_size if video_path.exists() else 0,
        "format": "mp4",
    }


def generate_extras(job_id: str, logger) -> None:
    """Generate export extras: notes.md, anki.csv, quiz.json."""
    job_dir = get_job_dir(job_id)
    output_dir = job_dir / "output"
    
    # Load script and slides
    script_path = job_dir / "llm" / "script.json"
    script = None
    if script_path.exists():
        with open(script_path, "r") as f:
            script = ScriptPlan.model_validate(json.load(f))
    
    slides_path = job_dir / "extracted" / "slides.json"
    slides = None
    if slides_path.exists():
        with open(slides_path, "r") as f:
            slides = SlidesExtracted.model_validate(json.load(f))
    
    if script:
        # Generate enhanced notes.md with LLM
        generate_smart_notes(job_id, script, slides, output_dir / "notes.md", logger)
        
        # Generate anki.csv
        generate_anki_csv(script, output_dir / "anki.csv", logger)
        
        # Generate quiz
        try:
            from stages.quiz import run_quiz_stage
            run_quiz_stage(job_id)
        except Exception as e:
            logger.warning(f"Quiz generation failed: {e}")


def generate_notes_md(
    script: ScriptPlan, 
    slides: Optional[SlidesExtracted],
    output_path: Path,
    logger
) -> None:
    """Generate markdown study notes."""
    lines = []
    
    lines.append(f"# {script.title}")
    lines.append("")
    lines.append(f"> {script.hook}")
    lines.append("")
    
    lines.append("## Key Takeaways")
    lines.append("")
    for takeaway in script.study_takeaways:
        lines.append(f"- {takeaway}")
    lines.append("")
    
    lines.append("## Script Outline")
    lines.append("")
    for i, line in enumerate(script.script_lines, 1):
        lines.append(f"{i}. {line.line}")
        if line.emphasis:
            lines.append(f"   - Key words: {', '.join(line.emphasis)}")
    lines.append("")
    
    if slides and slides.slides:
        lines.append("## Source Slides")
        lines.append("")
        for slide in slides.slides[:10]:
            lines.append(f"### Slide {slide.index}: {slide.title}")
            for bullet in slide.bullets[:5]:
                lines.append(f"- {bullet}")
            lines.append("")
    
    lines.append("---")
    lines.append("*Generated by BrainRotStudy*")
    
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    
    logger.info("Generated notes.md")


def generate_anki_csv(script: ScriptPlan, output_path: Path, logger) -> None:
    """Generate Anki flashcard CSV."""
    rows = ["front,back"]
    
    # Create cards from takeaways
    for i, takeaway in enumerate(script.study_takeaways, 1):
        # Create simple Q/A format
        question = f"What is key point #{i} about {script.title}?"
        answer = takeaway
        
        # Escape commas and quotes for CSV
        question = question.replace('"', '""')
        answer = answer.replace('"', '""')
        
        rows.append(f'"{question}","{answer}"')
    
    # Create cards from emphasis words
    for line in script.script_lines:
        if line.emphasis:
            for word in line.emphasis[:2]:  # Limit to 2 per line
                question = f"In the context of {script.title}, explain: {word}"
                # Find context from the line
                answer = line.line
                
                question = question.replace('"', '""')
                answer = answer.replace('"', '""')
                
                rows.append(f'"{question}","{answer}"')
    
    with open(output_path, "w") as f:
        f.write("\n".join(rows[:20]))  # Limit to 20 cards
    
    logger.info("Generated anki.csv")


def generate_smart_notes(
    job_id: str,
    script: ScriptPlan, 
    slides: Optional[SlidesExtracted],
    output_path: Path,
    logger
) -> None:
    """Generate enhanced markdown study notes using LLM."""
    # Try LLM-enhanced summary
    smart_summary = None
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    
    if os.getenv("GOOGLE_API_KEY") and llm_provider == "gemini":
        smart_summary = try_gemini_summary(script, slides, logger)
    elif os.getenv("OPENAI_API_KEY") and llm_provider == "openai":
        smart_summary = try_openai_summary(script, slides, logger)
    elif os.getenv("ANTHROPIC_API_KEY") and llm_provider == "anthropic":
        smart_summary = try_anthropic_summary(script, slides, logger)
    
    # Fallback to basic notes
    if not smart_summary:
        generate_notes_md(script, slides, output_path, logger)
        return
    
    # Write enhanced summary
    with open(output_path, "w") as f:
        f.write(smart_summary)
    
    logger.info("Generated smart notes.md with LLM")


def try_gemini_summary(
    script: ScriptPlan,
    slides: Optional[SlidesExtracted],
    logger
) -> Optional[str]:
    """Generate smart summary using Gemini."""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
        
        prompt = build_summary_prompt(script, slides)
        response = model.generate_content(prompt)
        
        return response.text
        
    except Exception as e:
        logger.debug(f"Gemini summary failed: {e}")
        return None


def try_openai_summary(
    script: ScriptPlan,
    slides: Optional[SlidesExtracted],
    logger
) -> Optional[str]:
    """Generate smart summary using OpenAI."""
    try:
        import openai
        
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = build_summary_prompt(script, slides)
        
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are an expert educational content summarizer. Create clear, structured markdown study notes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.debug(f"OpenAI summary failed: {e}")
        return None


def try_anthropic_summary(
    script: ScriptPlan,
    slides: Optional[SlidesExtracted],
    logger
) -> Optional[str]:
    """Generate smart summary using Anthropic."""
    try:
        import anthropic
        
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = build_summary_prompt(script, slides)
        
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            max_tokens=2048,
            system="You are an expert educational content summarizer. Create clear, structured markdown study notes.",
            messages=[{"role": "user", "content": prompt}],
        )
        
        return response.content[0].text
        
    except Exception as e:
        logger.debug(f"Anthropic summary failed: {e}")
        return None


def cleanup_artifacts(job_id: str, logger) -> None:
    """
    Remove large intermediate files after finalization to save disk space.
    Target ~50% storage reduction per job by removing video_raw.mp4 and other temp files.
    """
    job_dir = get_job_dir(job_id)
    total_freed_mb = 0

    # List of files/directories to remove
    artifacts_to_remove = [
        job_dir / "render" / "video_raw.mp4",  # Largest file (~90% of job size)
        job_dir / "audio" / "temp.mp3",         # Temp audio files
        job_dir / "audio" / "temp.wav",         # Temp audio files
    ]

    for artifact_path in artifacts_to_remove:
        if artifact_path.exists():
            try:
                size_bytes = artifact_path.stat().st_size
                size_mb = size_bytes / (1024 * 1024)

                if artifact_path.is_file():
                    artifact_path.unlink()
                    logger.info(f"Cleaned up {artifact_path.name} ({size_mb:.1f} MB)")
                    total_freed_mb += size_mb

            except Exception as e:
                logger.warning(f"Failed to clean up {artifact_path}: {e}")

    if total_freed_mb > 0:
        logger.info(f"Total storage freed: {total_freed_mb:.1f} MB")


def build_summary_prompt(
    script: ScriptPlan,
    slides: Optional[SlidesExtracted]
) -> str:
    """Build prompt for smart summary generation."""
    parts = [
        f"Create comprehensive markdown study notes for: {script.title}",
        "",
        "Content to summarize:",
        "",
        f"Hook: {script.hook}",
        "",
        "Key Takeaways:",
    ]
    
    for takeaway in script.study_takeaways:
        parts.append(f"- {takeaway}")
    
    parts.append("")
    parts.append("Script Content:")
    for line in script.script_lines:
        parts.append(f"- {line.line}")
    
    if slides and slides.slides:
        parts.append("")
        parts.append("Source Material:")
        for slide in slides.slides[:5]:
            if slide.title:
                parts.append(f"## {slide.title}")
            for bullet in slide.bullets[:5]:
                parts.append(f"- {bullet}")
    
    parts.append("")
    parts.append("Generate markdown notes with:")
    parts.append("- Clear section headers")
    parts.append("- Bullet points for key concepts")
    parts.append("- Examples where applicable")
    parts.append("- Summary section at the end")
    parts.append("- Study tips or mnemonics if helpful")
    
    return "\n".join(parts)

