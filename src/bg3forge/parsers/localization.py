"""Parser for Larian ``.loca`` localization archives.

Binary layout::

    char[4] signature   "LOCA"
    u32     num_entries
    u32     texts_offset            absolute offset of the text block
    -- entry table (num_entries records) --
    char[64] key                    null-padded handle, e.g. "h0123...;1"
    u16      version
    u32      length                 text length including NUL terminator
    -- text block at texts_offset: concatenated NUL-terminated UTF-8 --

BG3 handles referenced from stats/LSX look like ``h<uuid-ish>`` and may
carry a ``;<version>`` suffix; :class:`Localization` lookups accept both.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SIGNATURE = b"LOCA"
_HEADER = struct.Struct("<4sII")
_ENTRY = struct.Struct("<64sHI")


class LocaError(ValueError):
    pass


@dataclass(frozen=True)
class LocaEntry:
    key: str
    version: int
    text: str


def parse_loca(data: bytes) -> list[LocaEntry]:
    if len(data) < _HEADER.size:
        raise LocaError("file too small to be a .loca archive")
    signature, num_entries, texts_offset = _HEADER.unpack_from(data)
    if signature != SIGNATURE:
        raise LocaError(f"not a .loca file (signature {signature!r})")
    # num_entries is an untrusted u32: validate the whole entry table fits
    # before looping, so a truncated or corrupt file raises LocaError here
    # instead of leaking struct.error from deep inside the loop.
    if _HEADER.size + num_entries * _ENTRY.size > len(data):
        raise LocaError("truncated entry table")
    entries: list[LocaEntry] = []
    entry_offset = _HEADER.size
    text_offset = texts_offset
    for _ in range(num_entries):
        raw_key, version, length = _ENTRY.unpack_from(data, entry_offset)
        entry_offset += _ENTRY.size
        raw_text = data[text_offset : text_offset + length]
        if len(raw_text) != length:
            raise LocaError("truncated text block")
        text_offset += length
        entries.append(
            LocaEntry(
                key=raw_key.rstrip(b"\x00").decode("utf-8", errors="replace"),
                version=version,
                text=raw_text.rstrip(b"\x00").decode("utf-8", errors="replace"),
            )
        )
    return entries


def write_loca(entries: list[LocaEntry]) -> bytes:
    """Serialize entries back into .loca format (used for test fixtures)."""
    table = bytearray()
    texts = bytearray()
    for entry in entries:
        raw_key = entry.key.encode("utf-8")
        if len(raw_key) > 64:
            raise LocaError(f"key too long: {entry.key!r}")
        raw_text = entry.text.encode("utf-8") + b"\x00"
        table += _ENTRY.pack(raw_key.ljust(64, b"\x00"), entry.version, len(raw_text))
        texts += raw_text
    texts_offset = _HEADER.size + len(table)
    return _HEADER.pack(SIGNATURE, len(entries), texts_offset) + bytes(table) + bytes(texts)


class Localization:
    """Handle → text lookup across one or more .loca files."""

    def __init__(self):
        self._texts: dict[str, str] = {}
        self._versions: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self._texts)

    def __contains__(self, handle: str) -> bool:
        return self._normalize(handle) in self._texts

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self._texts.items())

    def load_bytes(self, data: bytes) -> None:
        for entry in parse_loca(data):
            key = self._normalize(entry.key)
            if entry.version >= self._versions.get(key, -1):
                self._texts[key] = entry.text
                self._versions[key] = entry.version

    def load_file(self, path: str | Path) -> None:
        self.load_bytes(Path(path).read_bytes())

    def resolve(self, handle: str | None, default: str = "") -> str:
        """Resolve a handle like ``h0abc...;1`` to its display text."""
        if not handle:
            return default
        return self._texts.get(self._normalize(handle), default)

    @staticmethod
    def _normalize(handle: str) -> str:
        return handle.split(";", 1)[0].strip()
