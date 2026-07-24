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
    CHARACTER_TYPE,
    ITEM_TYPES,
    PASSIVE_TYPE,
    SPELL_TYPE,
    STATUS_TYPE,
    Character,
    Item,
    NamedCollection,
    Passive,
    Spell,
    Status,
)
from .parsers.equipment import EquipmentSet, parse_equipment_sets
from .pak.reader import PakReader, file_is_lspk
from .parsers.localization import Localization
from .parsers.osiris import CompiledStory, parse_osiris
from .parsers.progressions import (
    Progression,
    ProgressionCollection,
    parse_progressions,
)
from .parsers.resource import parse_resource
from .parsers.roottemplates import RootTemplateIndex
from .parsers.classdescriptions import ClassDescription, parse_class_descriptions
from .parsers.races import Race, parse_races
from .parsers.spelllists import SpellList, parse_spell_lists
from .parsers.dialogs import Dialog, parse_dialog
from .parsers.goals import Goal, parse_goal
from .parsers.journal import (
    Marker,
    Objective,
    Quest,
    QuestCategory,
    parse_markers,
    parse_objectives,
    parse_quest_categories,
    parse_quests,
)
from .parsers.stats import StatsCollection
from .parsers.tags import TagRegistry
from .parsers.treasure import TreasureTable, parse_treasure_tables
from .assets.atlases import TextureAtlas, parse_atlas
from .assets.icons import IconError, IconExportResult, IconExtractor


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


class StoryIndex(ResourceIndex):
    """Lazy access to compiled Osiris ``story.div.osi`` databases."""

    def __init__(self, game: "Game"):
        super().__init__(game, _is_story_file, parse_osiris)

    @cached_property
    def goal_names(self) -> set[str]:
        """Goal names present across every compiled story variant."""
        names: set[str] = set()
        for path in self.paths:
            story: CompiledStory | None = self.get(path)
            if story is not None:
                names.update(story.goal_names)
        return names


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

    @cached_property
    def _by_stem(self) -> dict[str, list[str]]:
        """Lowercased file stem → timeline paths, built once."""
        index: dict[str, list[str]] = {}
        for name in self._sources:
            stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
            index.setdefault(stem, []).append(name)
        return index

    def for_dialog(self, dialog: Dialog) -> list[str]:
        """Timeline paths whose file stem matches the dialog's timeline id."""
        if not dialog.timeline_id:
            return []
        return list(self._by_stem.get(dialog.timeline_id.lower(), ()))


def _is_stats_file(name: str) -> bool:
    lowered = name.lower()
    return "/stats/generated/data/" in lowered and lowered.endswith(".txt")


def _is_treasure_file(name: str) -> bool:
    return name.lower().endswith("/stats/generated/treasuretable.txt")


def _is_roottemplate_file(name: str) -> bool:
    lowered = name.lower()
    return "/roottemplates/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_placed_item_file(name: str) -> bool:
    """Placed item definitions loaded into the runtime template map."""
    lowered = name.lower()
    return (
        ("/globals/" in lowered or "/levels/" in lowered)
        and "/items/" in lowered
        and lowered.endswith((".lsx", ".lsf"))
    )


def _is_atlas_file(name: str) -> bool:
    lowered = name.lower()
    return "/gui/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_tag_file(name: str) -> bool:
    lowered = name.lower()
    return "/tags/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_equipment_file(name: str) -> bool:
    return name.lower().endswith("/stats/generated/equipment.txt")


def _is_progression_file(name: str) -> bool:
    lowered = name.lower()
    return "/progressions/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_class_description_file(name: str) -> bool:
    lowered = name.lower()
    return "/classdescriptions/" in lowered and lowered.endswith((".lsx", ".lsf"))


def _is_race_file(name: str) -> bool:
    lowered = name.lower()
    return ("/races/" in lowered or "racedescription" in lowered) and lowered.endswith(
        (".lsx", ".lsf")
    )


def _is_spell_list_file(name: str) -> bool:
    lowered = name.lower()
    basename = lowered.rsplit("/", 1)[-1]
    return (
        "/lists/" in lowered
        and "spelllist" in basename
        and lowered.endswith((".lsx", ".lsf"))
    )


def _is_quest_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/journal/" in lowered and lowered.rsplit("/", 1)[-1].startswith(
        "quest_prototypes."
    )


def _is_objective_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/journal/" in lowered and lowered.rsplit("/", 1)[-1].startswith(
        "objective_prototypes."
    )


def _is_category_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/journal/" in lowered and lowered.rsplit("/", 1)[-1].startswith(
        "questcategory_prototypes."
    )


def _is_marker_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/journal/markers/" in lowered and lowered.endswith(
        (".lsx", ".lsf", ".lsj")
    )


def _is_goal_file(name: str) -> bool:
    lowered = name.lower()
    return "/story/rawfiles/goals/" in lowered and lowered.endswith(".txt")


def _is_story_file(name: str) -> bool:
    lowered = name.lower()
    return lowered == "story.div.osi" or lowered.endswith("/story/story.div.osi")


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
        self._reader_list: list[PakReader] | None = None
        self._extracted_files: list[tuple[str, Path]] | None = None

    # -- raw collections -----------------------------------------------------

    @cached_property
    def stats(self) -> StatsCollection:
        stats = StatsCollection()
        for name, data in self._iter_files(_is_stats_file, layer_same_path=True):
            try:
                stats.load_text(data.decode("utf-8-sig", errors="replace"), source=name)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        return stats

    @cached_property
    def localization(self) -> Localization:
        loca = self._load_language(self.language)
        if self.language.lower() != "english":
            # Not every handle is translated in every language; the game
            # falls back to English rather than showing nothing, and so
            # do we.  Only handles missing from the chosen language are
            # filled in, so translations always win.
            loca.merge_missing(self._load_language("English"))
        return loca

    def _load_language(self, language: str) -> Localization:
        loca = Localization()
        needle = f"/{language.lower()}/"
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
    def item_templates(self) -> RootTemplateIndex:
        """RootTemplates plus globally placed item objects.

        Entries under ``Mods/*/{Globals,Levels}/*/Items`` are the stable,
        story-facing UUIDs returned by Script Extender's runtime template API.
        Their ``TemplateName`` points to a RootTemplate; the returned index
        resolves that reference alongside normal ``ParentTemplateId``
        inheritance.
        """
        # RootTemplates are the largest files in the game; `templates`
        # has already parsed them, so start from a copy of that index and
        # layer only the placed-item files on top (they load after the
        # RootTemplates, preserving override order).
        index = self.templates.copy()
        for name, data in self._iter_files(_is_placed_item_file):
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

    def export_icons(
        self,
        names,
        output_dir: str | Path,
        format: str = "webp",
        overwrite: bool = False,
    ) -> IconExportResult:
        """Export selected atlas icons directly from installed game data.

        Atlas definitions and their DDS textures are both read from the pak
        set; no prior extraction step is required. Existing files are skipped
        unless ``overwrite`` is true. Names absent from every atlas, textures
        that cannot be located, and decode failures are reported in the
        returned :class:`IconExportResult` instead of aborting the batch.
        """
        wanted = list(dict.fromkeys(name for name in names if name))
        wanted_set = set(wanted)
        result = IconExportResult()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "." + format.lower()

        groups: list[tuple[TextureAtlas, list[str]]] = []
        matched: set[str] = set()
        for atlas in self.atlases:
            group = [name for name in atlas.icons if name in wanted_set and name not in matched]
            if group:
                groups.append((atlas, group))
                matched.update(group)
        result.missing.extend(name for name in wanted if name not in matched)

        texture_sources = self._locate_entries(
            lambda name: name.lower().endswith((".dds", ".png", ".webp"))
        )
        normalized_sources = [
            (name.replace("\\", "/").lower(), name, source)
            for name, source in texture_sources.items()
        ]

        for atlas, group in groups:
            pending = []
            for name in group:
                target = output_dir / f"{name}{suffix}"
                if target.exists() and not overwrite:
                    result.skipped.append(name)
                else:
                    pending.append(name)
            if not pending:
                continue

            texture_path = (atlas.texture_path or "").replace("\\", "/").lstrip("/")
            needle = texture_path.lower()
            candidates = [
                (name, source)
                for normalized, name, source in normalized_sources
                if needle and (normalized == needle or normalized.endswith("/" + needle))
            ]
            if not candidates:
                result.missing.extend(pending)
                result.errors[texture_path or "<missing atlas path>"] = "texture not found"
                continue

            archived_name, source = candidates[-1]
            try:
                extractor = IconExtractor(atlas, self._read_entry(archived_name, source))
                exported = extractor.export_all(output_dir, format=format, names=pending)
            except IconError as exc:
                result.missing.extend(pending)
                result.errors[texture_path] = str(exc)
                continue
            result.written.extend(exported.written)
            result.missing.extend(exported.missing)

        result.missing = list(dict.fromkeys(result.missing))
        return result

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
        # Lowercased on both sides: template attributes and tag files
        # disagree on UUID casing in retail data.
        return list(self._tag_index.get(uuid.lower(), ()))

    @cached_property
    def _tag_index(self) -> dict[str, list[Item]]:
        index: dict[str, list[Item]] = {}
        for item in self.items:
            for uuid in item.tag_ids:
                index.setdefault(uuid.lower(), []).append(item)
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
    def objectives(self) -> NamedCollection[Objective]:
        """Quest objectives with localized descriptions
        (``game.objectives["FOR_UnfortunateGnome_Approach"]``)."""
        objectives: list[Objective] = []
        for name, data in self._iter_files(_is_objective_file):
            try:
                objectives.extend(parse_objectives(parse_resource(data), source=name))
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        for objective in objectives:
            objective.description = self.localization.resolve(
                objective.description_handle
            )
        return self._collect(objectives)

    @cached_property
    def quest_categories(self) -> NamedCollection[QuestCategory]:
        """Journal categories with localized names, by CategoryID."""
        categories: list[QuestCategory] = []
        for name, data in self._iter_files(_is_category_file):
            try:
                categories.extend(
                    parse_quest_categories(parse_resource(data), source=name)
                )
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        for category in categories:
            category.description = self.localization.resolve(
                category.description_handle
            )
        return self._collect(categories)

    def objectives_for_quest(self, quest_id: str) -> list[Objective]:
        return list(self._objective_quest_index.get(quest_id, ()))

    @cached_property
    def _objective_quest_index(self) -> dict[str, list[Objective]]:
        index: dict[str, list[Objective]] = {}
        for objective in self.objectives:
            if objective.quest_id:
                index.setdefault(objective.quest_id, []).append(objective)
        return index

    def quests_in_category(self, category_id: str) -> list[Quest]:
        return list(self._quest_category_index.get(category_id, ()))

    @cached_property
    def _quest_category_index(self) -> dict[str, list[Quest]]:
        index: dict[str, list[Quest]] = {}
        for quest in self.quests:
            if quest.category_id:
                index.setdefault(quest.category_id, []).append(quest)
        return index

    def markers_by_id(self, marker_id: str) -> list[Marker]:
        """Quest markers whose MarkerID matches (objectives link this way)."""
        return list(self._marker_id_index.get(marker_id, ()))

    @cached_property
    def _marker_id_index(self) -> dict[str, list[Marker]]:
        index: dict[str, list[Marker]] = {}
        for marker in self.quest_markers:
            if marker.marker_id:
                index.setdefault(marker.marker_id, []).append(marker)
        return index

    @cached_property
    def goals(self) -> GoalIndex:
        """Lazy index of Osiris goal scripts (quest logic source)."""
        return GoalIndex(self)

    @cached_property
    def story(self) -> StoryIndex:
        """Lazy index of compiled Osiris story databases."""
        return StoryIndex(self)

    def uncompiled_goals(self) -> list[str]:
        """Source goal names absent from every compiled story variant."""
        source_names = set()
        for path in self.goals.paths:
            goal: Goal | None = self.goals.get(path)
            if goal is not None:
                source_names.add(goal.name)
        return sorted(source_names - self.story.goal_names)

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

    @cached_property
    def classes(self) -> NamedCollection[ClassDescription]:
        """Class and subclass descriptions, joined to the spell machinery.

        ``game.classes["Wizard"]`` resolves the class's learnable/preparable
        ``.spell_list``, its ``.progressions`` (via ``ProgressionTableUUID``),
        and ``.subclasses``/``.parent`` links.  Later records with the same
        UUID replace earlier ones in pak load order.
        """
        by_uuid: dict[str, ClassDescription] = {}
        for name, data in self._iter_files(_is_class_description_file):
            try:
                records = parse_class_descriptions(parse_resource(data), source=name)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
                continue
            for record in records:
                by_uuid[record.uuid] = record
        records = sorted(by_uuid.values(), key=lambda record: (record.name, record.uuid))
        for record in records:
            if record.display_name_handle:
                record.display_name = self.localization.resolve(
                    record.display_name_handle
                )
        return self._collect(records)

    @cached_property
    def races(self) -> NamedCollection[Race]:
        """Race and subrace records, joined like :attr:`classes`.

        ``game.races["Human"]`` resolves ``.parent``/``.subraces`` (the
        ``ParentGuid`` tree rooted at ``Humanoid``), ``.progressions`` via
        the race's table, and ``.tags``.  Later records with the same UUID
        replace earlier ones in pak load order.
        """
        by_uuid: dict[str, Race] = {}
        for name, data in self._iter_files(_is_race_file):
            try:
                records = parse_races(parse_resource(data), source=name)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
                continue
            for record in records:
                by_uuid[record.uuid] = record
        records = sorted(by_uuid.values(), key=lambda record: (record.name, record.uuid))
        for record in records:
            if record.display_name_handle:
                record.display_name = self.localization.resolve(
                    record.display_name_handle
                )
            if record.description_handle:
                record.description = self.localization.resolve(
                    record.description_handle
                )
        return self._collect(records)

    def spell_lists_containing(self, spell_name: str) -> list[SpellList]:
        """Every spell list carrying ``spell_name``.

        The practical query behind class-spell authoring: retail ships
        cumulative per-level lists, so a custom spell belongs in every list
        where its same-class, same-level siblings appear — e.g. all lists
        containing ``Target_MistyStep`` for a level-2 arcane spell.
        """
        return [
            spell_list
            for spell_list in self.spell_lists
            if spell_name in spell_list.spell_names
        ]

    @cached_property
    def spell_lists(self) -> NamedCollection[SpellList]:
        """Spell lists referenced by progression ``Add/SelectSpells``.

        Later records with the same UUID replace earlier ones, following the
        same pak load order used by the rest of :class:`Game`.
        """
        by_uuid: dict[str, SpellList] = {}
        for name, data in self._iter_files(_is_spell_list_file):
            try:
                records = parse_spell_lists(parse_resource(data), source=name)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
                continue
            for record in records:
                by_uuid[record.uuid] = record
        return self._collect(by_uuid[uuid] for uuid in sorted(by_uuid))

    @cached_property
    def progressions(self) -> ProgressionCollection:
        """Level progressions indexed by record UUID and grouped by table.

        Use ``game.progressions.by_table(table_uuid)`` for the ordered levels
        in one class/race table.  Automatic spell grants and player choices
        are exposed separately on each record.
        """
        by_uuid: dict[str, Progression] = {}
        for name, data in self._iter_files(_is_progression_file):
            try:
                records = parse_progressions(parse_resource(data), source=name)
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
                continue
            for record in records:
                by_uuid[record.uuid] = record
        records = sorted(
            by_uuid.values(),
            key=lambda record: (
                record.table_uuid,
                record.level,
                record.is_multiclass,
                record.uuid,
            ),
        )
        collection = ProgressionCollection(records)
        for record in collection:
            record._link(self)
        return collection

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
            template_icon = None
            if map_key:
                fields = templates_by_key.resolved(map_key)
                display = self.localization.resolve(fields.get("DisplayName"))
                description = self.localization.resolve(fields.get("Description"))
                template_icon = fields.get("Icon")
            item = Item.from_stats(
                entry.name,
                self.stats.resolved_type(entry.name),
                data,
                display_name=display,
                description=description,
                map_key=map_key,
            )
            if not item.icon and template_icon:
                # Stats entries without their own Icon inherit the root
                # template's, exactly like DisplayName/Description.
                item.icon = template_icon
            items.append(item)
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

    @cached_property
    def characters(self) -> NamedCollection[Character]:
        """NPC/creature stat blocks joined to their templates.

        Display names, archetype, and the equipment-set reference come
        from the root template whose ``Stats`` field names the entry.
        """
        characters = []
        for entry in self.stats.by_type(CHARACTER_TYPE):
            data = self._resolved_or_record(entry)
            if data is None:
                continue
            display = description = ""
            map_key = archetype = equipment_name = None
            owners = self.templates.by_stats(entry.name)
            if owners:
                map_key = owners[0].map_key
                fields = self.templates.resolved(map_key)
                display = self.localization.resolve(fields.get("DisplayName"))
                description = self.localization.resolve(fields.get("Description"))
                archetype = fields.get("Archetype")
                equipment_name = fields.get("Equipment")
            characters.append(
                Character.from_stats(
                    entry.name,
                    data,
                    display_name=display,
                    description=description,
                    map_key=map_key,
                    archetype=archetype,
                    equipment_name=equipment_name,
                )
            )
        return self._collect(characters)

    @cached_property
    def equipment(self) -> NamedCollection[EquipmentSet]:
        """Equipment sets by name (``game.equipment["EQP_Gith_Soldier"]``)."""
        sets: list[EquipmentSet] = []
        for name, data in self._iter_files(_is_equipment_file):
            try:
                sets.extend(
                    parse_equipment_sets(
                        data.decode("utf-8-sig", errors="replace"), source=name
                    )
                )
            except ValueError as exc:
                self.load_issues.append(LoadIssue(file=name, error=str(exc)))
        return NamedCollection(sets)

    def characters_with_passive(self, name: str) -> list[Character]:
        """Characters whose Passives include ``name`` (reverse edge)."""
        return list(self._character_passive_index.get(name, ()))

    @cached_property
    def _character_passive_index(self) -> dict[str, list[Character]]:
        index: dict[str, list[Character]] = {}
        for character in self.characters:
            for passive_name in character.passive_names:
                index.setdefault(passive_name, []).append(character)
        return index

    def progressions_granting_passive(self, name: str) -> list[Progression]:
        """Progression records whose ``PassivesAdded`` contains ``name``."""
        return list(self._progression_passive_index.get(name, ()))

    @cached_property
    def _progression_passive_index(self) -> dict[str, list[Progression]]:
        index: dict[str, list[Progression]] = {}
        for progression in self.progressions:
            for name in progression.passives_added:
                index.setdefault(name, []).append(progression)
        return index

    def progressions_granting_spell(self, name: str) -> list[Progression]:
        """Progressions that automatically grant ``name`` via AddSpells."""
        return list(self._progression_spell_index.get(name, ()))

    def progressions_offering_spell(self, name: str) -> list[Progression]:
        """Progressions that offer ``name`` via SelectSpells."""
        return list(self._progression_spell_choice_index.get(name, ()))

    @cached_property
    def _progression_spell_index(self) -> dict[str, list[Progression]]:
        return self._index_progression_spells("spells")

    @cached_property
    def _progression_spell_choice_index(self) -> dict[str, list[Progression]]:
        return self._index_progression_spells("selectable_spells")

    def _index_progression_spells(
        self, relation: str
    ) -> dict[str, list[Progression]]:
        index: dict[str, list[Progression]] = {}
        for progression in self.progressions:
            for spell in getattr(progression, relation):
                index.setdefault(spell.name, []).append(progression)
        return index

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

    def _iter_files(self, predicate, *, layer_same_path: bool = False):
        """Yield (name, bytes) for archived/extracted files matching predicate.

        Most resources use virtual-file semantics: a higher-priority archive
        replaces an earlier copy of the same path wholesale. Stats are the
        exception. Their loader consumes definitions from every package in
        load order, and a patch can re-ship the same path with only a partial
        self-``using`` layer. ``layer_same_path=True`` preserves those
        earlier definitions while retaining whole-file replacement for
        journals, templates, and other resource families.
        """
        if self.extracted_dir is not None:
            for rel, file in self._extracted_file_list():
                if predicate(rel):
                    yield rel, file.read_bytes()
            return

        if layer_same_path:
            for reader in self._open_readers():
                for entry in reader:
                    if predicate(entry.name):
                        yield entry.name, reader.read(entry)
            return

        winners: dict[str, tuple[PakReader, object]] = {}
        for reader in self._open_readers():
            for entry in reader:
                if predicate(entry.name):
                    winners[entry.name] = (reader, entry)
        for name, (reader, entry) in winners.items():
            yield name, reader.read(entry)

    def _extracted_file_list(self) -> list[tuple[str, Path]]:
        """Every file under ``extracted_dir`` as (posix-relative, path),
        walked and sorted once.  ~18 lazily-built collections each iterate
        this; before caching, each re-ran ``rglob('*')`` plus a per-file
        ``is_file()`` over the whole tree."""
        if self._extracted_files is None:
            self._extracted_files = [
                (file.relative_to(self.extracted_dir).as_posix(), file)
                for file in sorted(self.extracted_dir.rglob("*"))
                if file.is_file()
            ]
        return self._extracted_files

    def _open_readers(self) -> list[PakReader]:
        """All primary pak readers in (priority, name) load order.

        Opened once and cached: parsing a pak's file list is the
        expensive part (~2.3 s across a retail install), and every
        collection load and index build walks the same lists.  Before
        this cache, ten pipeline stages each paid that toll — the
        retail benchmark showed near-identical ~2.3 s costs for wildly
        different stages.  ``close()`` releases the handles.
        """
        if self._reader_list is None:
            readers: list[PakReader] = []
            for pak_path in sorted(self.data_dir.rglob("*.pak")):
                try:
                    readers.append(PakReader(pak_path))
                except ValueError as exc:
                    # Secondary archive parts (Textures_1.pak) and foreign
                    # files don't start with LSPK — skipping those is
                    # routine.  A file that *does* carry the signature is a
                    # real archive that failed to open (truncated download,
                    # interrupted patch): record it so `bg3forge validate`
                    # and doctor can surface it instead of silently
                    # loading without its data.
                    if file_is_lspk(pak_path):
                        self.load_issues.append(
                            LoadIssue(file=pak_path.name, error=str(exc))
                        )
                    continue
            readers.sort(key=lambda r: (r.header.priority, r.path.name))
            self._reader_list = readers
            for reader in readers:
                self._pak_readers[reader.path] = reader
        return self._reader_list

    def find_files(self, pattern: str) -> dict[str, Path]:
        """Archived paths matching ``pattern``, mapped to their source.

        A pattern containing any of ``*?[`` is treated as a shell-style
        glob (case-insensitive); otherwise it is a case-insensitive
        substring.  The value is the pak (or extracted file) the path
        lives in.  No file content is read — this is the public form of
        what ``bg3forge search`` does, so other tools need not reach for
        the private ``_locate_entries``.
        """
        import fnmatch

        needle = pattern.lower()
        if any(ch in needle for ch in "*?["):
            predicate = lambda n: fnmatch.fnmatch(n.lower(), needle)  # noqa: E731
        else:
            predicate = lambda n: needle in n.lower()  # noqa: E731
        return self._locate_entries(predicate)

    def _locate_entries(self, predicate) -> dict[str, Path]:
        """Map matching archived names to their source (pak or file) WITHOUT
        reading any content — the cheap half of indexed datasets."""
        sources: dict[str, Path] = {}
        if self.extracted_dir is not None:
            for rel, file in self._extracted_file_list():
                if predicate(rel):
                    sources[rel] = file
            return sources
        for reader in self._open_readers():
            for entry in reader:
                if predicate(entry.name):
                    sources[entry.name] = reader.path
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
        self._reader_list = None

    def __enter__(self) -> "Game":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self):  # pragma: no cover - interpreter-dependent timing
        try:
            self.close()
        except Exception:
            pass
