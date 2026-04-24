"""Stage 2: LLM generates a video script from extracted content."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from ..config import Settings, get_settings
from ..schemas import ExtractedContent, JobOptions, Pacing, Script, ScriptSegment, Vibe

log = logging.getLogger(__name__)

WPM = {Pacing.FAST: 185, Pacing.BALANCED: 165, Pacing.CHILL: 140}


VIBES = {
    Vibe.STANDARD: (
        "You are a sharp, warm educational creator making a TikTok-length study recap. "
        "Tone is clear, punchy, and friendly — like the smartest person in your group chat."
    ),
    Vibe.UNHINGED: (
        "You are a chaotic Gen-Z creator with ZERO chill. Heavy slang ('no cap', 'lowkey', 'actually insane'), "
        "dramatic reactions, strategic ALL CAPS. Every fact is the most insane thing you've heard this week."
    ),
    Vibe.ASMR: (
        "You are an ASMR study companion: soft, slow, soothing. Gentle transitions, calming sensory words, "
        "no jarring punctuation. Perfect for a late-night study session."
    ),
    Vibe.GOSSIP: (
        "You are spilling the hottest tea. Treat every concept like celebrity drama. Dramatic pauses, "
        "reveals ('and you WON'T believe what happened next…'), playful commentary."
    ),
    Vibe.PROFESSOR: (
        "You are a brilliant, engaging professor. Precise language, broader context, confident citations. "
        "Substantive but concise — office hours energy."
    ),
}


def _sys_prompt(vibe: Vibe) -> str:
    return (
        VIBES[vibe]
        + "\n\nYou will receive study material. Respond with a JSON object matching this schema EXACTLY:\n"
        '{\n'
        '  "title": string,                         // punchy video title, <= 70 chars\n'
        '  "hook": string,                          // first 2 seconds of narration — grab attention\n'
        '  "segments": [                            // 5-10 spoken beats, in order\n'
        '    {\n'
        '      "text": string,                      // one spoken line, 8-25 words\n'
        '      "emphasis": string[],                // 0-3 key words from `text` to highlight\n'
        '      "visual_query": string               // 2-4 word search query for a stock image\n'
        '    }\n'
        '  ],\n'
        '  "takeaways": string[]                    // 3-5 short study bullets for notes\n'
        "}\n\n"
        "Rules:\n"
        "- Respond with ONLY the JSON object. No prose, no markdown fences.\n"
        "- Write narration as it should be spoken aloud; no stage directions, no '(pause)'.\n"
        "- The `emphasis` list must only contain words that literally appear in `text`.\n"
        "- Every visual_query should be a concrete noun phrase a stock-photo search would match."
    )


def _user_prompt(content: ExtractedContent, opts: JobOptions) -> str:
    wpm = WPM[opts.pacing]
    target_words = max(20, int(opts.length_sec * wpm / 60))
    parts: list[str] = [
        f"Target duration: {opts.length_sec} seconds at {wpm} words/min "
        f"(≈ {target_words} spoken words total across segments).",
        f"Pacing: {opts.pacing.value}. Vibe: {opts.vibe.value}.",
        f"Title candidate: {content.title}",
    ]
    if content.sections:
        parts.append("\nSource material:")
        for i, section in enumerate(content.sections[:12], 1):
            parts.append(f"\n## {i}. {section.heading or 'Section'}")
            for bullet in section.bullets[:6]:
                parts.append(f"- {bullet}")
            if section.body:
                parts.append(section.body[:500])
    else:
        parts.append(
            "\nNo source outline provided — write an engaging, factually grounded "
            f"recap of the topic: {content.title!r}."
        )
    parts.append("\nReturn the JSON object now.")
    return "\n".join(parts)


# ------- Provider dispatch ------------------------------------------------


def _pick_provider(settings: Settings) -> str:
    """Auto-select the first available provider, honoring an explicit override."""
    if settings.llm_provider != "auto":
        key_attr = {
            "gemini": "google_api_key",
            "anthropic": "anthropic_api_key",
            "openai": "openai_api_key",
        }[settings.llm_provider]
        if not getattr(settings, key_attr):
            raise RuntimeError(
                f"LLM_PROVIDER={settings.llm_provider} but {key_attr.upper()} is not set."
            )
        return settings.llm_provider

    # Priority: Gemini (free tier) → Anthropic → OpenAI
    if settings.google_api_key:
        return "gemini"
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.openai_api_key:
        return "openai"
    raise RuntimeError(
        "No LLM API key configured. Set one of GOOGLE_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY."
    )


def generate_script(
    content: ExtractedContent,
    options: JobOptions,
    *,
    settings: Settings | None = None,
    llm_caller: Callable[[str, str], str] | None = None,
) -> Script:
    """Produce a Script via the configured LLM provider.

    ``llm_caller`` exists purely so tests can short-circuit network calls.
    """
    settings = settings or get_settings()
    system = _sys_prompt(options.vibe)
    user = _user_prompt(content, options)

    if llm_caller is None:
        provider = _pick_provider(settings)
        log.info("generating script via %s", provider)
        llm_caller = _CALLERS[provider](settings)

    raw = llm_caller(system, user)
    data = _parse_json(raw)
    script = _coerce_script(data, fallback_title=content.title)
    _validate(script)
    return script


# ------- Providers --------------------------------------------------------


def _gemini_caller(settings: Settings) -> Callable[[str, str], str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.google_api_key)

    def call(system: str, user: str) -> str:
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                temperature=0.8,
            ),
        )
        return resp.text or ""

    return call


def _anthropic_caller(settings: Settings) -> Callable[[str, str], str]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def call(system: str, user: str) -> str:
        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text if resp.content else ""

    return call


def _openai_caller(settings: Settings) -> Callable[[str, str], str]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    def call(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            temperature=0.8,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    return call


_CALLERS: dict[str, Callable[[Settings], Callable[[str, str], str]]] = {
    "gemini": _gemini_caller,
    "anthropic": _anthropic_caller,
    "openai": _openai_caller,
}


# ------- Parsing helpers --------------------------------------------------


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("﻿"):
        text = text[1:]
    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError(f"LLM did not return JSON: {raw[:200]!r}")
    return json.loads(text[first : last + 1])


def _coerce_script(data: dict[str, Any], *, fallback_title: str) -> Script:
    segments_raw = data.get("segments") or []
    segments: list[ScriptSegment] = []
    for seg in segments_raw:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            ScriptSegment(
                text=text,
                emphasis=[str(w).strip() for w in (seg.get("emphasis") or []) if w],
                visual_query=str(seg.get("visual_query", "")).strip(),
            )
        )
    takeaways = [str(t).strip() for t in (data.get("takeaways") or []) if t]
    return Script(
        title=str(data.get("title") or fallback_title)[:120],
        hook=str(data.get("hook", "")).strip(),
        segments=segments,
        takeaways=takeaways[:6],
    )


def _validate(script: Script) -> None:
    if not script.segments:
        raise ValueError("LLM returned a script with no segments")
    if not script.hook:
        # Non-fatal: synthesize from first segment so downstream still works.
        script.hook = script.segments[0].text
    for seg in script.segments:
        text_lower = seg.text.lower()
        seg.emphasis = [e for e in seg.emphasis if e.lower() in text_lower]
