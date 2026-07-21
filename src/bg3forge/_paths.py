"""Internal helpers for writing files beneath a caller-selected directory."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class UnsafePathError(ValueError):
    """Raised when untrusted input would select a path outside its root."""


def safe_output_path(root: str | Path, untrusted_name: str) -> Path:
    """Return an absolute output path guaranteed to remain beneath ``root``.

    Archive paths use forward slashes, but accepting data produced on other
    platforms means both POSIX and Windows absolute/drive syntax must be
    rejected explicitly.  Resolving the final path also catches an existing
    symlink inside ``root`` that points elsewhere.
    """
    if not untrusted_name or "\x00" in untrusted_name:
        raise UnsafePathError("path is empty or contains a null byte")

    normalized = untrusted_name.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise UnsafePathError("absolute and drive-qualified paths are not allowed")
    if any(part == ".." for part in posix_path.parts):
        raise UnsafePathError("parent-directory components are not allowed")
    if not posix_path.parts or posix_path == PurePosixPath("."):
        raise UnsafePathError("path does not name a file")

    resolved_root = Path(root).resolve()
    target = (resolved_root / Path(*posix_path.parts)).resolve()
    if not target.is_relative_to(resolved_root):
        raise UnsafePathError("resolved path escapes the output directory")
    return target
