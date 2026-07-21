"""Writing Larian LSPK (.pak) archives.

Primarily used for building test fixtures and repacking modified data,
this writer produces single-part v18 archives readable by the game and by
:class:`bg3forge.pak.reader.PakReader`.
"""

from __future__ import annotations

import hashlib
import zlib
from pathlib import Path

from . import lz4compat
from .format import (
    DEFAULT_VERSION,
    FILE_LIST_HEADER_STRUCT,
    HEADER_STRUCT,
    CompressionMethod,
    PakEntry,
    PakHeader,
)


class PakWriter:
    """Build a single-part .pak archive.

    Usage::

        writer = PakWriter()
        writer.add("Public/Shared/Stats/Generated/Data/Weapon.txt", data)
        writer.write("Shared.pak")
    """

    def __init__(
        self,
        version: int = DEFAULT_VERSION,
        compression: CompressionMethod = CompressionMethod.LZ4,
        priority: int = 0,
    ):
        self.version = version
        self.compression = compression
        self.priority = priority
        self._files: list[tuple[str, bytes]] = []

    def add(self, name: str, data: bytes) -> None:
        self._files.append((name.replace("\\", "/"), data))

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        entries: list[PakEntry] = []
        blobs: list[bytes] = []
        offset = HEADER_STRUCT.size
        for name, data in self._files:
            blob, method = self._compress(data)
            entries.append(
                PakEntry(
                    name=name,
                    offset=offset,
                    archive_part=0,
                    flags=int(method),
                    size_on_disk=len(blob),
                    uncompressed_size=0 if method is CompressionMethod.NONE else len(data),
                )
            )
            blobs.append(blob)
            offset += len(blob)

        table = b"".join(e.pack() for e in entries)
        compressed_table = lz4compat.compress(table)
        file_list = (
            FILE_LIST_HEADER_STRUCT.pack(len(entries), len(compressed_table))
            + compressed_table
        )
        header = PakHeader(
            version=self.version,
            file_list_offset=offset,
            file_list_size=len(file_list),
            flags=0,
            priority=self.priority,
            md5=hashlib.md5(table).digest(),
            num_parts=1,
        )
        with path.open("wb") as fh:
            fh.write(header.pack())
            for blob in blobs:
                fh.write(blob)
            fh.write(file_list)
        return path

    def _compress(self, data: bytes) -> tuple[bytes, CompressionMethod]:
        if self.compression is CompressionMethod.NONE or not data:
            return data, CompressionMethod.NONE
        if self.compression is CompressionMethod.ZLIB:
            return zlib.compress(data), CompressionMethod.ZLIB
        if self.compression is CompressionMethod.LZ4:
            return lz4compat.compress(data), CompressionMethod.LZ4
        raise ValueError(f"unsupported write compression: {self.compression}")
