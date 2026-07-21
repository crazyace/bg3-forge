"""Markdown table exporter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .base import ensure_parent, normalize


def export_markdown(
    objects: Iterable[Any],
    path: str | Path,
    title: str | None = None,
    columns: list[str] | None = None,
) -> Path:
    """Write objects as a GitHub-flavored Markdown table.

    ``columns`` restricts and orders the columns; by default every column
    is included in first-seen order.
    """
    path = ensure_parent(path)
    records, all_columns = normalize(objects)
    cols = columns or all_columns
    lines: list[str] = []
    if title:
        lines += [f"# {title}", ""]
    if cols:
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join("---" for _ in cols) + " |")
        for record in records:
            cells = [_cell(record.get(c)) for c in cols]
            lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return path


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", "<br>")
