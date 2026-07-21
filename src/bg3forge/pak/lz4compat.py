"""LZ4 block compression support with a pure-Python fallback.

Pak file lists and most pak entries in BG3 are LZ4 block compressed.  When
the native :mod:`lz4` package is installed it is used for both directions;
otherwise this module falls back to:

* a complete pure-Python LZ4 *block* decompressor (correct for any input,
  just slower), and
* a literals-only LZ4 *block* compressor (produces valid but uncompressed
  LZ4 streams — fine for writing test fixtures and small files).

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


def _py_decompress(src: bytes, uncompressed_size: int) -> bytes:
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
    if len(dst) != uncompressed_size:
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
