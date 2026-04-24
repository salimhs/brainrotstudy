"""Stage 6: write study-extras artifacts (notes, Anki)."""

from __future__ import annotations

import csv
from pathlib import Path

from ..schemas import Script


def write_notes(script: Script, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [f"# {script.title}", ""]
    if script.hook:
        lines.append(f"> {script.hook}")
        lines.append("")
    if script.takeaways:
        lines.append("## Key takeaways")
        lines.extend(f"- {t}" for t in script.takeaways)
        lines.append("")
    lines.append("## Narration")
    for i, seg in enumerate(script.segments, 1):
        lines.append(f"{i}. {seg.text}")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_anki(script: Script, path: Path) -> None:
    """Emit a simple front-back CSV compatible with Anki's basic import.

    Cards = takeaways if present, else one card per segment.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    if script.takeaways:
        for t in script.takeaways:
            front = t.split(":")[0].split("—")[0].strip() or t[:60]
            back = t
            rows.append((front, back))
    else:
        for seg in script.segments:
            front = (seg.visual_query or seg.text.split(".")[0]).strip()[:80]
            rows.append((front, seg.text))

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Front", "Back"])
        writer.writerows(rows)
