from __future__ import annotations

import json

import pytest

from brainrotstudy.pipeline import script as script_mod
from brainrotstudy.schemas import ExtractedContent, ExtractedSection, JobOptions, Pacing, Vibe


def _content() -> ExtractedContent:
    return ExtractedContent(
        title="Cell respiration",
        source="topic",
        sections=[
            ExtractedSection(
                heading="Glycolysis",
                bullets=["Glucose → 2 pyruvate", "Net 2 ATP", "Happens in cytoplasm"],
            )
        ],
    )


def test_auto_provider_prefers_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    from brainrotstudy import config

    config.get_settings.cache_clear()
    assert script_mod._pick_provider(config.get_settings()) == "gemini"


def test_auto_provider_falls_back_to_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    from brainrotstudy import config

    config.get_settings.cache_clear()
    assert script_mod._pick_provider(config.get_settings()) == "anthropic"


def test_no_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    from brainrotstudy import config

    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="No LLM API key"):
        script_mod._pick_provider(config.get_settings())


def test_generate_script_with_mock_caller() -> None:
    mock = json.dumps(
        {
            "title": "Cell respiration in 60s",
            "hook": "Your cells eat pizza too, here's how.",
            "segments": [
                {
                    "text": "First, glycolysis breaks glucose into pyruvate.",
                    "emphasis": ["glycolysis", "pyruvate"],
                    "visual_query": "glucose molecule diagram",
                },
                {
                    "text": "Net gain: two ATP molecules in the cytoplasm.",
                    "emphasis": ["two ATP"],
                    "visual_query": "ATP molecule",
                },
            ],
            "takeaways": ["Glycolysis = cytoplasm", "Net 2 ATP", "Glucose → 2 pyruvate"],
        }
    )

    opts = JobOptions(length_sec=45, pacing=Pacing.FAST, vibe=Vibe.STANDARD)
    result = script_mod.generate_script(
        _content(), opts, llm_caller=lambda sys, user: mock
    )
    assert result.title.startswith("Cell respiration")
    assert len(result.segments) == 2
    assert result.segments[0].emphasis == ["glycolysis", "pyruvate"]
    assert result.takeaways[0] == "Glycolysis = cytoplasm"


def test_generate_script_strips_markdown_fences() -> None:
    wrapped = "```json\n" + json.dumps(
        {
            "title": "X",
            "hook": "hi",
            "segments": [{"text": "hello world", "emphasis": [], "visual_query": "q"}],
            "takeaways": ["a", "b", "c"],
        }
    ) + "\n```"
    opts = JobOptions()
    result = script_mod.generate_script(
        _content(), opts, llm_caller=lambda sys, user: wrapped
    )
    assert result.segments[0].text == "hello world"


def test_emphasis_filtered_to_words_in_text() -> None:
    raw = json.dumps(
        {
            "title": "t",
            "hook": "h",
            "segments": [
                {
                    "text": "mitochondria generate energy",
                    "emphasis": ["mitochondria", "unrelated"],
                    "visual_query": "mitochondria",
                }
            ],
            "takeaways": ["x"],
        }
    )
    result = script_mod.generate_script(
        _content(), JobOptions(), llm_caller=lambda s, u: raw
    )
    assert result.segments[0].emphasis == ["mitochondria"]


def test_bad_json_raises() -> None:
    with pytest.raises(ValueError):
        script_mod.generate_script(
            _content(), JobOptions(), llm_caller=lambda s, u: "not json at all"
        )


def test_empty_segments_raises() -> None:
    raw = json.dumps({"title": "t", "hook": "h", "segments": [], "takeaways": []})
    with pytest.raises(ValueError, match="no segments"):
        script_mod.generate_script(
            _content(), JobOptions(), llm_caller=lambda s, u: raw
        )
