"""On-disk structures of Larian LSPK (.pak) archives.

BG3 ships LSPK version 18 archives (version 15 has the same entry layout
with a slightly different header).  Layout of a v18 archive:

* Header (at offset 0)::

      char[4]  signature      "LSPK"
      u32      version        18
      u64      file_list_offset
      u32      file_list_size
      u8       flags
      u8       priority
      u8[16]   md5            checksum of the file list
      u16      num_parts

* File list (at ``file_list_offset``)::

      u32      num_files
      u32      compressed_size
      u8[...]  LZ4 block-compressed table of ``num_files`` entries

* File entry (272 bytes each)::

      char[256] name          null-padded UTF-8 path
      u32       offset_lo     low 32 bits of data offset
      u16       offset_hi     high 16 bits of data offset
      u8        archive_part  index of the .pak part holding the data
      u8        flags         low nibble: compression method,
                              high nibble: compression level
      u32       size_on_disk  compressed size
      u32       uncompressed_size (0 when stored uncompressed)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

SIGNATURE = b"LSPK"
SUPPORTED_VERSIONS = (15, 16, 18)
DEFAULT_VERSION = 18

HEADER_STRUCT = struct.Struct("<4sIQIBB16sH")
FILE_LIST_HEADER_STRUCT = struct.Struct("<II")
ENTRY_STRUCT = struct.Struct("<256sIHBBII")
ENTRY_SIZE = ENTRY_STRUCT.size  # 272
NAME_SIZE = 256


class CompressionMethod(IntEnum):
    NONE = 0
    ZLIB = 1
    LZ4 = 2
    ZSTD = 3


@dataclass(frozen=True)
class PakHeader:
    version: int
    file_list_offset: int
    file_list_size: int
    flags: int
    priority: int
    md5: bytes
    num_parts: int

    @classmethod
    def parse(cls, data: bytes) -> "PakHeader":
        if len(data) < HEADER_STRUCT.size:
            raise ValueError("file too small to be a .pak archive")
        (
            signature,
            version,
            file_list_offset,
            file_list_size,
            flags,
            priority,
            md5,
            num_parts,
        ) = HEADER_STRUCT.unpack_from(data)
        if signature != SIGNATURE:
            raise ValueError(f"not an LSPK archive (signature {signature!r})")
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(f"unsupported LSPK version {version}")
        return cls(version, file_list_offset, file_list_size, flags, priority, md5, num_parts)

    def pack(self) -> bytes:
        return HEADER_STRUCT.pack(
            SIGNATURE,
            self.version,
            self.file_list_offset,
            self.file_list_size,
            self.flags,
            self.priority,
            self.md5,
            self.num_parts,
        )


@dataclass(frozen=True)
class PakEntry:
    """A single file inside a .pak archive."""

    name: str
    offset: int
    archive_part: int
    flags: int
    size_on_disk: int
    uncompressed_size: int

    @property
    def compression(self) -> CompressionMethod:
        return CompressionMethod(self.flags & 0x0F)

    @property
    def size(self) -> int:
        """Decompressed size of the file."""
        if self.compression is CompressionMethod.NONE:
            return self.size_on_disk
        return self.uncompressed_size

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> "PakEntry":
        raw_name, off_lo, off_hi, part, flags, size_on_disk, uncompressed = (
            ENTRY_STRUCT.unpack_from(data, offset)
        )
        name = raw_name.rstrip(b"\x00").decode("utf-8", errors="replace")
        return cls(
            name=name,
            offset=off_lo | (off_hi << 32),
            archive_part=part,
            flags=flags,
            size_on_disk=size_on_disk,
            uncompressed_size=uncompressed,
        )

    def pack(self) -> bytes:
        raw_name = self.name.encode("utf-8")
        if len(raw_name) > NAME_SIZE:
            raise ValueError(f"entry name too long: {self.name!r}")
        return ENTRY_STRUCT.pack(
            raw_name.ljust(NAME_SIZE, b"\x00"),
            self.offset & 0xFFFFFFFF,
            (self.offset >> 32) & 0xFFFF,
            self.archive_part,
            self.flags,
            self.size_on_disk,
            self.uncompressed_size,
        )
