"""Repeatable measurements of the full pipeline against real game data.

Not a CI gate — a baseline.  ``run_benchmark`` times each pipeline stage
against whatever data source the :class:`~bg3forge.game.Game` points at
and reports counts plus peak memory, so optimization proposals can say
"this reduces RootTemplate parsing by 28% on the benchmark" instead of
relying on impressions (see CONTRIBUTING.md, design principle #5).

    from bg3forge import Game
    from bg3forge.benchmark import format_report, run_benchmark

    print(format_report(run_benchmark(Game())))

The CLI equivalent is ``bg3forge benchmark``.
"""

from __future__ import annotations

import platform
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .exporters import export_json
from .game import Game
from .pak import lz4compat
from .pak.reader import PakReader


@dataclass
class BenchmarkReport:
    environment: dict[str, str] = field(default_factory=dict)
    stages: list[tuple[str, float]] = field(default_factory=list)  # label, seconds
    counts: dict[str, int] = field(default_factory=dict)
    peak_rss_mb: float | None = None


def run_benchmark(game: Game | None = None, export_dir: str | Path | None = None) -> BenchmarkReport:
    """Time every pipeline stage.

    Pass a *fresh* ``Game`` (or none, to auto-locate the install): stages
    measure first-touch cost, so a Game whose collections are already
    cached will report near-zero times for the loading stages.  Exports
    go to ``export_dir`` or a temporary directory.
    """
    if game is None:
        game = Game()
    report = BenchmarkReport(environment=_environment(game))

    def timed(label: str, fn) -> None:
        start = time.perf_counter()
        fn()
        report.stages.append((label, time.perf_counter() - start))

    def read_pak_indexes() -> None:
        if game.data_dir is None:
            return
        entries = 0
        for pak_path in sorted(game.data_dir.rglob("*.pak")):
            try:
                with PakReader(pak_path) as pak:
                    entries += len(pak)
            except ValueError:
                continue
        report.counts["pak entries"] = entries

    def resolve_relationships() -> None:
        game.items_granting("passives", "")  # force the reverse index
        for item in game.items:
            item.passives, item.statuses, item.spells
            item.tags, item.owner_templates
        for progression in game.progressions:
            progression.passives, progression.removed_passives
            progression.spells, progression.selectable_spells
        game.progressions_granting_passive("")
        game.progressions_granting_spell("")
        game.progressions_offering_spell("")

    def export() -> None:
        target = Path(export_dir) if export_dir else Path(tempfile.mkdtemp(prefix="bg3forge-bench-"))
        for dataset in (
            "items", "spells", "passives", "statuses",
            "progressions", "spell_lists",
        ):
            export_json(getattr(game, dataset), target / f"{dataset}.json")

    def parse_compiled_stories() -> None:
        stories = [game.story.load(path) for path in game.story.paths]
        report.counts["compiled stories"] = len(stories)
        report.counts["story goals"] = sum(len(story.goals) for story in stories)
        report.counts["story databases"] = sum(
            len(story.databases) for story in stories
        )
        report.counts["story rules"] = sum(story.rule_count for story in stories)

    def parse_progressions() -> None:
        report.counts["progressions"] = len(game.progressions)
        report.counts["progression tables"] = len(game.progressions.table_ids)
        report.counts["spell lists"] = len(game.spell_lists)
        report.counts["progression passive grants"] = sum(
            len(record.passives_added) for record in game.progressions
        )
        report.counts["progression spell grants"] = sum(
            sum(len(spell_list.spell_names) for spell_list in record.added_spell_lists)
            for record in game.progressions
        )
        report.counts["progression spell choices"] = sum(
            sum(
                len(spell_list.spell_names)
                for spell_list in record.selectable_spell_lists
            )
            for record in game.progressions
        )

    timed("Read pak indexes", read_pak_indexes)
    timed("Parse stats", lambda: report.counts.__setitem__("stats entries", len(game.stats)))
    timed("Parse localization", lambda: report.counts.__setitem__("loca handles", len(game.localization)))
    timed("Parse root templates", lambda: report.counts.__setitem__("root templates", len(game.templates)))
    timed("Parse tags", lambda: report.counts.__setitem__("tags", len(game.tags)))
    timed("Parse atlases", lambda: report.counts.__setitem__("atlases", len(game.atlases)))
    # dialogs/timelines are indexed, not parsed — this measures the cheap half
    timed("Index dialogs", lambda: report.counts.__setitem__("dialogs indexed", len(game.dialogs)))
    timed("Index timelines", lambda: report.counts.__setitem__("timelines indexed", len(game.timelines)))
    def parse_journal() -> None:
        report.counts["quests"] = len(game.quests)
        report.counts["objectives"] = len(game.objectives)
        report.counts["quest categories"] = len(game.quest_categories)

    timed("Parse quests", parse_journal)
    timed("Index goals", lambda: report.counts.__setitem__("goals indexed", len(game.goals)))
    timed("Parse compiled stories", parse_compiled_stories)
    timed("Parse progressions", parse_progressions)
    timed("Build models", _build_models(game, report))
    timed("Resolve relationships", resolve_relationships)
    timed("Export JSON", export)

    report.peak_rss_mb = _peak_rss_mb()
    return report


def _build_models(game: Game, report: BenchmarkReport):
    def build() -> None:
        report.counts["items"] = len(game.items)
        report.counts["spells"] = len(game.spells)
        report.counts["passives"] = len(game.passives)
        report.counts["statuses"] = len(game.statuses)
        report.counts["characters"] = len(game.characters)
        report.counts["equipment sets"] = len(game.equipment)
    return build


def _environment(game: Game) -> dict[str, str]:
    if game.extracted_dir is not None:
        source = f"extracted tree: {game.extracted_dir}"
    else:
        paks = list(game.data_dir.rglob("*.pak"))
        total = sum(p.stat().st_size for p in paks)
        source = f"{game.data_dir} ({len(paks)} paks, {total / 1e9:.2f} GB)"
    return {
        "bg3forge": __version__,
        "Python": platform.python_version(),
        "OS": platform.platform(),
        "Native LZ4": "yes" if lz4compat.HAVE_NATIVE_LZ4 else "no (pure-Python fallback)",
        "Data source": source,
        "Language": game.language,
    }


def _peak_rss_mb() -> float | None:
    try:
        import resource
    except ImportError:  # Windows
        try:
            import psutil  # optional; present on many dev machines

            return psutil.Process().memory_info().peak_wset / 1e6
        except Exception:
            return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is KiB on Linux, bytes on macOS.
    return peak / 1e3 if sys.platform != "darwin" else peak / 1e6


def format_report(report: BenchmarkReport) -> str:
    lines = ["Environment", "-----------"]
    for key, value in report.environment.items():
        lines.append(f"{key}: {value}")
    lines += ["", "Results", "-------"]
    width = max(len(label) for label, _ in report.stages) + 4
    for label, seconds in report.stages:
        lines.append(f"{label + ' ':.<{width}} {seconds:6.2f} s")
    lines.append("")
    for key, value in report.counts.items():
        lines.append(f"{key + ' ':.<{width}} {value:>8,}")
    lines.append("")
    if report.peak_rss_mb is not None:
        lines.append(f"{'Peak RSS ':.<{width}} {report.peak_rss_mb:6.0f} MB")
    else:
        lines.append("Peak RSS: unavailable on this platform")
    return "\n".join(lines)
