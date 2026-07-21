"""Locate an installed copy of Baldur's Gate 3.

Checks the ``BG3_PATH`` environment variable first, then well-known
Steam/GOG install locations for the current platform.  A directory counts
as an install if it contains a ``Data`` folder with at least one ``.pak``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_GAME_DIR = "Baldurs Gate 3"

_STEAM_LIBRARY_SUFFIX = Path("steamapps") / "common" / _GAME_DIR


def _candidate_paths() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        for drive in ("C:", "D:", "E:"):
            candidates += [
                Path(drive + "\\Program Files (x86)\\Steam") / _STEAM_LIBRARY_SUFFIX,
                Path(drive + "\\Program Files\\Steam") / _STEAM_LIBRARY_SUFFIX,
                Path(drive + "\\SteamLibrary") / _STEAM_LIBRARY_SUFFIX,
                Path(drive + "\\GOG Games") / _GAME_DIR,
                Path(drive + "\\Program Files (x86)\\GOG Galaxy\\Games") / _GAME_DIR,
            ]
    elif sys.platform == "darwin":
        candidates.append(
            home / "Library" / "Application Support" / "Steam" / _STEAM_LIBRARY_SUFFIX
        )
    else:
        candidates += [
            home / ".steam" / "steam" / _STEAM_LIBRARY_SUFFIX,
            home / ".local" / "share" / "Steam" / _STEAM_LIBRARY_SUFFIX,
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share"
            / "Steam" / _STEAM_LIBRARY_SUFFIX,
        ]
    return candidates


def is_game_dir(path: str | Path) -> bool:
    data = Path(path) / "Data"
    return data.is_dir() and any(data.glob("*.pak"))


def find_game(path: str | Path | None = None) -> Path | None:
    """Return the game's install root, or None if it cannot be found."""
    if path is not None:
        path = Path(path)
        return path if is_game_dir(path) else None
    env = os.environ.get("BG3_PATH")
    if env and is_game_dir(env):
        return Path(env)
    for candidate in _candidate_paths():
        if is_game_dir(candidate):
            return candidate
    return None
