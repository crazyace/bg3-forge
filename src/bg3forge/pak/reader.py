"""Reading Larian LSPK (.pak) archives."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from . import lz4compat
from .format import (
    FILE_LIST_HEADER_STRUCT,
    SIGNATURE,
    CompressionMethod,
    PakEntry,
    PakHeader,
)


class PakError(ValueError):
    pass


def file_is_lspk(path: str | Path) -> bool:
    """True when the file on disk starts with the LSPK signature.

    Distinguishes a *damaged* archive (worth reporting) from secondary
    archive parts and foreign files (routinely skipped): only the former
    carry the signature.
    """
    try:
        with Path(path).open("rb") as fh:
            return fh.read(4) == SIGNATURE
    except OSError:
        return False


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
        raw_header = self._fh.read(FILE_LIST_HEADER_STRUCT.size)
        if len(raw_header) != FILE_LIST_HEADER_STRUCT.size:
            raise PakError("truncated file list header")
        num_files, compressed_size = FILE_LIST_HEADER_STRUCT.unpack(raw_header)
        # v15/v16 use the 296-byte FileEntry15 layout, v18 the 272-byte one.
        entry_size = self.header.entry_size
        table_size = num_files * entry_size
        # An LZ4 block expands at most ~255x, so a table_size far beyond
        # that bound means num_files is corrupt.  Reject it here, before
        # the decompressor pre-allocates a buffer of that size.
        if table_size > compressed_size * 256 + 4096:
            raise PakError(f"implausible file count {num_files} in file list")
        compressed = self._fh.read(compressed_size)
        if len(compressed) != compressed_size:
            raise PakError("truncated file list")
        try:
            table = lz4compat.decompress(compressed, table_size)
        except lz4compat.LZ4Error as exc:
            raise PakError(f"corrupt file list: {exc}") from exc
        return PakEntry.parse_all(table, self.header.version)

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
        try:
            return lz4compat.zlib_decompress(raw)
        except lz4compat.LZ4Error as exc:
            raise PakError(f"corrupt zlib data for {name!r}: {exc}") from exc
        except ValueError as exc:  # DecompressionBombError
            raise PakError(f"{name!r}: {exc}") from exc
    if method is CompressionMethod.LZ4:
        try:
            lz4compat.guard_size(len(raw), uncompressed_size, lz4compat.MAX_RATIO_LZ4, name)
            return lz4compat.decompress(raw, uncompressed_size)
        except lz4compat.LZ4Error as exc:
            raise PakError(f"corrupt LZ4 data for {name!r}: {exc}") from exc
        except ValueError as exc:  # DecompressionBombError
            raise PakError(f"{name!r}: {exc}") from exc
    if method is CompressionMethod.ZSTD:
        try:
            import zstandard
        except ImportError:
            raise PakError(
                f"{name!r} is zstd-compressed; install bg3forge[zstd]"
            ) from None
        try:
            lz4compat.guard_size(len(raw), uncompressed_size, lz4compat.MAX_RATIO_ZSTD, name)
            return zstandard.ZstdDecompressor().decompress(
                raw, max_output_size=uncompressed_size
            )
        except lz4compat.DecompressionBombError as exc:
            raise PakError(f"{name!r}: {exc}") from exc
        except zstandard.ZstdError as exc:
            raise PakError(f"corrupt zstd data for {name!r}: {exc}") from exc
    raise PakError(f"unknown compression method {method} for {name!r}")
