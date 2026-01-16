"""Stage 2: Generate script using LLM."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/app")

from shared.models import (
    ScriptPlan, ScriptLine, VisualCue, SlidesExtracted, Preset, StylePreset, Duration
)
from shared.utils import (
    get_job_dir, get_job_logger, load_job_metadata, 
    estimate_speech_duration, get_wpm_for_preset
)


def run_script_stage(job_id: str) -> None:
    """
    Generate a script plan using LLM or create a fallback script.
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    metadata = load_job_metadata(job_id)
    
    if not metadata:
        raise ValueError(f"Job {job_id} not found")
    
    # Check for idempotency
    script_json_path = job_dir / "llm" / "script.json"
    if script_json_path.exists():
        logger.info("CACHE HIT: script.json already exists, skipping generation")
        return
    
    # Load slides if available
    slides_path = job_dir / "extracted" / "slides.json"
    slides = None
    if slides_path.exists():
        with open(slides_path, "r") as f:
            slides = SlidesExtracted.model_validate(json.load(f))
    
    # Get topic for topic-only jobs
    topic = None
    outline = None
    topic_path = job_dir / "input" / "topic.json"
    if topic_path.exists():
        with open(topic_path, "r") as f:
            topic_data = json.load(f)
            topic = topic_data.get("topic", "")
            outline = topic_data.get("outline", "")
    
    # Try LLM generation first
    script = None
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    
    if os.getenv("GOOGLE_API_KEY") and llm_provider == "gemini":
        script = try_gemini_generation(job_id, topic, outline, slides, metadata.options)
    elif os.getenv("OPENAI_API_KEY") and llm_provider == "openai":
        script = try_openai_generation(job_id, topic, outline, slides, metadata.options)
    elif os.getenv("ANTHROPIC_API_KEY") and llm_provider == "anthropic":
        script = try_anthropic_generation(job_id, topic, outline, slides, metadata.options)
    
    # Fallback to simple script if LLM fails
    if script is None:
        logger.warning("LLM generation failed, using fallback script")
        script = create_fallback_script(job_id, topic, outline, slides, metadata.options)
    
    # Validate script fits target duration
    script = validate_and_adjust_script(script, metadata.options.length_sec, logger)
    
    # Save script
    script_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(script_json_path, "w") as f:
        json.dump(script.model_dump(), f, indent=2)
    
    # Update job title from script
    from shared.utils import update_job_status
    update_job_status(job_id, title=script.title)
    
    logger.info(f"Generated script with {len(script.script_lines)} lines")


def try_openai_generation(
    job_id: str, 
    topic: Optional[str], 
    outline: Optional[str],
    slides: Optional[SlidesExtracted],
    options
) -> Optional[ScriptPlan]:
    """Try to generate script using OpenAI API."""
    logger = get_job_logger(job_id)
    
    try:
        import openai
        
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = build_script_prompt(topic, outline, slides, options)
        
        # Get style-aware system prompt
        style = getattr(options, 'style_preset', StylePreset.STANDARD)
        
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": get_system_prompt(style)},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.8 if style == StylePreset.UNHINGED else 0.7,
        )
        
        result = response.choices[0].message.content
        script_data = json.loads(result)
        
        return ScriptPlan.model_validate(script_data)
        
    except Exception as e:
        logger.error(f"OpenAI generation failed: {e}")
        return None


def try_anthropic_generation(
    job_id: str,
    topic: Optional[str],
    outline: Optional[str],
    slides: Optional[SlidesExtracted],
    options
) -> Optional[ScriptPlan]:
    """Try to generate script using Anthropic API."""
    logger = get_job_logger(job_id)
    
    try:
        import anthropic
        
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        prompt = build_script_prompt(topic, outline, slides, options)
        
        # Get style-aware system prompt
        style = getattr(options, 'style_preset', StylePreset.STANDARD)
        
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            max_tokens=2048,
            system=get_system_prompt(style),
            messages=[{"role": "user", "content": prompt}],
        )
        
        result = response.content[0].text
        # Extract JSON from response
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            result = result.split("```")[1].split("```")[0]
        
        script_data = json.loads(result)
        return ScriptPlan.model_validate(script_data)
        
    except Exception as e:
        logger.error(f"Anthropic generation failed: {e}")
        return None


def try_gemini_generation(
    job_id: str,
    topic: Optional[str],
    outline: Optional[str],
    slides: Optional[SlidesExtracted],
    options
) -> Optional[ScriptPlan]:
    """Try to generate script using Google Gemini API."""
    logger = get_job_logger(job_id)
    
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        
        model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.8 if getattr(options, 'style_preset', StylePreset.STANDARD) == StylePreset.UNHINGED else 0.7,
            }
        )
        
        prompt = build_script_prompt(topic, outline, slides, options)
        
        # Get style-aware system prompt
        style = getattr(options, 'style_preset', StylePreset.STANDARD)
        system_prompt = get_system_prompt(style)
        
        # Combine system and user prompts for Gemini
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        response = model.generate_content(full_prompt)
        
        script_data = json.loads(response.text)
        
        return ScriptPlan.model_validate(script_data)
        
    except Exception as e:
        logger.error(f"Gemini generation failed: {e}")
        return None


def get_system_prompt(style_preset: StylePreset = StylePreset.STANDARD) -> str:
    """System prompt for script generation, customized by style preset."""
    
    base_schema = """Your output MUST be valid JSON matching this exact structure:
{
    "title": "string - catchy video title",
    "hook": "string - attention-grabbing first line",
    "style_preset": "FAST" | "BALANCED" | "EXAM",
    "script_lines": [
        {
            "t": 0.0,
            "line": "narration text",
            "emphasis": ["key", "words"],
            "source_slide_indices": [1]
        }
    ],
    "visual_cues": [
        {
            "t": 5.0,
            "query": "search query for visual",
            "type": "image",
            "priority": 1
        }
    ],
    "study_takeaways": ["bullet 1", "bullet 2", "bullet 3"]
}

Keep narration punchy and conversational. Use emphasis words that should pop on screen.
Visual cues should be specific, searchable terms for stock images."""

    style_instructions = {
        StylePreset.STANDARD: """You are a TikTok-style educational content creator. Generate engaging, 
punchy study video scripts that capture attention and deliver key learnings fast.
Keep your tone clear, friendly, and educational.""",
        
        StylePreset.UNHINGED: """You are a CHAOTIC Gen-Z educational content creator with ZERO chill.
Generate absolutely UNHINGED study scripts that are:
- Packed with memes, internet slang, and dramatic exaggerations
- Use phrases like "actually insane", "no cap", "fr fr", "lowkey", "highkey", "slay"
- React dramatically to every fact like it just personally attacked you
- Sound like you're telling your bestie the craziest tea ever
- Use ALL CAPS for emphasis
- Add chaotic energy transitions like "OKAY BUT WAIT" and "HOLD UP THO"
Make learning feel like scrolling through the most unhinged group chat.""",
        
        StylePreset.ASMR: """You are a calming ASMR-style educational content creator.
Generate soothing, whisper-worthy study scripts that are:
- Soft, gentle, and peaceful in tone
- Use calming language and smooth transitions
- Include sensory words and relaxing phrasing
- Perfect for late-night study sessions
- Sound like a gentle friend helping you understand
- Avoid jarring words or sudden tone changes
Make learning feel like a cozy, relaxing experience.""",
        
        StylePreset.GOSSIP: """You are a DRAMATIC storyteller who treats every fact like HOT TEA.
Generate gossip-style study scripts that are:
- Full of dramatic pauses and reveals ("And guess what happened NEXT...") 
- Treat historical figures and concepts like celebrities
- Use phrases like "spill the tea", "the drama", "iconic", "the gag is"
- Make facts sound like juicy secrets being shared
- Add dramatic commentary ("I mean, can you BELIEVE?!")
- Build suspense before revealing key information
Make learning feel like catching up on the hottest gossip.""",
        
        StylePreset.PROFESSOR: """You are an authoritative but engaging university professor.
Generate academic-style study scripts that are:
- Formal yet accessible and engaging
- Use precise, scholarly language
- Reference the broader context and implications
- Include phrases like "It's important to note...", "Research demonstrates..."
- Sound knowledgeable and confident
- Provide depth while remaining concise
Make learning feel like attending an excellent lecture.""",
    }
    
    style_intro = style_instructions.get(style_preset, style_instructions[StylePreset.STANDARD])
    
    return f"""{style_intro}

{base_schema}"""


def build_script_prompt(
    topic: Optional[str],
    outline: Optional[str],
    slides: Optional[SlidesExtracted],
    options
) -> str:
    """Build the prompt for script generation."""
    parts = []
    
    # Get duration from Duration enum if available
    duration = options.length_sec
    if hasattr(options, 'duration') and options.duration:
        duration_map = {
            Duration.QUICK: 35,      # Middle of 20-45
            Duration.STANDARD: 60,   # Middle of 45-80 
            Duration.EXTENDED: 150,  # 2.5 minutes
            Duration.CUSTOM: options.length_sec,
        }
        duration = duration_map.get(options.duration, options.length_sec)
    
    # Target parameters
    parts.append(f"Create a {duration}-second study video script.")
    parts.append(f"Pacing preset: {options.preset.value}")
    
    # Add style preset instruction if available
    if hasattr(options, 'style_preset') and options.style_preset:
        parts.append(f"Style: {options.style_preset.value} - Follow the style instructions EXACTLY.")
    
    parts.append(f"Caption style: {options.caption_style.value}")
    
    if topic:
        parts.append(f"\nTopic: {topic}")
    
    if outline:
        parts.append(f"\nOutline provided:\n{outline}")
    
    if slides and slides.slides:
        parts.append("\n\nSlide content to incorporate:")
        for slide in slides.slides[:10]:  # Limit to 10 slides
            parts.append(f"\nSlide {slide.index}: {slide.title}")
            if slide.bullets:
                for bullet in slide.bullets[:5]:
                    parts.append(f"  - {bullet}")
    
    parts.append("\n\nGenerate a JSON script following the exact schema specified.")
    parts.append("Ensure the total speaking time fits the target duration.")
    parts.append("Include 3-5 visual cues and 3-6 study takeaways.")
    
    return "\n".join(parts)


def create_fallback_script(
    job_id: str,
    topic: Optional[str],
    outline: Optional[str],
    slides: Optional[SlidesExtracted],
    options
) -> ScriptPlan:
    """Create a simple fallback script when LLM is unavailable."""
    logger = get_job_logger(job_id)
    logger.info("Creating fallback script")
    
    title = topic if topic else "Study Session"
    target_duration = options.length_sec
    preset = options.preset
    
    # Build content from available sources
    content_parts = []
    
    if topic:
        content_parts.append(topic)
    
    if outline:
        content_parts.append(outline)
    
    if slides and slides.slides:
        for slide in slides.slides[:5]:
            if slide.raw_text:
                content_parts.append(slide.raw_text[:200])
    
    content = " ".join(content_parts)[:500] if content_parts else "Let's learn something new today."
    
    # Create simple script lines
    hook = f"Hey! Let's break down {title} in under {target_duration} seconds."
    
    script_lines = [
        ScriptLine(t=0.0, line=hook, emphasis=[title.split()[0] if title else "this"]),
    ]
    
    # Add main content lines
    if content:
        words = content.split()
        chunk_size = len(words) // 3 if len(words) >= 9 else len(words)
        current_time = 3.0
        
        for i in range(0, min(len(words), chunk_size * 3), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk:
                script_lines.append(ScriptLine(
                    t=current_time,
                    line=chunk,
                    emphasis=words[i:i+2] if len(words) > i+1 else [],
                ))
                current_time += target_duration / 4
    
    # Add closing
    script_lines.append(ScriptLine(
        t=target_duration - 5,
        line="And that's the quick breakdown! Follow for more study tips.",
        emphasis=["follow"],
    ))
    
    return ScriptPlan(
        title=title,
        hook=hook,
        style_preset=preset,
        script_lines=script_lines,
        visual_cues=[
            VisualCue(t=5.0, query=f"{title} concept diagram", type="image", priority=1),
            VisualCue(t=15.0, query=f"{title} illustration", type="image", priority=2),
        ],
        study_takeaways=[
            f"Key concept: {title}",
            "Practice active recall",
            "Review within 24 hours",
        ],
    )


def validate_and_adjust_script(
    script: ScriptPlan, 
    target_duration: int,
    logger
) -> ScriptPlan:
    """Validate script duration and adjust if needed."""
    # Calculate total narration text
    total_text = " ".join(line.line for line in script.script_lines)
    estimated_duration = estimate_speech_duration(total_text, get_wpm_for_preset(script.style_preset.value))
    
    tolerance = 10  # seconds
    
    if abs(estimated_duration - target_duration) > tolerance:
        logger.warning(
            f"Script duration (~{estimated_duration:.0f}s) differs from target ({target_duration}s)"
        )
        # For MVP, just log the warning - a more sophisticated version would trim/pad
    
    return script
