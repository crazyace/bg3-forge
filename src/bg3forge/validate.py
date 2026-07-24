"""Format-coverage validation sweep over a game data directory.

``validate_data`` walks every pak, tries to parse every file whose format
BG3 Forge claims to understand, and reports what it saw — counts on
success, precise per-file errors on failure.  Run it against a retail
install to find out which format assumptions actually hold::

    report = validate_data(game_data_dir)
    report.ok            # True when every recognized file parsed
    report.counts        # {"paks": 34, "stats_entries": 21042, ...}
    report.issues        # [ValidationIssue(file=..., stage=..., error=...)]

The CLI equivalent is ``bg3forge validate``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .assets.atlases import parse_atlas
from .game import (
    _is_atlas_file,
    _is_dialog_file,
    _is_editor_dialog_file,
    _is_equipment_file,
    _is_class_description_file,
    _is_goal_file,
    _is_race_file,
    _is_category_file,
    _is_marker_file,
    _is_objective_file,
    _is_progression_file,
    _is_quest_file,
    _is_roottemplate_file,
    _is_spell_list_file,
    _is_stats_file,
    _is_story_file,
    _is_timeline_file,
    _is_treasure_file,
)
from .models import PASSIVE_TYPE, SPELL_TYPE
from .parsers.equipment import parse_equipment_sets
from .parsers.goals import parse_goal
from .parsers.journal import (
    parse_markers,
    parse_objectives,
    parse_quest_categories,
    parse_quests,
)
from .parsers.dialogs import parse_dialog
from .pak.reader import PakReader, file_is_lspk
from .parsers.lsf import is_lsf
from .parsers.lsj import is_lsj
from .parsers.localization import parse_loca
from .parsers.osiris import parse_osiris
from .parsers.classdescriptions import parse_class_descriptions
from .parsers.races import parse_races
from .parsers.progressions import Progression, parse_progressions
from .parsers.resource import parse_resource
from .parsers.roottemplates import parse_root_templates
from .parsers.stats import StatsCollection, parse_stats_document
from .parsers.spelllists import SpellList, parse_spell_lists
from .parsers.treasure import parse_treasure_tables


@dataclass(frozen=True)
class ValidationIssue:
    file: str
    stage: str
    error: str


@dataclass
class ValidationReport:
    counts: dict[str, int] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_data(
    data_dir: str | Path,
    progress: Callable[[str], None] | None = None,
) -> ValidationReport:
    """Parse every recognized file in every pak under ``data_dir``.

    ``progress``, when given, receives short human-readable status lines
    ("[3/30] Gustav.pak — 12,000 files, 4 issues") as the sweep advances;
    the CLI renders them on stderr when attached to a terminal.
    """
    report = ValidationReport()
    counts = report.counts
    for key in (
        "paks", "paks_corrupt", "pak_parts_skipped", "stats_files", "stats_entries",
        "stats_globals", "treasure_files", "treasure_tables", "loca_files",
        "loca_handles", "lsx_resources", "lsf_resources", "lsj_resources",
        "root_templates",
        "atlases", "dialogs", "dialog_nodes", "timelines", "quests",
        "quest_steps", "quest_markers", "objectives", "quest_categories",
        "goals", "goal_quest_refs",
        "progression_files", "progressions", "progression_tables",
        "progression_passive_grants", "progression_passive_removals",
        "progression_passives_missing", "progression_spell_list_grants",
        "progression_spell_list_choices", "progression_spell_lists_missing",
        "spell_list_files", "spell_lists", "spell_list_spells",
        "spell_list_spells_missing", "class_descriptions", "races",
        "compiled_stories", "story_functions", "story_databases",
        "story_goals", "story_rules", "source_goals_compiled",
        "source_goals_missing",
        "equipment_files", "equipment_sets", "files_skipped",
        "stats_resolved",
    ):
        counts[key] = 0

    stats = StatsCollection()
    source_goal_names: set[str] = set()
    compiled_goal_names: set[str] = set()
    progressions: dict[str, Progression] = {}
    spell_lists: dict[str, SpellList] = {}
    pak_paths = sorted(Path(data_dir).rglob("*.pak"))
    for index, pak_path in enumerate(pak_paths, start=1):
        try:
            reader = PakReader(pak_path)
        except ValueError as exc:
            # Secondary archive parts and foreign files carry no LSPK
            # signature — skipping them is routine.  A file that *does*
            # is a damaged archive: exactly what a validation sweep
            # exists to surface, so it must fail the report, not hide
            # in the skip counter.
            if file_is_lspk(pak_path):
                counts["paks_corrupt"] += 1
                report.issues.append(
                    ValidationIssue(file=pak_path.name, stage="pak", error=str(exc))
                )
            else:
                counts["pak_parts_skipped"] += 1
            continue
        counts["paks"] += 1
        prefix = f"[{index}/{len(pak_paths)}] {pak_path.name}"
        if progress:
            progress(prefix)
        with reader:
            for position, entry in enumerate(reader, start=1):
                _validate_entry(
                    reader,
                    entry,
                    report,
                    stats,
                    source_goal_names,
                    compiled_goal_names,
                    progressions,
                    spell_lists,
                )
                if progress and position % 5000 == 0:
                    progress(
                        f"{prefix} — {position:,} files, {len(report.issues)} issues"
                    )

    # Cross-file phase: entries reference each other across paks, so
    # inheritance can only be checked once everything is loaded.
    if progress:
        progress(f"resolving inheritance for {len(stats):,} stats entries")
    for entry in stats:
        try:
            stats.resolved(entry.name)
            counts["stats_resolved"] += 1
        except Exception as exc:  # noqa: BLE001
            report.issues.append(
                ValidationIssue(
                    file=entry.source or "<stats>",
                    stage="stats-resolve",
                    error=f"{entry.name}: {type(exc).__name__}: {exc}",
                )
            )

    if counts["compiled_stories"]:
        missing = sorted(source_goal_names - compiled_goal_names)
        counts["source_goals_compiled"] = len(source_goal_names) - len(missing)
        counts["source_goals_missing"] = len(missing)
        if missing:
            preview = ", ".join(missing[:20])
            if len(missing) > 20:
                preview += f", ... ({len(missing) - 20} more)"
            report.issues.append(
                ValidationIssue(
                    file="<compiled stories>",
                    stage="story-crosscheck",
                    error=f"{len(missing)} source goal(s) absent: {preview}",
                )
            )

    passive_names = {entry.name for entry in stats.by_type(PASSIVE_TYPE)}
    spell_names = {entry.name for entry in stats.by_type(SPELL_TYPE)}
    counts["progression_tables"] = len(
        {record.table_uuid for record in progressions.values() if record.table_uuid}
    )
    counts["progression_passive_grants"] = sum(
        len(record.passives_added) for record in progressions.values()
    )
    counts["progression_passive_removals"] = sum(
        len(record.passives_removed) for record in progressions.values()
    )
    missing_passives = [
        name
        for record in progressions.values()
        for name in (*record.passives_added, *record.passives_removed)
        if name not in passive_names
    ]
    counts["progression_passives_missing"] = len(missing_passives)
    _record_missing_references(
        report,
        stage="progression-passives",
        file="<progressions>",
        values=missing_passives,
        kind="passive",
    )
    counts["progression_spell_list_grants"] = sum(
        len(record.added_spell_list_ids) for record in progressions.values()
    )
    counts["progression_spell_list_choices"] = sum(
        len(record.selectable_spell_list_ids) for record in progressions.values()
    )
    missing_progression_spell_lists = [
        uuid
        for record in progressions.values()
        for uuid in (*record.added_spell_list_ids, *record.selectable_spell_list_ids)
        if uuid not in spell_lists
    ]
    counts["progression_spell_lists_missing"] = len(missing_progression_spell_lists)
    _record_missing_references(
        report,
        stage="progression-spell-lists",
        file="<progressions>",
        values=missing_progression_spell_lists,
        kind="spell-list",
    )
    counts["spell_list_spells"] = sum(
        len(spell_list.spell_names) for spell_list in spell_lists.values()
    )
    missing_spell_list_spells = [
        name
        for spell_list in spell_lists.values()
        for name in spell_list.spell_names
        if name not in spell_names
    ]
    counts["spell_list_spells_missing"] = len(missing_spell_list_spells)
    _record_missing_references(
        report,
        stage="spell-list-spells",
        file="<spell lists>",
        values=missing_spell_list_spells,
        kind="spell",
    )
    return report


def _record_missing_references(
    report: ValidationReport,
    *,
    stage: str,
    file: str,
    values: list[str],
    kind: str,
) -> None:
    """Turn unresolved relationship counts into validation failures."""
    if not values:
        return
    unique = sorted(set(values))
    preview = ", ".join(unique[:20])
    if len(unique) > 20:
        preview += f", ... ({len(unique) - 20} more)"
    report.issues.append(
        ValidationIssue(
            file=file,
            stage=stage,
            error=(
                f"{len(values)} unresolved {kind} reference(s) across "
                f"{len(unique)} unique value(s): {preview}"
            ),
        )
    )


def _validate_entry(
    reader: PakReader,
    entry,
    report: ValidationReport,
    stats: StatsCollection,
    source_goal_names: set[str],
    compiled_goal_names: set[str],
    progressions: dict[str, Progression],
    spell_lists: dict[str, SpellList],
) -> None:
    name = entry.name
    lowered = name.lower()
    counts = report.counts

    def check(stage: str, fn) -> bool:
        try:
            fn(reader.read(entry))
            return True
        except Exception as exc:  # noqa: BLE001 - every failure is the payload
            report.issues.append(
                ValidationIssue(file=name, stage=stage, error=f"{type(exc).__name__}: {exc}")
            )
            return False

    if _is_stats_file(name):
        def parse(data):
            document = parse_stats_document(
                data.decode("utf-8-sig", errors="replace"), source=name
            )
            counts["stats_entries"] += len(document.entries)
            counts["stats_globals"] += len(document.globals)
            for stats_entry in document.entries:
                stats.add(stats_entry)
        if check("stats", parse):
            counts["stats_files"] += 1
    elif _is_treasure_file(name):
        def parse(data):
            tables = parse_treasure_tables(data.decode("utf-8-sig", errors="replace"))
            counts["treasure_tables"] += len(tables)
        if check("treasure", parse):
            counts["treasure_files"] += 1
    elif _is_equipment_file(name):
        def parse(data):
            sets = parse_equipment_sets(
                data.decode("utf-8-sig", errors="replace"), source=name
            )
            counts["equipment_sets"] += len(sets)
        if check("equipment", parse):
            counts["equipment_files"] += 1
    elif _is_goal_file(name):
        def parse(data):
            goal = parse_goal(data.decode("utf-8-sig", errors="replace"), source=name)
            counts["goal_quest_refs"] += len(goal.quest_ids)
            source_goal_names.add(goal.name)
        if check("goal", parse):
            counts["goals"] += 1
    elif _is_story_file(name):
        def parse(data):
            story = parse_osiris(data, source=name)
            counts["story_functions"] += len(story.functions)
            counts["story_databases"] += len(story.databases)
            counts["story_goals"] += len(story.goals)
            counts["story_rules"] += story.rule_count
            compiled_goal_names.update(story.goal_names)
        if check("story", parse):
            counts["compiled_stories"] += 1
    elif lowered.endswith(".loca"):
        def parse(data):
            counts["loca_handles"] += len(parse_loca(data))
        if check("loca", parse):
            counts["loca_files"] += 1
    elif lowered.endswith((".lsx", ".lsf", ".lsj")):
        kind = "lsx_resources"

        def parse(data):
            nonlocal kind
            if is_lsf(data):
                kind = "lsf_resources"
            elif is_lsj(data):
                kind = "lsj_resources"
            document = parse_resource(data)
            if _is_roottemplate_file(name):
                counts["root_templates"] += len(parse_root_templates(document))
            elif _is_atlas_file(name) and parse_atlas(document).icons:
                counts["atlases"] += 1
            elif _is_dialog_file(name) or _is_editor_dialog_file(name):
                dialog = parse_dialog(document, source=name)
                counts["dialogs"] += 1
                counts["dialog_nodes"] += len(dialog.nodes)
            elif _is_quest_file(name):
                quests = parse_quests(document, source=name)
                counts["quests"] += len(quests)
                counts["quest_steps"] += sum(len(q.steps) for q in quests)
            elif _is_marker_file(name):
                counts["quest_markers"] += len(parse_markers(document, source=name))
            elif _is_objective_file(name):
                counts["objectives"] += len(parse_objectives(document, source=name))
            elif _is_category_file(name):
                counts["quest_categories"] += len(
                    parse_quest_categories(document, source=name)
                )
            elif _is_progression_file(name):
                records = parse_progressions(document, source=name)
                counts["progressions"] += len(records)
                for record in records:
                    progressions[record.uuid] = record
            elif _is_spell_list_file(name):
                records = parse_spell_lists(document, source=name)
                counts["spell_lists"] += len(records)
                for record in records:
                    spell_lists[record.uuid] = record
            elif _is_class_description_file(name):
                counts["class_descriptions"] += len(
                    parse_class_descriptions(document, source=name)
                )
            elif _is_race_file(name):
                counts["races"] += len(parse_races(document, source=name))
            elif _is_timeline_file(name):
                counts["timelines"] += 1
        if check("resource", parse):
            counts[kind] += 1
            if _is_progression_file(name):
                counts["progression_files"] += 1
            elif _is_spell_list_file(name):
                counts["spell_list_files"] += 1
    else:
        counts["files_skipped"] += 1


def format_report(report: ValidationReport, max_issues: int = 20) -> str:
    lines = ["Coverage", "--------"]
    for key, value in report.counts.items():
        label = key.replace("_", " ")
        lines.append(f"{label:<24}{value:>10,}")
    lines.append("")
    if report.ok:
        lines.append("OK: every recognized file parsed cleanly.")
    else:
        lines.append(f"{len(report.issues)} validation issue(s):")
        for issue in report.issues[:max_issues]:
            lines.append(f"  [{issue.stage}] {issue.file}")
            lines.append(f"      {issue.error}")
        remaining = len(report.issues) - max_issues
        if remaining > 0:
            lines.append(f"  ... and {remaining} more")
    return "\n".join(lines)
