"""Parser for Larian stats ``.txt`` files.

These are the ``Public/<Mod>/Stats/Generated/Data/*.txt`` files, e.g.::

    new entry "WPN_Longsword"
    type "Weapon"
    using "_BaseWeapon"
    data "Damage" "1d8"
    data "Damage Type" "Slashing"

Entries may inherit from another entry via ``using``; inheritance is
resolved lazily across every file loaded into a :class:`StatsCollection`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

_LINE_RE = re.compile(r'^(?P<keyword>[a-z ]+?)\s+"(?P<args>.*)"\s*$')
_ARG_SPLIT_RE = re.compile(r'"\s+"')


@dataclass
class StatsEntry:
    name: str
    type: str = ""
    using: str | None = None
    data: dict[str, str] = field(default_factory=dict)
    source: str | None = None  # file the entry came from

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.data.get(key, default)


class StatsParseError(ValueError):
    def __init__(self, message: str, source: str | None = None, line: int | None = None):
        location = f"{source or '<stats>'}:{line}" if line else source or "<stats>"
        super().__init__(f"{location}: {message}")


def parse_stats(text: str, source: str | None = None) -> list[StatsEntry]:
    """Parse one stats .txt document into a list of entries."""
    entries: list[StatsEntry] = []
    current: StatsEntry | None = None
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue  # tolerate directives we don't model (e.g. key/value oddities)
        keyword = match.group("keyword")
        args = _ARG_SPLIT_RE.split(match.group("args"))
        if keyword == "new entry":
            current = StatsEntry(name=args[0], source=source)
            entries.append(current)
        elif current is None:
            raise StatsParseError(f"{keyword!r} before any 'new entry'", source, lineno)
        elif keyword == "type":
            current.type = args[0]
        elif keyword == "using":
            current.using = args[0]
        elif keyword == "data":
            if len(args) < 2:
                raise StatsParseError(f"'data' needs a key and a value", source, lineno)
            current.data[args[0]] = args[1]
    return entries


class StatsCollection:
    """All stats entries across any number of files, with inheritance.

    ``resolved(name)`` returns the entry's effective data with every
    ``using`` ancestor's fields merged in (nearest definition wins).
    """

    def __init__(self, entries: Iterable[StatsEntry] = ()):
        self._entries: dict[str, StatsEntry] = {}
        for entry in entries:
            self.add(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[StatsEntry]:
        return iter(self._entries.values())

    def __getitem__(self, name: str) -> StatsEntry:
        return self._entries[name]

    def add(self, entry: StatsEntry) -> None:
        # Later definitions override earlier ones, mirroring pak priority.
        self._entries[entry.name] = entry

    def load_text(self, text: str, source: str | None = None) -> None:
        for entry in parse_stats(text, source):
            self.add(entry)

    def load_file(self, path: str | Path) -> None:
        path = Path(path)
        self.load_text(path.read_text("utf-8-sig"), source=path.name)

    def load_directory(self, directory: str | Path) -> None:
        for path in sorted(Path(directory).rglob("*.txt")):
            self.load_file(path)

    def by_type(self, *types: str) -> list[StatsEntry]:
        wanted = set(types)
        return [e for e in self._entries.values() if e.type in wanted]

    def resolved(self, name: str) -> dict[str, str]:
        """Effective key/value data for ``name`` with inheritance applied."""
        chain: list[StatsEntry] = []
        seen: set[str] = set()
        cursor: str | None = name
        while cursor is not None:
            if cursor in seen:
                raise StatsParseError(f"inheritance cycle at {cursor!r}")
            seen.add(cursor)
            entry = self._entries.get(cursor)
            if entry is None:
                break  # dangling 'using' reference; keep what we have
            chain.append(entry)
            cursor = entry.using
        data: dict[str, str] = {}
        for entry in reversed(chain):
            data.update(entry.data)
        return data
