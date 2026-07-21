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
from .parsers.dialogs import Dialog, parse_dialog
from .parsers.goals import Goal, parse_goal
from .parsers.journal import Marker, Quest, parse_markers, parse_quests
from .parsers.stats import StatsCollection
from .parsers.tags import TagRegistry
from .parsers.treasure import TreasureTable, parse_treasure_tables
from .assets.atlases import TextureAtlas, parse_atlas


class GameNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadIssue:
    """A file that failed to parse while loading a collection."""

    file: str
    error: str


class ResourceIndex:
    """Lazy, indexed access to a family of archived resources.

    The phase-3 pattern for datasets too large to parse eagerly:
    building the index touches only the pak file lists; each resource is
    parsed on first access and cached.  Subclasses supply the file
    predicate and a ``loader(document_bytes, name)``.
    """

    def __init__(self, game: "Game", predicate, loader):
        self._game = game
        self._sources = game._locate_entries(predicate)
        self._loader = loader
        self._cache: dict[str, object] = {}

    def __len__(self) -> int:
        return len(self._sources)

    def __contains__(self, name: str) -> bool:
        return name in self._sources

    @property
    def paths(self) -> list[str]:
        return list(self._sources)

    def find(self, query: str) -> list[str]:
        """Archived paths whose name contains ``query`` (case-insensitive)."""
        needle = query.lower()
        return [name for name in self._sources if needle in name.lower()]

    def load(self, name: str):
        """Parse one resource (cached after the first call)."""
        if name not in self._cache:
            try:
                source = self._sources[name]
            except KeyError:
                raise KeyError(f"no indexed resource at {name!r}") from None
            data = self._game._read_entry(name, source)
            self._cache[name] = self._loader(data, name)
        return self._cache[name]

    def get(self, name: str):
        try:
            return self.load(name)
        except (KeyError, ValueError):
            return None


class DialogIndex(ResourceIndex):
    """Lazy dialog access::

        game.dialogs.find("Karlach")          # search archived paths, free
        dialog = game.dialogs.load(path)      # parses this one file
        game.dialogs.lines(path)              # (speaker, localized text) pairs
    """

    def __init__(self, game: "Game"):
        super().__init__(
            game,
            _is_dialog_file,
            lambda data, name: parse_dialog(parse_resource(data), source=name),
        )

    def lines(self, name: str) -> list[tuple[int | None, str]]:
        """(speaker index, localized text) for every spoken line, in
        graph walk order.  Lines whose handles have no localization are
        skipped."""
        dialog: Dialog = self.load(name)
        result = []
        walk = list(dialog.walk()) or dialog.nodes
        for node in walk:
            for handle, _version in node.text_handles:
                text = self._game.localization.resolve(handle)
                if text:
                    result.append((node.speaker, text))
        return result


class GoalIndex(ResourceIndex):
    """Lazy access to Osiris goal scripts (quest logic source)."""

    def __init__(self, game: "Game"):
        super().__init__(
            game,
            _is_goal_file,
            lambda data, name: parse_goal(
                data.decode("utf-8-sig", errors="replace"), source=name
            ),
        )


class TimelineIndex(ResourceIndex):
    """Lazy access to timeline (cinematic scene) resources.

    Timelines are the cinematic side of dialogs; a dialog's
    ``timeline_id`` names the timeline file that stages it.  ``load``
    returns the raw node-tree document — the timeline internals are not
    modeled yet, but existence, counts, and dialog↔timeline linkage are.
    """

    def __init__(self, game: "Game"):
        super().__init__(
            game, _is_timeline_file, lambda data, name: parse_resource(data)
        )

    def for_dialog(self, dialog: Dialog) -> list[str]:
        """Timeline paths whose file stem matches the dialog's timeline id."""
        if not dialog.timeline_id:
            return []
        stem = dialog.timeline_id.lower()
        return [
            name
            for name in self._sources
            if name.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower() == stem
        ]


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


def _is_tag_file(name: str) -> bool:
    lowered = name.lower()
    return "/tags/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_quest_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/journal/" in lowered and lowered.rsplit("/", 1)[-1].startswith(
        "quest_prototypes."
    )


def _is_marker_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/journal/markers/" in lowered and lowered.endswith(
        (".lsx", ".lsf", ".lsj")
    )


def _is_goal_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/rawfiles/goals/" in lowered and lowered.endswith(".txt")


def _is_timeline_file(name: str) -> bool:
    lowered = name.lower()
    return "/timeline/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_dialog_file(name: str) -> bool:
    """The authoritative shipped dialogs used by :class:`DialogIndex`.

    Retail ships every dialog twice — binary under ``DialogsBinary/``
    and editor-side ``.lsj`` under ``Dialogs/`` — so the index covers
    only the binary tree to avoid listing each dialog twice.
    """
    lowered = name.lower()
    return "/story/dialogsbinary/" in lowered and lowered.endswith(
        (".lsx", ".lsf", ".lsj")
    )


def _is_editor_dialog_file(name: str) -> bool:
    """Editor-side duplicates under ``Story/Dialogs/`` (mostly ``.lsj``);
    validated as dialogs but excluded from the index."""
    lowered = name.lower()
    if not lowered.endswith((".lsx", ".lsf", ".lsj")):
        return False
    if "/scriptflags/" in lowered or "/dialogvariables/" in lowered:
        # Registry files that live under Story/Dialogs/ but aren't
        # dialog resources (verified against retail: 7 such files).
        return False
    return "/story/dialogs/" in lowered


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
    def tags(self) -> TagRegistry:
        """The tag registry, with display strings already localized.

        Lookup by UUID or engine name: ``game.tags["PALADIN"]``.
        """
        registry = TagRegistry()
        for name, data in self._iter_files(_is_tag_file):
            try:
                registry.add_document(parse_resource(data))
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        for tag in registry:
            tag.display_name = self.localization.resolve(tag.display_name_handle)
            tag.display_description = self.localization.resolve(
                tag.display_description_handle
            )
            tag._link(self)
        return registry

    def items_with_tag(self, tag_key: str) -> list[Item]:
        """Items whose template chain carries the tag (UUID or name)."""
        tag = self.tags.get(tag_key)
        uuid = tag.uuid if tag is not None else tag_key
        return list(self._tag_index.get(uuid, ()))

    @cached_property
    def _tag_index(self) -> dict[str, list[Item]]:
        index: dict[str, list[Item]] = {}
        for item in self.items:
            for uuid in item.tag_ids:
                index.setdefault(uuid, []).append(item)
        return index

    @cached_property
    def dialogs(self) -> DialogIndex:
        """Lazy dialog index — cheap to build, parses per file on access."""
        return DialogIndex(self)

    @cached_property
    def timelines(self) -> TimelineIndex:
        """Lazy timeline (cinematic) index; see ``TimelineIndex.for_dialog``."""
        return TimelineIndex(self)

    @cached_property
    def quests(self) -> NamedCollection[Quest]:
        """The quest catalog with localized titles and step descriptions.

        Lookup by quest id: ``game.quests["PLA_ZhentShipment"]``.
        """
        quests: list[Quest] = []
        for name, data in self._iter_files(_is_quest_file):
            try:
                quests.extend(parse_quests(parse_resource(data), source=name))
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        for quest in quests:
            quest.title = self.localization.resolve(quest.title_handle)
            for step in quest.steps:
                step.description = self.localization.resolve(step.description_handle)
        return self._collect(quests)

    @cached_property
    def quest_markers(self) -> list[Marker]:
        """Quest map markers with localized display text."""
        markers: list[Marker] = []
        for name, data in self._iter_files(_is_marker_file):
            try:
                markers.extend(parse_markers(parse_resource(data), source=name))
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        for marker in markers:
            marker.display_text = self.localization.resolve(marker.display_text_handle)
        return markers

    @cached_property
    def goals(self) -> GoalIndex:
        """Lazy index of Osiris goal scripts (quest logic source)."""
        return GoalIndex(self)

    def goals_for_quest(self, quest_id: str) -> list[str]:
        """Goal script paths whose logic references the quest (reverse edge)."""
        return list(self._goal_quest_index.get(quest_id, ()))

    @cached_property
    def _goal_quest_index(self) -> dict[str, list[str]]:
        """quest id → goal paths.  Parses every goal once; they are small
        text files, and the index is only built on first use."""
        index: dict[str, list[str]] = {}
        for path in self.goals.paths:
            goal: Goal | None = self.goals.get(path)
            if goal is None:
                continue
            for quest_id in goal.quest_ids:
                index.setdefault(quest_id, []).append(path)
        return index

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
        readers = self._open_readers()
        try:
            for reader in readers:
                for entry in reader:
                    if predicate(entry.name):
                        yield entry.name, reader.read(entry)
        finally:
            for reader in readers:
                reader.close()

    def _open_readers(self) -> list[PakReader]:
        """All primary pak readers in (priority, name) load order."""
        readers: list[PakReader] = []
        for pak_path in sorted(self.data_dir.rglob("*.pak")):
            try:
                readers.append(PakReader(pak_path))
            except ValueError:
                continue  # secondary archive part or foreign file
        readers.sort(key=lambda r: (r.header.priority, r.path.name))
        return readers

    def _locate_entries(self, predicate) -> dict[str, Path]:
        """Map matching archived names to their source (pak or file) WITHOUT
        reading any content — the cheap half of indexed datasets."""
        sources: dict[str, Path] = {}
        if self.extracted_dir is not None:
            for file in sorted(self.extracted_dir.rglob("*")):
                if not file.is_file():
                    continue
                rel = file.relative_to(self.extracted_dir).as_posix()
                if predicate(rel):
                    sources[rel] = file
            return sources
        readers = self._open_readers()
        try:
            for reader in readers:
                for entry in reader:
                    if predicate(entry.name):
                        sources[entry.name] = reader.path
        finally:
            for reader in readers:
                reader.close()
        return sources

    def _read_entry(self, name: str, source: Path) -> bytes:
        """Read one archived entry located by :meth:`_locate_entries`.

        Readers are cached per pak: opening one means parsing the whole
        archive file list, which is far too expensive to repeat per entry
        (reading ~1,000 goal scripts used to reopen Gustav.pak ~1,000
        times).  Call :meth:`close` (or use the Game as a context
        manager) to release the handles early; they are also released
        when the Game is garbage collected.
        """
        if self.extracted_dir is not None:
            return source.read_bytes()
        reader = self._pak_readers.get(source)
        if reader is None:
            reader = self._pak_readers[source] = PakReader(source)
        return reader.read(name)

    @cached_property
    def _pak_readers(self) -> dict[Path, PakReader]:
        return {}

    def close(self) -> None:
        """Release cached pak readers (safe to call more than once)."""
        for reader in self._pak_readers.values():
            reader.close()
        self._pak_readers.clear()

    def __enter__(self) -> "Game":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self):  # pragma: no cover - interpreter-dependent timing
        try:
            self.close()
        except Exception:
            pass
