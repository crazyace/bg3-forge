"""Finding dialog content the game almost never shows.

Two structural signals in the dialog graph mark a line as hard to see:

*Gating* — a node carries ``checkflags``, so playback only enters it
when every flag in the group holds.  Conditions compound down a branch,
so the interesting question is not "is this node gated" but "how many
conditions must all be true before anyone hears this line".  This module
answers that with a cheapest-path search from the dialog's entry points,
where a node costs the number of flags guarding it: the result is the
*minimum* set of conditions any playthrough must satisfy to reach it.

*Orphaning* — a node nothing links to and no root flag marks.  Normal
flow cannot reach it at all: cut lines, editor leftovers, and nodes that
only Osiris script jumps into look the same from the data side.

Flag UUIDs are resolved to their authored names through
:attr:`bg3forge.game.Game.flag_names`, so a result reads
``Global:ORI_Withers_Recruited`` rather than a bare GUID.

    from bg3forge import Game
    from bg3forge.hidden import find_hidden, format_report

    game = Game()
    report = find_hidden(game, match="Astarion", min_gates=3)
    print(format_report(report))
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .game import Game, LoadIssue
from .parsers.dialogs import Dialog, DialogNode, FlagRef

#: Node kinds a scan can report.
KINDS = ("gated", "orphan")

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Condition:
    """One flag that must hold for a line to play."""

    scope: str          # Global, Object, Local, Dialog, Tag, Script, User, ...
    uuid: str
    value: bool = True
    name: str | None = None  # authored flag name, when the registry knows it

    @property
    def label(self) -> str:
        flag = self.name or self.uuid
        text = f"{self.scope}:{flag}" if self.scope else flag
        return text if self.value else f"not {text}"

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True)
class HiddenLine:
    """A spoken line together with what it takes to hear it."""

    dialog: str                 # archived path of the dialog resource
    category: str
    node: str                   # node UUID
    constructor: str
    speaker: int | None
    handle: str
    text: str
    kind: str                   # "gated" or "orphan"
    conditions: tuple[Condition, ...] = ()

    @property
    def gate_count(self) -> int:
        return len(self.conditions)


@dataclass
class HiddenReport:
    lines: list[HiddenLine] = field(default_factory=list)
    dialogs_scanned: int = 0
    dialogs_matched: int = 0
    #: Nodes carrying at least one ``checkflags`` condition.  Reported so
    #: that "no gated lines" is distinguishable from "no conditions were
    #: read at all" on a game build whose dialogs are shaped differently.
    gated_nodes: int = 0
    failures: list[LoadIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def find_hidden(
    game: Game,
    *,
    paths: Sequence[str] | None = None,
    match: str | None = None,
    category: str | None = None,
    kinds: Iterable[str] = KINDS,
    min_gates: int = 0,
    progress: Callable[[str], None] | None = None,
) -> HiddenReport:
    """Scan dialogs and rank the lines hardest to reach.

    ``paths`` (or ``match``, a case-insensitive substring of the
    archived path) narrows the sweep; the whole dialog tree is scanned
    otherwise, which on a retail install means tens of thousands of
    files.  Results are sorted most-gated first and are fully
    deterministic for a given install.
    """
    wanted_kinds = {kind.lower() for kind in kinds}
    unknown = wanted_kinds - set(KINDS)
    if unknown:
        raise ValueError(f"unknown kind(s): {', '.join(sorted(unknown))}")

    if paths is None:
        paths = game.dialogs.find(match) if match else game.dialogs.paths
    report = HiddenReport()
    flag_names = game.flag_names
    localization = game.localization

    for index, path in enumerate(sorted(paths), start=1):
        if progress:
            progress(f"scanning dialogs: {index:,}/{len(paths):,}")
        try:
            dialog: Dialog = game.dialogs.load(path)
        except (KeyError, ValueError) as exc:
            report.failures.append(LoadIssue(file=path, error=str(exc)))
            continue
        report.dialogs_scanned += 1
        if category and (dialog.category or "").lower() != category.lower():
            continue
        report.dialogs_matched += 1
        report.gated_nodes += sum(1 for node in dialog.nodes if node.check_flags)
        report.lines.extend(
            line
            for line in analyze_dialog(
                dialog, flag_names=flag_names, resolve=localization.resolve, path=path
            )
            if line.kind in wanted_kinds and line.gate_count >= min_gates
        )

    report.lines.sort(key=_rank)
    return report


def analyze_dialog(
    dialog: Dialog,
    *,
    flag_names: dict[str, str] | None = None,
    resolve: Callable[[str | None], str | None] | None = None,
    path: str | None = None,
) -> list[HiddenLine]:
    """Every gated or orphaned spoken line in one dialog.

    ``resolve`` maps a localization handle to text (typically
    ``game.localization.resolve``); lines whose handle resolves to
    nothing are skipped, since an untranslated handle says nothing
    about the content.  Without a resolver the raw handle is reported.
    """
    conditions = _cheapest_conditions(dialog, flag_names or {})
    reachable = {node.uuid for node in dialog.walk()}
    source = path or dialog.source or dialog.uuid

    lines: list[HiddenLine] = []
    for node in dialog.nodes:
        gates = conditions.get(node.uuid, ())
        kind = "gated" if node.uuid in reachable else "orphan"
        if kind == "gated" and not gates:
            continue  # plain, unconditional line: nothing hidden about it
        for handle, _version in node.text_handles:
            text = resolve(handle) if resolve else handle
            if not text:
                continue
            lines.append(
                HiddenLine(
                    dialog=source,
                    category=dialog.category,
                    node=node.uuid,
                    constructor=node.constructor,
                    speaker=node.speaker,
                    handle=handle,
                    text=_WHITESPACE_RE.sub(" ", text).strip(),
                    kind=kind,
                    conditions=gates,
                )
            )
    lines.sort(key=_rank)
    return lines


def _cheapest_conditions(
    dialog: Dialog, flag_names: dict[str, str]
) -> dict[str, tuple[Condition, ...]]:
    """node UUID -> the smallest condition set that reaches it.

    A uniform-cost search over flow edges where entering a node costs
    the number of flags guarding it.  Orphans seed the search alongside
    the real entry points so that cut subtrees are described too;
    whether a node is reachable in play is decided separately.
    """
    sources = {node.uuid for node in dialog.entry_points}
    sources.update(node.uuid for node in dialog.orphans())

    best: dict[str, tuple[Condition, ...]] = {}
    # (cost, node uuid, insertion order, conditions) — the counter keeps
    # ties away from the condition tuples, which do not compare.
    heap: list[tuple[int, str, int, tuple[Condition, ...]]] = []
    counter = 0
    for uuid in sorted(sources):
        node = dialog.node(uuid)
        if node is None:
            continue
        gates = _conditions(node, flag_names)
        heapq.heappush(heap, (len(gates), uuid, counter, gates))
        counter += 1

    while heap:
        cost, uuid, _order, gates = heapq.heappop(heap)
        if uuid in best:
            continue  # already reached by a path with no more conditions
        best[uuid] = gates
        node = dialog.node(uuid)
        if node is None:
            continue
        for target_uuid in node.targets:
            if target_uuid in best:
                continue
            target = dialog.node(target_uuid)
            if target is None:
                continue
            merged = _merge(gates, _conditions(target, flag_names))
            heapq.heappush(heap, (len(merged), target_uuid, counter, merged))
            counter += 1
    return best


def _conditions(node: DialogNode, flag_names: dict[str, str]) -> tuple[Condition, ...]:
    return tuple(
        _condition(scope, flag, flag_names) for scope, flag in node.checks
    )


def _condition(scope: str, flag: FlagRef, flag_names: dict[str, str]) -> Condition:
    return Condition(
        scope=scope,
        uuid=flag.uuid,
        value=flag.value,
        name=flag_names.get(flag.uuid.lower()),
    )


def _merge(
    inherited: tuple[Condition, ...], own: tuple[Condition, ...]
) -> tuple[Condition, ...]:
    """Path conditions plus a node's own, in order, without repeats.

    A branch commonly re-checks a flag its parent already checked; that
    is one condition to satisfy, not two, and counting it twice would
    inflate the ranking.
    """
    merged = list(inherited)
    seen = set(inherited)
    for condition in own:
        if condition not in seen:
            seen.add(condition)
            merged.append(condition)
    return tuple(merged)


def _rank(line: HiddenLine) -> tuple:
    """Most conditions first, orphans ahead of equally-gated lines."""
    return (-line.gate_count, line.kind != "orphan", line.dialog, line.node, line.handle)


def to_records(report: HiddenReport) -> list[dict]:
    """The findings as plain records, ready for the exporters."""
    return [
        {
            "dialog": line.dialog,
            "category": line.category,
            "node": line.node,
            "constructor": line.constructor,
            "speaker": line.speaker,
            "handle": line.handle,
            "text": line.text,
            "kind": line.kind,
            "gate_count": line.gate_count,
            "conditions": [condition.label for condition in line.conditions],
        }
        for line in report.lines
    ]


def format_report(report: HiddenReport, limit: int = 40, width: int = 96) -> str:
    # ASCII-only output: these strings land in Windows consoles whose
    # OEM codepage mangles anything fancier.
    lines = ["Hidden dialog content", "---------------------"]
    lines.append(
        f"scanned {report.dialogs_scanned:,} dialog(s); "
        f"{report.gated_nodes:,} node(s) carry conditions; "
        f"found {len(report.lines):,} line(s)"
    )
    if not report.lines:
        lines.append("")
        lines.append("nothing matched: try a lower --min-gates or a wider --match.")
        return "\n".join(lines + _failures(report))

    shown = report.lines[:limit]
    current = None
    for line in shown:
        if line.dialog != current:
            current = line.dialog
            category = f"  [{line.category}]" if line.category else ""
            lines.append("")
            lines.append(f"{line.dialog}{category}")
        tag = "orphan" if line.kind == "orphan" else f"gated x{line.gate_count}"
        speaker = "speaker ?" if line.speaker is None else f"speaker {line.speaker}"
        lines.append(f"  {tag:<10}{speaker:<11}{_quote(line.text, width)}")
        if line.conditions:
            requires = ", ".join(condition.label for condition in line.conditions)
            lines.append(f"  {'':<10}requires {requires}")
    remaining = len(report.lines) - len(shown)
    if remaining > 0:
        lines.append("")
        lines.append(f"... and {remaining:,} more (raise --limit to see them)")
    return "\n".join(lines + _failures(report))


def _failures(report: HiddenReport) -> list[str]:
    if report.ok:
        return []
    lines = ["", f"{len(report.failures)} dialog(s) failed to parse:"]
    for issue in report.failures[:5]:
        lines.append(f"  {issue.file}: {issue.error}")
    remaining = len(report.failures) - 5
    if remaining > 0:
        lines.append(f"  ... and {remaining:,} more")
    return lines


def _quote(text: str, width: int) -> str:
    if len(text) > width:
        text = text[: width - 3].rstrip() + "..."
    return f'"{text}"'
