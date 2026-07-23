"""On-disk structures of Larian LSPK (.pak) archives.

BG3 ships LSPK version 18 archives; versions 15 (DOS2 DE) and 16 (BG3
Early Access) are also readable.  Struct layouts follow LSLib, the
reference implementation.  Layout of a v18 archive:

* Header (at offset 0; v16 is identical, v15 omits ``num_parts``)::

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

* v18 file entry (272 bytes each)::

      char[256] name          null-padded UTF-8 path
      u32       offset_lo     low 32 bits of data offset
      u16       offset_hi     high 16 bits of data offset
      u8        archive_part  index of the .pak part holding the data
      u8        flags         low nibble: compression method,
                              high nibble: compression level
      u32       size_on_disk  compressed size
      u32       uncompressed_size (0 when stored uncompressed)

* v15/v16 file entry (296 bytes each; LSLib's ``FileEntry15``)::

      char[256] name
      u64       offset
      u64       size_on_disk
      u64       uncompressed_size
      u32       archive_part
      u32       flags
      u32       crc
      u32       unknown2
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

SIGNATURE = b"LSPK"
SUPPORTED_VERSIONS = (15, 16, 18)
DEFAULT_VERSION = 18

_MAGIC_VERSION_STRUCT = struct.Struct("<4sI")
HEADER_STRUCT = struct.Struct("<4sIQIBB16sH")  # v16/v18 (LSPKHeader16)
HEADER15_STRUCT = struct.Struct("<4sIQIBB16s")  # v15 has no num_parts
FILE_LIST_HEADER_STRUCT = struct.Struct("<II")
ENTRY_STRUCT = struct.Struct("<256sIHBBII")  # v18 (FileEntry18)
ENTRY_SIZE = ENTRY_STRUCT.size  # 272
ENTRY15_STRUCT = struct.Struct("<256sQQQIIII")  # v15/v16 (FileEntry15)
ENTRY15_SIZE = ENTRY15_STRUCT.size  # 296
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
        if len(data) < _MAGIC_VERSION_STRUCT.size:
            raise ValueError("file too small to be a .pak archive")
        signature, version = _MAGIC_VERSION_STRUCT.unpack_from(data)
        if signature != SIGNATURE:
            raise ValueError(f"not an LSPK archive (signature {signature!r})")
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(f"unsupported LSPK version {version}")
        layout = HEADER15_STRUCT if version == 15 else HEADER_STRUCT
        if len(data) < layout.size:
            raise ValueError("file too small to be a .pak archive")
        if version == 15:
            (_, _, file_list_offset, file_list_size, flags, priority, md5) = (
                layout.unpack_from(data)
            )
            num_parts = 1  # v15 predates multi-part archives
        else:
            (
                _,
                _,
                file_list_offset,
                file_list_size,
                flags,
                priority,
                md5,
                num_parts,
            ) = layout.unpack_from(data)
        return cls(version, file_list_offset, file_list_size, flags, priority, md5, num_parts)

    @property
    def entry_size(self) -> int:
        """Size of one file-list entry for this archive version."""
        return ENTRY15_SIZE if self.version < 18 else ENTRY_SIZE

    def pack(self) -> bytes:
        if self.version == 15:
            return HEADER15_STRUCT.pack(
                SIGNATURE,
                self.version,
                self.file_list_offset,
                self.file_list_size,
                self.flags,
                self.priority,
                self.md5,
            )
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

    @classmethod
    def parse15(cls, data: bytes, offset: int = 0) -> "PakEntry":
        """Parse the 296-byte v15/v16 entry layout (LSLib's FileEntry15)."""
        raw_name, off, size_on_disk, uncompressed, part, flags, _crc, _unknown = (
            ENTRY15_STRUCT.unpack_from(data, offset)
        )
        name = raw_name.rstrip(b"\x00").decode("utf-8", errors="replace")
        return cls(
            name=name,
            offset=off,
            archive_part=part,
            flags=flags,
            size_on_disk=size_on_disk,
            uncompressed_size=uncompressed,
        )

    @classmethod
    def parse_all(cls, table: bytes, version: int) -> list["PakEntry"]:
        """Parse a whole file-list table at once.

        ``struct.iter_unpack`` walks the fixed-size records in C, avoiding
        a Python-level offset multiply and method dispatch per entry — the
        file list holds hundreds of thousands of entries across a retail
        install.  ``table`` must be exactly ``num_files * entry_size``
        bytes (the caller sizes it so).
        """
        if version < 18:  # 296-byte FileEntry15
            return [
                cls(rn.rstrip(b"\x00").decode("utf-8", "replace"), off, part, flags, sod, unc)
                for rn, off, sod, unc, part, flags, _crc, _unk in ENTRY15_STRUCT.iter_unpack(table)
            ]
        return [
            cls(rn.rstrip(b"\x00").decode("utf-8", "replace"), lo | (hi << 32), part, flags, sod, unc)
            for rn, lo, hi, part, flags, sod, unc in ENTRY_STRUCT.iter_unpack(table)
        ]

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
