"""Shared exporter plumbing.

Every exporter consumes an iterable of models (or plain dicts) and writes
one named dataset.  Records are flattened via :func:`bg3forge.models.to_record`
so nested ``data`` fields become stable ``data.<Key>`` columns.  Column
order is deterministic: fields in first-seen order, which keeps exports
reproducible for identical inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..models import to_record


def normalize(objects: Iterable[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Flatten objects into records and compute the union of columns."""
    records = [to_record(obj) for obj in objects]
    columns: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return records, columns


def ensure_parent(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
