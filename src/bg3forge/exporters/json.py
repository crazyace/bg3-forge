"""JSON exporter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .base import ensure_parent, normalize


def export_json(
    objects: Iterable[Any],
    path: str | Path,
    indent: int | None = 2,
    flatten: bool = False,
) -> Path:
    """Write objects as a JSON array.

    With ``flatten=False`` (default) dataclass records keep their nested
    mappings and lists.  With ``flatten=True``, raw ``data`` / ``fields``
    mappings become namespaced columns and list-valued model fields become
    semicolon-delimited scalars, matching the tabular exporters.  Keys are
    sorted for deterministic output.
    """
    path = ensure_parent(path)
    if flatten:
        records, _ = normalize(objects)
    else:
        from dataclasses import asdict, is_dataclass

        records = [
            asdict(obj) if is_dataclass(obj) else dict(obj) for obj in objects
        ]
    path.write_text(
        json.dumps(records, indent=indent, sort_keys=True, ensure_ascii=False) + "\n",
        "utf-8",
    )
    return path
