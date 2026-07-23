"""Lint a mod ``.pak`` for internal consistency before you ship it.

Where :func:`bg3forge.validate.validate_data` checks that a whole install
*parses*, ``lint_mod`` checks that a single mod is *coherent*: its files
parse, its UUIDs are well-formed, the localization handles it references
have text, and — when the base game is supplied via ``data_dir`` — its
``using`` chains and equip references actually resolve.

These are the mistakes that ship broken mods: a ``DisplayName`` that
renders as a raw ``h…`` handle, a ``using`` pointing at a stat that does
not exist, a template ``Stats`` binding with no matching entry.

A mod is *not* self-contained — it references base-game stats, passives,
statuses, and spells. So reference checks (``using`` targets, equip
references) only run when ``data_dir`` points at an install to resolve
against; without it they are reported as skipped, not failed. Format and
in-mod handle checks always run.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .game import (
    Game,
    _is_roottemplate_file,
    _is_stats_file,
)
from .parsers.localization import Localization
from .parsers.resource import parse_resource
from .parsers.roottemplates import RootTemplateIndex, parse_root_templates
from .parsers.stats import StatsCollection, StatsEntry, parse_stats_document
from .pak.reader import PakReader

ERROR = "error"
WARNING = "warning"
INFO = "info"

_UNLOCK_SPELL_RE = re.compile(r"UnlockSpell\(\s*([^),\s]+)")


@dataclass(frozen=True)
class LintFinding:
    severity: str  # ERROR / WARNING / INFO
    category: str
    message: str
    file: str | None = None


@dataclass
class LintReport:
    findings: list[LintFinding] = field(default_factory=list)

    def add(self, severity: str, category: str, message: str, file: str | None = None) -> None:
        self.findings.append(LintFinding(severity, category, message, file))

    @property
    def errors(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        """True when nothing is broken (warnings and info are allowed)."""
        return not self.errors


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _handle_only(value: str | None) -> str | None:
    """Strip a ``;version`` suffix from a stats DisplayName/Description
    value, leaving the bare ``h…`` handle (or None)."""
    if not value:
        return None
    return value.split(";", 1)[0].strip() or None


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


def lint_mod(
    pak_path: str | Path,
    base: Game | str | Path | None = None,
    language: str = "English",
) -> LintReport:
    """Check a mod ``.pak`` for internal consistency.

    With ``base`` — a :class:`~bg3forge.game.Game` over an install, or a
    path to its ``Data`` directory — the mod is resolved against the base
    game, so ``using`` chains and equip references are verified. Without
    it those reference checks are skipped (a mod is not self-contained).
    """
    report = LintReport()

    if base is not None and not isinstance(base, Game):
        base = Game(data_dir=base, language=language)

    # Base game, if provided.  Its own load issues are not the mod's fault,
    # so they are not reported here.
    base_stats: StatsCollection | None = None
    base_loca: Localization | None = None
    base_templates: RootTemplateIndex | None = None
    if base is not None:
        base_stats = base.stats
        base_loca = base.localization
        base_templates = base.templates

    # Merged views: base first, then the mod layered on top.  These are
    # the throwaway base collections (mutating them is fine for a one-shot
    # lint) or fresh ones when no base was supplied.
    stats = base_stats if base_stats is not None else StatsCollection()
    loca = base_loca if base_loca is not None else Localization()
    templates = base_templates if base_templates is not None else RootTemplateIndex()

    mod_stats: list[StatsEntry] = []
    mod_templates: list = []

    with PakReader(pak_path) as pak:
        for entry in pak:
            name = entry.name
            try:
                data = pak.read(entry)
            except ValueError as exc:
                report.add(ERROR, "read", f"could not read entry: {exc}", name)
                continue

            if _is_stats_file(name):
                try:
                    document = parse_stats_document(
                        data.decode("utf-8-sig", errors="replace"), source=name
                    )
                except ValueError as exc:
                    report.add(ERROR, "parse", f"stats file does not parse: {exc}", name)
                    continue
                for stat_entry in document.entries:
                    stats.add(stat_entry)
                    mod_stats.append(stat_entry)
            elif _is_roottemplate_file(name) or name.lower().endswith((".lsx", ".lsf")):
                try:
                    document = parse_resource(data)
                except ValueError as exc:
                    report.add(ERROR, "parse", f"resource does not parse: {exc}", name)
                    continue
                if _is_roottemplate_file(name):
                    parsed = parse_root_templates(document)
                    templates.add_document(document)
                    mod_templates.extend(parsed)
            elif name.lower().endswith(".loca"):
                try:
                    loca.load_bytes(data)
                except ValueError as exc:
                    report.add(ERROR, "parse", f"localization does not parse: {exc}", name)

    _check_uuids(report, mod_templates)
    _check_handles(report, mod_stats, mod_templates, loca)
    _check_references(report, mod_stats, mod_templates, stats, have_base=base is not None)

    if base is None:
        report.add(
            INFO, "scope",
            "reference checks (using chains, equip references) were skipped; "
            "pass --data-dir <install>/Data to resolve them against the base game",
        )
    return report


def _check_uuids(report: LintReport, mod_templates: list) -> None:
    for template in mod_templates:
        for label, value in (
            ("MapKey", template.map_key),
            ("ParentTemplateId", template.parent_id),
            ("TemplateName", template.template_name),
        ):
            if value and not _looks_like_uuid(value):
                report.add(
                    ERROR, "uuid",
                    f"template {template.name or template.map_key!r}: {label} "
                    f"{value!r} is not a valid UUID",
                )


def _check_handles(
    report: LintReport,
    mod_stats: list[StatsEntry],
    mod_templates: list,
    loca: Localization,
) -> None:
    def check(handle: str | None, owner: str, kind: str) -> None:
        handle = _handle_only(handle)
        if handle and handle.startswith("h") and not loca.resolve(handle):
            report.add(
                WARNING, "handle",
                f"{owner}: {kind} handle {handle!r} has no localization entry "
                "(it will render as a raw handle in game)",
            )

    for entry in mod_stats:
        check(entry.get("DisplayName"), f"stats {entry.name!r}", "DisplayName")
        check(entry.get("Description"), f"stats {entry.name!r}", "Description")
    for template in mod_templates:
        owner = f"template {template.name or template.map_key!r}"
        check(template.display_name_handle, owner, "DisplayName")
        check(template.description_handle, owner, "Description")


def _check_references(
    report: LintReport,
    mod_stats: list[StatsEntry],
    mod_templates: list,
    stats: StatsCollection,
    have_base: bool,
) -> None:
    # Without the base game, every base-referencing name would flag; only
    # run these when there is something to resolve against.
    if not have_base:
        return

    for entry in mod_stats:
        if entry.using and entry.using != entry.name and entry.using not in stats:
            report.add(
                ERROR, "using",
                f"stats {entry.name!r}: using {entry.using!r} does not exist",
            )
        for passive in _split_list(entry.get("PassivesOnEquip")):
            if passive not in stats:
                report.add(
                    WARNING, "reference",
                    f"stats {entry.name!r}: PassivesOnEquip {passive!r} not found",
                )
        for status in _split_list(entry.get("StatusOnEquip")):
            if status not in stats:
                report.add(
                    WARNING, "reference",
                    f"stats {entry.name!r}: StatusOnEquip {status!r} not found",
                )
        for spell in _UNLOCK_SPELL_RE.findall(entry.get("Boosts", "") or ""):
            if spell not in stats:
                report.add(
                    WARNING, "reference",
                    f"stats {entry.name!r}: UnlockSpell {spell!r} not found",
                )

    known_stats = {e.name for e in mod_stats} | set(_iter_names(stats))
    for template in mod_templates:
        binding = template.stats_name
        if binding and binding not in known_stats:
            report.add(
                WARNING, "binding",
                f"template {template.name or template.map_key!r}: Stats "
                f"{binding!r} has no matching stats entry",
            )


def _iter_names(stats: StatsCollection):
    return (entry.name for entry in stats)


def format_report(report: LintReport) -> str:
    symbols = {ERROR: "✗", WARNING: "!", INFO: "·"}
    lines = ["Lint", "----"]
    if not report.findings:
        lines.append("✓ no issues found")
        return "\n".join(lines)
    for finding in report.findings:
        loc = f" [{finding.file}]" if finding.file else ""
        lines.append(f"{symbols.get(finding.severity, '?')} {finding.message}{loc}")
    lines.append("")
    lines.append(
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    )
    return "\n".join(lines)
