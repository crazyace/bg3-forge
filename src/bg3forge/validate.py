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
    _is_roottemplate_file,
    _is_stats_file,
    _is_timeline_file,
    _is_treasure_file,
)
from .parsers.dialogs import parse_dialog
from .pak.reader import PakReader
from .parsers.lsf import is_lsf
from .parsers.lsj import is_lsj
from .parsers.localization import parse_loca
from .parsers.resource import parse_resource
from .parsers.roottemplates import parse_root_templates
from .parsers.stats import StatsCollection, parse_stats_document
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
        "paks", "pak_parts_skipped", "stats_files", "stats_entries",
        "stats_globals", "treasure_files", "treasure_tables", "loca_files",
        "loca_handles", "lsx_resources", "lsf_resources", "lsj_resources",
        "root_templates",
        "atlases", "dialogs", "dialog_nodes", "timelines", "files_skipped",
        "stats_resolved",
    ):
        counts[key] = 0

    stats = StatsCollection()
    pak_paths = sorted(Path(data_dir).rglob("*.pak"))
    for index, pak_path in enumerate(pak_paths, start=1):
        try:
            reader = PakReader(pak_path)
        except ValueError:
            counts["pak_parts_skipped"] += 1
            continue
        counts["paks"] += 1
        prefix = f"[{index}/{len(pak_paths)}] {pak_path.name}"
        if progress:
            progress(prefix)
        with reader:
            for position, entry in enumerate(reader, start=1):
                _validate_entry(reader, entry, report, stats)
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
    return report


def _validate_entry(
    reader: PakReader, entry, report: ValidationReport, stats: StatsCollection
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
            elif _is_timeline_file(name):
                counts["timelines"] += 1
        if check("resource", parse):
            counts[kind] += 1
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
        lines.append(f"{len(report.issues)} file(s) failed to parse:")
        for issue in report.issues[:max_issues]:
            lines.append(f"  [{issue.stage}] {issue.file}")
            lines.append(f"      {issue.error}")
        remaining = len(report.issues) - max_issues
        if remaining > 0:
            lines.append(f"  ... and {remaining} more")
    return "\n".join(lines)
