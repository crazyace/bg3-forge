"""LZ4 support (block and frame formats) with pure-Python fallbacks.

Pak file lists and most pak entries in BG3 are LZ4 *block* compressed;
LSF resources use the LZ4 *frame* format for their chunked sections.
When the native :mod:`lz4` package is installed it is used; otherwise
this module falls back to:

* a complete pure-Python LZ4 block decompressor (correct for any input,
  just slower),
* a pure-Python LZ4 frame parser (reusing the block decompressor), and
* a literals-only LZ4 block compressor (produces valid but uncompressed
  LZ4 streams — fine for writing test fixtures and small files).

Frame *compression* has no pure-Python fallback (the frame header
checksum requires xxHash); writers that need it should store data
uncompressed instead when native LZ4 is missing.

This keeps the core library dependency-free.
"""

from __future__ import annotations

try:  # pragma: no cover - exercised implicitly when lz4 is installed
    import lz4.block as _lz4block
except ImportError:  # pragma: no cover
    _lz4block = None

HAVE_NATIVE_LZ4 = _lz4block is not None


class LZ4Error(ValueError):
    """Raised when an LZ4 block cannot be decoded."""


def decompress(data: bytes, uncompressed_size: int) -> bytes:
    """Decompress a raw LZ4 block of known uncompressed size."""
    if _lz4block is not None:
        return _lz4block.decompress(data, uncompressed_size=uncompressed_size)
    return _py_decompress(data, uncompressed_size)


def compress(data: bytes) -> bytes:
    """Compress ``data`` into a raw LZ4 block."""
    if _lz4block is not None:
        return _lz4block.compress(data, store_size=False)
    return _py_compress_literals(data)


def decompress_frame(data: bytes) -> bytes:
    """Decompress LZ4 *frame* format data (possibly concatenated frames)."""
    if _lz4block is not None:
        import lz4.frame

        out = bytearray()
        pos = 0
        # lz4.frame handles one frame per call; loop for concatenated frames.
        while pos < len(data):
            decompressed, bytes_read = lz4.frame.decompress(
                data[pos:], return_bytes_read=True
            )
            out += decompressed
            if bytes_read <= 0:
                break
            pos += bytes_read
        return bytes(out)
    return _py_decompress_frame(data)


def compress_frame(data: bytes) -> bytes:
    """Compress data into a single LZ4 frame (requires native lz4)."""
    if _lz4block is None:
        raise LZ4Error(
            "LZ4 frame compression requires the lz4 package; "
            "install bg3forge[lz4] or write uncompressed"
        )
    import lz4.frame

    return lz4.frame.compress(data)


_FRAME_MAGIC = 0x184D2204
_SKIPPABLE_MIN = 0x184D2A50
_SKIPPABLE_MAX = 0x184D2A5F


def _py_decompress_frame(src: bytes) -> bytes:
    out = bytearray()
    i = 0
    try:
        while i < len(src):
            magic = int.from_bytes(src[i : i + 4], "little")
            i += 4
            if _SKIPPABLE_MIN <= magic <= _SKIPPABLE_MAX:
                size = int.from_bytes(src[i : i + 4], "little")
                i += 4 + size
                continue
            if magic != _FRAME_MAGIC:
                raise LZ4Error(f"bad LZ4 frame magic {magic:#x}")
            flg = src[i]
            i += 2  # FLG + BD
            if flg >> 6 != 0b01:
                raise LZ4Error("unsupported LZ4 frame version")
            block_checksum = bool(flg & 0x10)
            if flg & 0x08:  # content size present
                i += 8
            if flg & 0x01:  # dictionary id present
                i += 4
            i += 1  # header checksum (not verified)
            while True:
                block_size = int.from_bytes(src[i : i + 4], "little")
                i += 4
                if block_size == 0:  # EndMark
                    break
                is_uncompressed = bool(block_size & 0x80000000)
                block_size &= 0x7FFFFFFF
                block = src[i : i + block_size]
                if len(block) != block_size:
                    raise LZ4Error("truncated LZ4 frame block")
                i += block_size
                out += block if is_uncompressed else _py_decompress(block, None)
                if block_checksum:
                    i += 4
            if flg & 0x04:  # content checksum (not verified)
                i += 4
    except IndexError as exc:
        raise LZ4Error("truncated LZ4 frame") from exc
    return bytes(out)


def _py_decompress(src: bytes, uncompressed_size: int | None) -> bytes:
    dst = bytearray()
    i = 0
    n = len(src)
    try:
        while i < n:
            token = src[i]
            i += 1
            literal_len = token >> 4
            if literal_len == 15:
                while True:
                    extra = src[i]
                    i += 1
                    literal_len += extra
                    if extra != 255:
                        break
            dst += src[i : i + literal_len]
            i += literal_len
            if i >= n:
                break  # last sequence carries no match
            offset = src[i] | (src[i + 1] << 8)
            i += 2
            if offset == 0:
                raise LZ4Error("invalid zero match offset")
            match_len = (token & 0x0F) + 4
            if match_len == 19:
                while True:
                    extra = src[i]
                    i += 1
                    match_len += extra
                    if extra != 255:
                        break
            start = len(dst) - offset
            if start < 0:
                raise LZ4Error("match offset beyond output start")
            # Matches may overlap the output being built; copy byte-wise.
            for j in range(match_len):
                dst.append(dst[start + j])
    except IndexError as exc:
        raise LZ4Error("truncated LZ4 block") from exc
    if uncompressed_size is not None and len(dst) != uncompressed_size:
        raise LZ4Error(
            f"decompressed size mismatch: got {len(dst)}, expected {uncompressed_size}"
        )
    return bytes(dst)


def _py_compress_literals(data: bytes) -> bytes:
    """Encode ``data`` as a single literals-only LZ4 sequence."""
    out = bytearray()
    length = len(data)
    out.append(min(length, 15) << 4)
    if length >= 15:
        remaining = length - 15
        while remaining >= 255:
            out.append(255)
            remaining -= 255
        out.append(remaining)
    out += data
    return bytes(out)
