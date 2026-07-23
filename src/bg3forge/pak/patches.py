"""Detect changed .pak archives between runs (game patch detection).

The game's data directory is fingerprinted (per-pak size, mtime and the
archive's own file-list MD5 from its header) into a small JSON snapshot.
Comparing the current state against the previous snapshot tells you which
archives a patch touched, so only those need re-extraction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .format import PakHeader


@dataclass(frozen=True)
class PakFingerprint:
    size: int
    mtime: float
    md5: str

    @classmethod
    def of(cls, path: Path) -> "PakFingerprint":
        stat = path.stat()
        with path.open("rb") as fh:
            header = PakHeader.parse(fh.read(64))
        return cls(size=stat.st_size, mtime=stat.st_mtime, md5=header.md5.hex())


@dataclass
class PatchReport:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def dirty(self) -> bool:
        return bool(self.added or self.changed or self.removed)


class PatchDetector:
    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)

    def scan(self, data_dir: str | Path) -> dict[str, PakFingerprint]:
        """Fingerprint every top-level .pak in ``data_dir`` (recursively)."""
        data_dir = Path(data_dir)
        result: dict[str, PakFingerprint] = {}
        for pak in sorted(data_dir.rglob("*.pak")):
            key = pak.relative_to(data_dir).as_posix()
            try:
                result[key] = PakFingerprint.of(pak)
            except ValueError:
                continue  # not an LSPK file (or a non-primary archive part)
            except OSError:
                continue  # unreadable (permissions, vanished mid-scan, a directory)
        return result

    def compare(self, data_dir: str | Path) -> PatchReport:
        """Compare current state with the stored snapshot."""
        current = self.scan(data_dir)
        previous = self._load_snapshot()
        report = PatchReport()
        for name, fp in current.items():
            if name not in previous:
                report.added.append(name)
            elif previous[name] != fp:
                report.changed.append(name)
        report.removed = sorted(set(previous) - set(current))
        return report

    def update(self, data_dir: str | Path) -> None:
        """Store the current state as the new snapshot."""
        current = self.scan(data_dir)
        payload = {
            name: {"size": fp.size, "mtime": fp.mtime, "md5": fp.md5}
            for name, fp in current.items()
        }
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps(payload, indent=1, sort_keys=True), "utf-8")

    def _load_snapshot(self) -> dict[str, PakFingerprint]:
        if not self.snapshot_path.exists():
            return {}
        try:
            raw = json.loads(self.snapshot_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            name: PakFingerprint(size=v["size"], mtime=v["mtime"], md5=v["md5"])
            for name, v in raw.items()
        }
