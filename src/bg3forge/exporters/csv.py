"""CSV exporter."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from .base import ensure_parent, normalize


def export_csv(objects: Iterable[Any], path: str | Path) -> Path:
    path = ensure_parent(path)
    records, columns = normalize(objects)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    return path
