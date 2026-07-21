"""YAML exporter (optional; requires PyYAML)."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

from .base import ensure_parent


def export_yaml(objects: Iterable[Any], path: str | Path) -> Path:
    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            "YAML export requires PyYAML; install with: pip install bg3forge[yaml]"
        ) from None
    path = ensure_parent(path)
    records = [asdict(obj) if is_dataclass(obj) else dict(obj) for obj in objects]
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(records, fh, sort_keys=True, allow_unicode=True)
    return path
