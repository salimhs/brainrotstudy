from pathlib import Path

from brainrotstudy.pipeline.extract import extract_from_path, extract_from_topic


def test_topic_only() -> None:
    content = extract_from_topic("Photosynthesis for MCAT")
    assert content.source == "topic"
    assert content.title == "Photosynthesis for MCAT"
    assert content.sections == []


def test_topic_with_outline() -> None:
    outline = """
# Light-dependent reactions
- Split water via PSII
- Generate ATP and NADPH

# Calvin cycle
- Fix CO2 with RuBisCO
- Output: G3P
"""
    content = extract_from_topic("Photosynthesis", outline)
    assert len(content.sections) == 2
    assert content.sections[0].heading == "Light-dependent reactions"
    assert "Split water via PSII" in content.sections[0].bullets
    assert content.sections[1].heading == "Calvin cycle"


def test_text_file(tmp_path: Path) -> None:
    f = tmp_path / "notes.md"
    f.write_text(
        "# Big O notation\n\n"
        "- O(1) constant\n"
        "- O(log n) logarithmic\n"
        "\n"
        "## Why it matters\n"
        "Scalability.\n"
    )
    content = extract_from_path(f)
    assert content.source == "text"
    assert content.title == "Big O notation"
    assert any("log n" in b for b in content.sections[0].bullets)


def test_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "oops.docx"
    f.write_bytes(b"not really a docx")
    import pytest

    with pytest.raises(ValueError):
        extract_from_path(f)
