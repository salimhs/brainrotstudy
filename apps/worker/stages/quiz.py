"""Stage: Generate quiz questions from content."""

import json
import os
import sys
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, "/app")

from pydantic import BaseModel, Field
from shared.models import ScriptPlan, SlidesExtracted, StylePreset
from shared.utils import get_job_dir, get_job_logger


class QuizQuestion(BaseModel):
    """Single multiple-choice quiz question."""
    question: str
    options: List[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str
    difficulty: str = Field(default="medium")  # easy, medium, hard


class QuizSet(BaseModel):
    """Collection of quiz questions."""
    title: str
    questions: List[QuizQuestion] = Field(default_factory=list)


def run_quiz_stage(job_id: str) -> None:
    """
    Generate quiz questions from the extracted content and script.
    This runs after finalize stage as an optional enhancement.
    """
    logger = get_job_logger(job_id)
    job_dir = get_job_dir(job_id)
    
    # Check for idempotency
    quiz_json_path = job_dir / "output" / "quiz.json"
    if quiz_json_path.exists():
        logger.info("CACHE HIT: quiz.json already exists, skipping")
        return
    
    # Load script for content
    script_path = job_dir / "llm" / "script.json"
    script = None
    if script_path.exists():
        with open(script_path, "r") as f:
            script = ScriptPlan.model_validate(json.load(f))
    
    # Load slides for additional context
    slides_path = job_dir / "extracted" / "slides.json"
    slides = None
    if slides_path.exists():
        with open(slides_path, "r") as f:
            slides = SlidesExtracted.model_validate(json.load(f))
    
    # Try LLM generation first
    quiz = None
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    
    if os.getenv("GOOGLE_API_KEY") and llm_provider == "gemini":
        quiz = try_gemini_quiz_generation(job_id, script, slides)
    elif os.getenv("OPENAI_API_KEY") and llm_provider == "openai":
        quiz = try_openai_quiz_generation(job_id, script, slides)
    elif os.getenv("ANTHROPIC_API_KEY") and llm_provider == "anthropic":
        quiz = try_anthropic_quiz_generation(job_id, script, slides)
    
    # Fallback to simple quiz
    if quiz is None:
        logger.warning("LLM quiz generation failed, using fallback")
        quiz = create_fallback_quiz(script, slides)
    
    # Save quiz
    quiz_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(quiz_json_path, "w") as f:
        json.dump(quiz.model_dump(), f, indent=2)
    
    logger.info(f"Generated quiz with {len(quiz.questions)} questions")


def try_gemini_quiz_generation(
    job_id: str,
    script: Optional[ScriptPlan],
    slides: Optional[SlidesExtracted]
) -> Optional[QuizSet]:
    """Generate quiz using Gemini API."""
    logger = get_job_logger(job_id)
    
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        
        model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            generation_config={"response_mime_type": "application/json"}
        )
        
        prompt = build_quiz_prompt(script, slides)
        
        response = model.generate_content(prompt)
        quiz_data = json.loads(response.text)
        
        return QuizSet.model_validate(quiz_data)
        
    except Exception as e:
        logger.error(f"Gemini quiz generation failed: {e}")
        return None


def try_openai_quiz_generation(
    job_id: str,
    script: Optional[ScriptPlan],
    slides: Optional[SlidesExtracted]
) -> Optional[QuizSet]:
    """Generate quiz using OpenAI API."""
    logger = get_job_logger(job_id)
    
    try:
        import openai
        
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = build_quiz_prompt(script, slides)
        
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": get_quiz_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        
        result = response.choices[0].message.content
        quiz_data = json.loads(result)
        
        return QuizSet.model_validate(quiz_data)
        
    except Exception as e:
        logger.error(f"OpenAI quiz generation failed: {e}")
        return None


def try_anthropic_quiz_generation(
    job_id: str,
    script: Optional[ScriptPlan],
    slides: Optional[SlidesExtracted]
) -> Optional[QuizSet]:
    """Generate quiz using Anthropic API."""
    logger = get_job_logger(job_id)
    
    try:
        import anthropic
        
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        prompt = build_quiz_prompt(script, slides)
        
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            max_tokens=2048,
            system=get_quiz_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )
        
        result = response.content[0].text
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            result = result.split("```")[1].split("```")[0]
        
        quiz_data = json.loads(result)
        return QuizSet.model_validate(quiz_data)
        
    except Exception as e:
        logger.error(f"Anthropic quiz generation failed: {e}")
        return None


def get_quiz_system_prompt() -> str:
    """System prompt for quiz generation."""
    return """You are an expert educational content creator specializing in quiz generation.

Your output MUST be valid JSON matching this exact structure:
{
    "title": "Quiz Title",
    "questions": [
        {
            "question": "Question text ending with?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_index": 0,
            "explanation": "Why this answer is correct",
            "difficulty": "medium"
        }
    ]
}

Guidelines:
- Generate 5-8 questions covering key concepts
- Make questions clear and unambiguous
- Ensure all 4 options are plausible
- Include a mix of difficulties (easy, medium, hard)
- Provide helpful explanations
- Use proper grammar and formatting
- Make distractors (wrong answers) plausible but clearly incorrect"""


def build_quiz_prompt(
    script: Optional[ScriptPlan],
    slides: Optional[SlidesExtracted]
) -> str:
    """Build the prompt for quiz generation."""
    parts = [
        "Generate a multiple-choice quiz to test understanding of the following content:",
        ""
    ]
    
    if script:
        parts.append(f"Topic: {script.title}")
        parts.append("")
        parts.append("Key concepts covered:")
        for takeaway in script.study_takeaways[:5]:
            parts.append(f"- {takeaway}")
        parts.append("")
        parts.append("Content summary:")
        for line in script.script_lines[:10]:
            parts.append(f"  {line.line}")
    
    if slides and slides.slides:
        parts.append("")
        parts.append("Additional slide content:")
        for slide in slides.slides[:5]:
            if slide.title:
                parts.append(f"- {slide.title}")
            for bullet in slide.bullets[:3]:
                parts.append(f"  • {bullet}")
    
    parts.append("")
    parts.append("Generate a JSON quiz following the exact schema provided.")
    
    return "\n".join(parts)


def create_fallback_quiz(
    script: Optional[ScriptPlan],
    slides: Optional[SlidesExtracted]
) -> QuizSet:
    """Create a simple fallback quiz when LLM is unavailable."""
    title = script.title if script else "Study Quiz"
    
    # Create basic questions from takeaways
    questions = []
    
    if script and script.study_takeaways:
        for i, takeaway in enumerate(script.study_takeaways[:3]):
            questions.append(QuizQuestion(
                question=f"Which of the following is true about {script.title}?",
                options=[
                    takeaway,
                    "This is not covered in the material",
                    "This is the opposite of what was taught",
                    "This is unrelated to the topic"
                ],
                correct_index=0,
                explanation=f"The correct answer is based on: {takeaway}",
                difficulty="medium"
            ))
    
    # Ensure at least one question
    if not questions:
        questions.append(QuizQuestion(
            question=f"What was the main topic of this study session?",
            options=[
                title,
                "Something else entirely",
                "Not specified",
                "Multiple unrelated topics"
            ],
            correct_index=0,
            explanation=f"The main topic was: {title}",
            difficulty="easy"
        ))
    
    return QuizSet(title=f"{title} - Quiz", questions=questions)
