"""High-level facade over the whole toolkit.

:class:`Game` reads game data straight out of the installed ``.pak``
archives (no extraction step required) or from a pre-extracted directory
tree, and lazily builds typed collections::

    from bg3forge import Game

    game = Game()                     # auto-locate the install
    for item in game.items:
        print(item.name, item.display_name)

Everything is loaded on first access and cached, so constructing a Game
is cheap.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from .locate import find_game
from .models import (
    ITEM_TYPES,
    PASSIVE_TYPE,
    SPELL_TYPE,
    STATUS_TYPE,
    Item,
    Passive,
    Spell,
    Status,
)
from .pak.reader import PakReader
from .parsers.localization import Localization
from .parsers.lsx import LsxError, parse_lsx
from .parsers.roottemplates import RootTemplateIndex
from .parsers.stats import StatsCollection
from .parsers.treasure import TreasureTable, parse_treasure_tables
from .assets.atlases import TextureAtlas, parse_atlas


class GameNotFoundError(RuntimeError):
    pass


def _is_stats_file(name: str) -> bool:
    lowered = name.lower()
    return "/stats/generated/data/" in lowered and lowered.endswith(".txt")


def _is_treasure_file(name: str) -> bool:
    return name.lower().endswith("/stats/generated/treasuretable.txt")


def _is_roottemplate_file(name: str) -> bool:
    lowered = name.lower()
    return "/roottemplates/" in lowered and lowered.endswith(".lsx")


def _is_atlas_file(name: str) -> bool:
    lowered = name.lower()
    return "/gui/" in lowered and lowered.endswith(".lsx")


class Game:
    """Entry point to parsed BG3 data.

    Parameters
    ----------
    path:
        Game install root (the directory containing ``Data``).  When
        omitted, ``BG3_PATH`` and well-known install locations are tried.
    data_dir:
        Directory containing ``.pak`` archives directly (overrides
        ``path``).
    extracted_dir:
        A directory tree previously produced by the extractor; when set,
        files are read from disk instead of from archives.
    language:
        Localization language folder name (default ``"English"``).
    """

    def __init__(
        self,
        path: str | Path | None = None,
        data_dir: str | Path | None = None,
        extracted_dir: str | Path | None = None,
        language: str = "English",
    ):
        self.language = language
        self.extracted_dir = Path(extracted_dir) if extracted_dir else None
        if self.extracted_dir is not None:
            self.data_dir = None
        elif data_dir is not None:
            self.data_dir = Path(data_dir)
        else:
            root = find_game(path)
            if root is None:
                raise GameNotFoundError(
                    "could not locate a Baldur's Gate 3 install; pass path=, "
                    "data_dir=, extracted_dir=, or set BG3_PATH"
                )
            self.data_dir = root / "Data"

    # -- raw collections -----------------------------------------------------

    @cached_property
    def stats(self) -> StatsCollection:
        stats = StatsCollection()
        for name, data in self._iter_files(_is_stats_file):
            stats.load_text(data.decode("utf-8-sig", errors="replace"), source=name)
        return stats

    @cached_property
    def localization(self) -> Localization:
        loca = Localization()
        needle = f"/{self.language.lower()}/"
        for name, data in self._iter_files(
            lambda n: n.lower().endswith(".loca") and needle in f"/{n.lower()}"
        ):
            loca.load_bytes(data)
        return loca

    @cached_property
    def templates(self) -> RootTemplateIndex:
        index = RootTemplateIndex()
        for name, data in self._iter_files(_is_roottemplate_file):
            try:
                index.add_document(parse_lsx(data))
            except LsxError:
                continue
        return index

    @cached_property
    def atlases(self) -> list[TextureAtlas]:
        atlases = []
        for name, data in self._iter_files(_is_atlas_file):
            try:
                atlas = parse_atlas(parse_lsx(data))
            except LsxError:
                continue
            if atlas.icons:
                atlases.append(atlas)
        return atlases

    @cached_property
    def treasure_tables(self) -> list[TreasureTable]:
        tables: list[TreasureTable] = []
        for name, data in self._iter_files(_is_treasure_file):
            tables.extend(parse_treasure_tables(data.decode("utf-8-sig", errors="replace")))
        return tables

    # -- typed models --------------------------------------------------------

    @cached_property
    def items(self) -> list[Item]:
        items = []
        templates_by_key = self.templates
        for entry in self.stats.by_type(*ITEM_TYPES):
            data = self.stats.resolved(entry.name)
            map_key = data.get("RootTemplate")
            display = description = ""
            if map_key:
                fields = templates_by_key.resolved(map_key)
                display = self.localization.resolve(fields.get("DisplayName"))
                description = self.localization.resolve(fields.get("Description"))
            items.append(
                Item.from_stats(
                    entry.name,
                    entry.type,
                    data,
                    display_name=display,
                    description=description,
                    map_key=map_key,
                )
            )
        return items

    @cached_property
    def spells(self) -> list[Spell]:
        return [
            Spell.from_stats(entry.name, data, *self._texts(data))
            for entry in self.stats.by_type(SPELL_TYPE)
            if (data := self.stats.resolved(entry.name)) is not None
        ]

    @cached_property
    def passives(self) -> list[Passive]:
        return [
            Passive.from_stats(entry.name, data, *self._texts(data))
            for entry in self.stats.by_type(PASSIVE_TYPE)
            if (data := self.stats.resolved(entry.name)) is not None
        ]

    @cached_property
    def statuses(self) -> list[Status]:
        return [
            Status.from_stats(entry.name, data, *self._texts(data))
            for entry in self.stats.by_type(STATUS_TYPE)
            if (data := self.stats.resolved(entry.name)) is not None
        ]

    # -- internals -----------------------------------------------------------

    def _texts(self, data: dict[str, str]) -> tuple[str, str]:
        return (
            self.localization.resolve(data.get("DisplayName")),
            self.localization.resolve(data.get("Description")),
        )

    def _iter_files(self, predicate):
        """Yield (name, bytes) for archived/extracted files matching predicate."""
        if self.extracted_dir is not None:
            for file in sorted(self.extracted_dir.rglob("*")):
                if not file.is_file():
                    continue
                rel = file.relative_to(self.extracted_dir).as_posix()
                if predicate(rel):
                    yield rel, file.read_bytes()
            return
        for pak_path in sorted(self.data_dir.rglob("*.pak")):
            try:
                reader = PakReader(pak_path)
            except ValueError:
                continue  # secondary archive part or foreign file
            with reader:
                for entry in reader:
                    if predicate(entry.name):
                        yield entry.name, reader.read(entry)
