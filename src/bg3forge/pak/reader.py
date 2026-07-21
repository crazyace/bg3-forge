"""Reading Larian LSPK (.pak) archives."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Iterator

from . import lz4compat
from .format import (
    FILE_LIST_HEADER_STRUCT,
    ENTRY_SIZE,
    CompressionMethod,
    PakEntry,
    PakHeader,
)


class PakError(ValueError):
    pass


class PakReader:
    """Random-access reader for a .pak archive.

    Multi-part archives (``Textures.pak`` + ``Textures_1.pak`` …) are
    handled transparently: entries whose ``archive_part`` is non-zero are
    read from the sibling part file.

    Usage::

        with PakReader("Shared.pak") as pak:
            for entry in pak:
                ...
            data = pak.read("Public/Shared/Stats/Generated/Data/Weapon.txt")
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = self.path.open("rb")
        self._part_handles: dict[int, object] = {0: self._fh}
        try:
            self.header = PakHeader.parse(self._fh.read(64))
            self._entries = self._read_file_list()
        except Exception:
            self.close()
            raise
        self._by_name = {e.name: e for e in self._entries}

    # -- container protocol -------------------------------------------------

    def __enter__(self) -> "PakReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __iter__(self) -> Iterator[PakEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def close(self) -> None:
        for handle in self._part_handles.values():
            handle.close()
        self._part_handles = {}

    # -- public API ----------------------------------------------------------

    @property
    def entries(self) -> list[PakEntry]:
        return list(self._entries)

    def names(self) -> list[str]:
        return [e.name for e in self._entries]

    def entry(self, name: str) -> PakEntry:
        try:
            return self._by_name[name]
        except KeyError:
            raise PakError(f"{name!r} not found in {self.path.name}") from None

    def read(self, name_or_entry: str | PakEntry) -> bytes:
        """Return the decompressed content of an archived file."""
        entry = (
            name_or_entry
            if isinstance(name_or_entry, PakEntry)
            else self.entry(name_or_entry)
        )
        fh = self._part_handle(entry.archive_part)
        fh.seek(entry.offset)
        raw = fh.read(entry.size_on_disk)
        if len(raw) != entry.size_on_disk:
            raise PakError(f"truncated data for {entry.name!r}")
        return _decompress(raw, entry.compression, entry.uncompressed_size, entry.name)

    # -- internals -----------------------------------------------------------

    def _read_file_list(self) -> list[PakEntry]:
        self._fh.seek(self.header.file_list_offset)
        num_files, compressed_size = FILE_LIST_HEADER_STRUCT.unpack(
            self._fh.read(FILE_LIST_HEADER_STRUCT.size)
        )
        table_size = num_files * ENTRY_SIZE
        compressed = self._fh.read(compressed_size)
        if len(compressed) != compressed_size:
            raise PakError("truncated file list")
        table = lz4compat.decompress(compressed, table_size)
        return [PakEntry.parse(table, i * ENTRY_SIZE) for i in range(num_files)]

    def _part_handle(self, part: int):
        if part not in self._part_handles:
            part_path = self._part_path(part)
            if not part_path.exists():
                raise PakError(f"missing archive part: {part_path.name}")
            self._part_handles[part] = part_path.open("rb")
        return self._part_handles[part]

    def _part_path(self, part: int) -> Path:
        if part == 0:
            return self.path
        return self.path.with_name(f"{self.path.stem}_{part}{self.path.suffix}")


def _decompress(
    raw: bytes, method: CompressionMethod, uncompressed_size: int, name: str
) -> bytes:
    if method is CompressionMethod.NONE:
        return raw
    if method is CompressionMethod.ZLIB:
        return zlib.decompress(raw)
    if method is CompressionMethod.LZ4:
        return lz4compat.decompress(raw, uncompressed_size)
    if method is CompressionMethod.ZSTD:
        try:
            import zstandard
        except ImportError:
            raise PakError(
                f"{name!r} is zstd-compressed; install bg3forge[zstd]"
            ) from None
        return zstandard.ZstdDecompressor().decompress(raw, max_output_size=uncompressed_size)
    raise PakError(f"unknown compression method {method} for {name!r}")
