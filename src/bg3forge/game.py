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

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .locate import find_game
from .models import (
    ITEM_TYPES,
    PASSIVE_TYPE,
    SPELL_TYPE,
    STATUS_TYPE,
    Item,
    NamedCollection,
    Passive,
    Spell,
    Status,
)
from .pak.reader import PakReader
from .parsers.localization import Localization
from .parsers.resource import parse_resource
from .parsers.roottemplates import RootTemplateIndex
from .parsers.stats import StatsCollection
from .parsers.treasure import TreasureTable, parse_treasure_tables
from .assets.atlases import TextureAtlas, parse_atlas


class GameNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadIssue:
    """A file that failed to parse while loading a collection."""

    file: str
    error: str


def _is_stats_file(name: str) -> bool:
    lowered = name.lower()
    return "/stats/generated/data/" in lowered and lowered.endswith(".txt")


def _is_treasure_file(name: str) -> bool:
    return name.lower().endswith("/stats/generated/treasuretable.txt")


def _is_roottemplate_file(name: str) -> bool:
    lowered = name.lower()
    return "/roottemplates/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_atlas_file(name: str) -> bool:
    lowered = name.lower()
    return "/gui/" in lowered and lowered.endswith((".lsx", ".lsf"))


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
        #: Files that failed to parse during loading.  A malformed file
        #: never aborts a load — it is recorded here and skipped, so one
        #: bad file can't take down the whole pipeline.  ``bg3forge
        #: validate`` reports the same failures with full detail.
        self.load_issues: list[LoadIssue] = []

    # -- raw collections -----------------------------------------------------

    @cached_property
    def stats(self) -> StatsCollection:
        stats = StatsCollection()
        for name, data in self._iter_files(_is_stats_file):
            try:
                stats.load_text(data.decode("utf-8-sig", errors="replace"), source=name)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        return stats

    @cached_property
    def localization(self) -> Localization:
        loca = Localization()
        needle = f"/{self.language.lower()}/"
        for name, data in self._iter_files(
            lambda n: n.lower().endswith(".loca") and needle in f"/{n.lower()}"
        ):
            try:
                loca.load_bytes(data)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        return loca

    @cached_property
    def templates(self) -> RootTemplateIndex:
        index = RootTemplateIndex()
        for name, data in self._iter_files(_is_roottemplate_file):
            try:
                index.add_document(parse_resource(data))
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        return index

    @cached_property
    def atlases(self) -> list[TextureAtlas]:
        atlases = []
        for name, data in self._iter_files(_is_atlas_file):
            try:
                atlas = parse_atlas(parse_resource(data))
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
                continue
            if atlas.icons:
                atlases.append(atlas)
        return atlases

    @cached_property
    def treasure_tables(self) -> list[TreasureTable]:
        tables: list[TreasureTable] = []
        for name, data in self._iter_files(_is_treasure_file):
            try:
                tables.extend(
                    parse_treasure_tables(data.decode("utf-8-sig", errors="replace"))
                )
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        return tables

    # -- typed models --------------------------------------------------------

    @cached_property
    def items(self) -> NamedCollection[Item]:
        items = []
        templates_by_key = self.templates
        for entry in self.stats.by_type(*ITEM_TYPES):
            data = self._resolved_or_record(entry)
            if data is None:
                continue
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
        return self._collect(items)

    @cached_property
    def spells(self) -> NamedCollection[Spell]:
        return self._collect(
            Spell.from_stats(entry.name, data, *self._texts(data))
            for entry in self.stats.by_type(SPELL_TYPE)
            if (data := self._resolved_or_record(entry)) is not None
        )

    @cached_property
    def passives(self) -> NamedCollection[Passive]:
        return self._collect(
            Passive.from_stats(entry.name, data, *self._texts(data))
            for entry in self.stats.by_type(PASSIVE_TYPE)
            if (data := self._resolved_or_record(entry)) is not None
        )

    @cached_property
    def statuses(self) -> NamedCollection[Status]:
        return self._collect(
            Status.from_stats(entry.name, data, *self._texts(data))
            for entry in self.stats.by_type(STATUS_TYPE)
            if (data := self._resolved_or_record(entry)) is not None
        )

    # -- relationship graph ---------------------------------------------------

    def items_granting(self, relation: str, name: str) -> list[Item]:
        """Items whose ``relation`` ('passives'/'statuses'/'spells') includes
        ``name`` — the reverse edges of the item links.  The index is built
        once, lazily, from a single pass over the items."""
        return list(self._grants_index.get(relation, {}).get(name, ()))

    @cached_property
    def _grants_index(self) -> dict[str, dict[str, list[Item]]]:
        index: dict[str, dict[str, list[Item]]] = {
            "passives": {}, "statuses": {}, "spells": {},
        }
        for item in self.items:
            for relation, names in (
                ("passives", item.passive_names),
                ("statuses", item.status_names),
                ("spells", item.spell_names),
            ):
                for name in names:
                    index[relation].setdefault(name, []).append(item)
        return index

    # -- internals -----------------------------------------------------------

    def _resolved_or_record(self, entry) -> dict[str, str] | None:
        """Resolve a stats entry's inheritance; on failure (e.g. a genuine
        cycle) record a load issue and skip the entry instead of aborting
        the whole collection."""
        try:
            return self.stats.resolved(entry.name)
        except ValueError as exc:
            self.load_issues.append(
                LoadIssue(file=entry.source or "<stats>", error=f"{entry.name}: {exc}")
            )
            return None

    def _collect(self, objects) -> NamedCollection:
        collection = NamedCollection(objects)
        for obj in collection:
            obj._link(self)
        return collection

    def _texts(self, data: dict[str, str]) -> tuple[str, str]:
        return (
            self.localization.resolve(data.get("DisplayName")),
            self.localization.resolve(data.get("Description")),
        )

    def _iter_files(self, predicate):
        """Yield (name, bytes) for archived/extracted files matching predicate.

        Paks are visited in (priority, name) order — the engine's load
        order — so later, higher-priority archives override earlier ones
        and patch-layered stats resolve against the right base.
        """
        if self.extracted_dir is not None:
            for file in sorted(self.extracted_dir.rglob("*")):
                if not file.is_file():
                    continue
                rel = file.relative_to(self.extracted_dir).as_posix()
                if predicate(rel):
                    yield rel, file.read_bytes()
            return
        readers: list[PakReader] = []
        try:
            for pak_path in sorted(self.data_dir.rglob("*.pak")):
                try:
                    readers.append(PakReader(pak_path))
                except ValueError:
                    continue  # secondary archive part or foreign file
            readers.sort(key=lambda r: (r.header.priority, r.path.name))
            for reader in readers:
                for entry in reader:
                    if predicate(entry.name):
                        yield entry.name, reader.read(entry)
        finally:
            for reader in readers:
                reader.close()
