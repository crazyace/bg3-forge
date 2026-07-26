"""Finding dialog content the game almost never shows.

Two structural signals in the dialog graph mark a line as hard to see:

*Gating* — a node carries ``checkflags``, so playback only enters it
when every flag in the group holds.  Conditions compound down a branch,
so the interesting question is not "is this node gated" but "how many
conditions must all be true before anyone hears this line".  This module
answers that with a cheapest-path search from the dialog's entry points,
where a node costs the number of flags guarding it: the result is the
*minimum* set of conditions any playthrough must satisfy to reach it.

*Unreachability* — no entry point reaches the node at all.  Entry
covers child edges, jump targets, node groups, both root declarations,
and cross-file ``Nested Dialog`` pointers; Osiris starts dialogs at
resource granularity and cannot enter a node directly (verified against
retail — see ``docs/retail-testing.md``).  That covers
more than a stray node: a whole branch is unreachable when the link into
its top is missing, so the finding is "normal flow cannot get here",
not "nothing points at this".  Cut lines, editor leftovers, and nodes
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
import textwrap
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

from .game import Game, LoadIssue
from .parsers.dialogs import Dialog, DialogNode, FlagRef

#: Node kinds a scan can report.
KINDS = ("gated", "unreachable")

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
    kind: str                   # "gated" or "unreachable"
    conditions: tuple[Condition, ...] = ()
    #: Conditions that actually have to be *made* true to reach the line
    #: (see :func:`analyze_dialog` on why negated checks are free).
    gate_count: int = 0

    @property
    def required(self) -> tuple[Condition, ...]:
        """Flags an playthrough must set before this line can play."""
        return tuple(condition for condition in self.conditions if condition.value)

    @property
    def excluded(self) -> tuple[Condition, ...]:
        """Flags that must *not* be set — satisfied unless something
        happened, so they narrow a branch without hiding it."""
        return tuple(condition for condition in self.conditions if not condition.value)


@dataclass
class HiddenReport:
    lines: list[HiddenLine] = field(default_factory=list)
    dialogs_scanned: int = 0
    dialogs_matched: int = 0
    #: Nodes carrying at least one ``checkflags`` condition.  Reported so
    #: that "no gated lines" is distinguishable from "no conditions were
    #: read at all" on a game build whose dialogs are shaped differently.
    gated_nodes: int = 0
    #: Unreachable findings dropped because another dialog enters them
    #: through a ``Nested Dialog`` node.
    nested_entries: int = 0
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
    scopes: Iterable[str] | None = None,
    count_negated: bool = False,
    min_gates: int = 0,
    progress: Callable[[str], None] | None = None,
) -> HiddenReport:
    """Scan dialogs and rank the lines hardest to reach.

    ``paths`` (or ``match``, a case-insensitive substring of the
    archived path) narrows the sweep; the whole dialog tree is scanned
    otherwise, which on a retail install means tens of thousands of
    files.  Results are sorted most-gated first and are fully
    deterministic for a given install.

    A narrowed sweep cannot rule out cross-file entry: ``Nested Dialog``
    pointers are only known for the dialogs actually scanned, so an
    unreachable finding is strongest when the whole tree was swept.

    ``scopes`` restricts which flag scopes count as gating.  Retail
    dialogs mix world state (``Global``, ``Object``) with party-
    composition checks (``Tag``) and engine bookkeeping (``Script``);
    ranking by world state alone is often the more interesting question,
    and conditions in excluded scopes are dropped from both the count
    and the search.
    """
    wanted_kinds = {kind.lower() for kind in kinds}
    unknown = wanted_kinds - set(KINDS)
    if unknown:
        raise ValueError(f"unknown kind(s): {', '.join(sorted(unknown))}")

    wanted_scopes = {scope.lower() for scope in scopes} if scopes else None

    if paths is None:
        paths = game.dialogs.find(match) if match else game.dialogs.paths
    report = HiddenReport()
    # Nodes some other dialog enters through a 'Nested Dialog' pointer.
    # Collected as we go and applied at the end, so a node reached only
    # from another file is not reported as unreachable.
    nested_targets: set[str] = set()
    names = game_names(game)
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
        nested_targets.update(
            node.nested_dialog_uuid
            for node in dialog.nodes
            if node.nested_dialog_uuid
        )
        report.lines.extend(
            line
            for line in analyze_dialog(
                dialog,
                names=names,
                resolve=localization.resolve,
                scopes=wanted_scopes,
                count_negated=count_negated,
                path=path,
            )
            if line.kind in wanted_kinds and line.gate_count >= min_gates
        )

    if nested_targets:
        kept = [
            line
            for line in report.lines
            if line.kind != "unreachable" or line.node not in nested_targets
        ]
        report.nested_entries = len(report.lines) - len(kept)
        report.lines = kept

    report.lines.sort(key=_rank)
    return report


def analyze_dialog(
    dialog: Dialog,
    *,
    names: Mapping[str, str] | Callable[[str, str], str | None] | None = None,
    resolve: Callable[[str | None], str | None] | None = None,
    scopes: Iterable[str] | None = None,
    count_negated: bool = False,
    path: str | None = None,
) -> list[HiddenLine]:
    """Every gated or orphaned spoken line in one dialog.

    ``names`` resolves a flag UUID to its authored name — either a
    plain UUID -> name mapping or a ``(scope, uuid)`` callable, since
    the registry to consult depends on the scope (see
    :func:`game_names`).  ``resolve`` maps a localization handle to text
    (typically ``game.localization.resolve``); lines whose handle
    resolves to nothing are skipped, since an untranslated handle says
    nothing about the content.  Without a resolver the raw handle is
    reported.  ``scopes``, when given, limits which flag scopes gate.

    Negated checks (``not FLAG``) do not count toward the gate total by
    default.  Story flags start false, so a ``not`` check is satisfied
    until something sets it: retail greeting stacks list a dozen of them
    to say "use this line when nothing more specific applies", which
    describes the *fallback* line, not a hidden one.  Pass
    ``count_negated=True`` to weigh them equally anyway.
    """
    wanted_scopes = {scope.lower() for scope in scopes} if scopes else None
    conditions = _cheapest_conditions(
        dialog, _resolver(names), wanted_scopes, count_negated
    )
    reachable = {node.uuid for node in dialog.walk()}
    source = path or dialog.source or dialog.uuid

    lines: list[HiddenLine] = []
    for node in dialog.nodes:
        gates = conditions.get(node.uuid, ())
        kind = "gated" if node.uuid in reachable else "unreachable"
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
                    gate_count=_cost(gates, count_negated),
                )
            )
    lines.sort(key=_rank)
    return lines


def game_names(game: Game) -> Callable[[str, str], str | None]:
    """A ``(scope, uuid) -> name`` resolver backed by a game install.

    ``Tag``-scope conditions are party-composition checks naming entries
    in the tag registry, not story flags; every other scope resolves
    through :attr:`bg3forge.game.Game.flag_names`.  The tag registry is
    only built if a Tag condition actually turns up — most sweeps that
    never see one should not pay for parsing thousands of tag files.
    """
    flags = game.flag_names
    tags: dict[str, str] | None = None

    def lookup(scope: str, uuid: str) -> str | None:
        nonlocal tags
        key = uuid.lower()
        if scope.lower() == "tag":
            if tags is None:
                tags = {
                    tag.uuid.lower(): tag.name or tag.display_name
                    for tag in game.tags
                }
            name = tags.get(key)
            if name:
                return name
        return flags.get(key)

    return lookup


def _resolver(
    names: Mapping[str, str] | Callable[[str, str], str | None] | None,
) -> Callable[[str, str], str | None]:
    """Normalize the two accepted ``names`` forms to one callable."""
    if names is None:
        return lambda scope, uuid: None
    if callable(names):
        return names
    return lambda scope, uuid: names.get(uuid.lower())


def _cost(conditions: tuple[Condition, ...], count_negated: bool) -> int:
    """How many of these conditions someone has to bring about."""
    if count_negated:
        return len(conditions)
    return sum(1 for condition in conditions if condition.value)


def _cheapest_conditions(
    dialog: Dialog,
    names: Callable[[str, str], str | None],
    scopes: set[str] | None,
    count_negated: bool = False,
) -> dict[str, tuple[Condition, ...]]:
    """node UUID -> the smallest condition set that reaches it.

    A uniform-cost search over flow edges where entering a node costs
    the number of flags guarding it.  Orphans seed the search alongside
    the real entry points so that cut subtrees are described too;
    whether a node is reachable in play is decided separately.
    """
    sources = {node.uuid for node in dialog.entry_points}
    sources.update(node.uuid for node in dialog.orphans())  # describe cut branches too

    best: dict[str, tuple[Condition, ...]] = {}
    # (cost, node uuid, insertion order, conditions) — the counter keeps
    # ties away from the condition tuples, which do not compare.
    heap: list[tuple[int, str, int, tuple[Condition, ...]]] = []
    counter = 0
    for uuid in sorted(sources):
        node = dialog.node(uuid)
        if node is None:
            continue
        gates = _conditions(node, names, scopes)
        heapq.heappush(heap, (_cost(gates, count_negated), uuid, counter, gates))
        counter += 1

    while heap:
        cost, uuid, _order, gates = heapq.heappop(heap)
        if uuid in best:
            continue  # already reached by a path with no more conditions
        best[uuid] = gates
        node = dialog.node(uuid)
        if node is None:
            continue
        for target_uuid in dialog.targets_of(node):
            if target_uuid in best:
                continue
            target = dialog.node(target_uuid)
            if target is None:
                continue
            merged = _merge(gates, _conditions(target, names, scopes))
            heapq.heappush(
                heap, (_cost(merged, count_negated), target_uuid, counter, merged)
            )
            counter += 1
    return best


def _conditions(
    node: DialogNode,
    names: Callable[[str, str], str | None],
    scopes: set[str] | None,
) -> tuple[Condition, ...]:
    return tuple(
        Condition(
            scope=scope,
            uuid=flag.uuid,
            value=flag.value,
            name=names(scope, flag.uuid),
        )
        for scope, flag in node.checks
        if scopes is None or scope.lower() in scopes
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
    """Most conditions first, unreachable lines ahead of equally-gated ones."""
    return (
        -line.gate_count,
        line.kind != "unreachable",
        line.dialog,
        line.node,
        line.handle,
    )


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
            "requires": [condition.label for condition in line.required],
            "unless": [condition.label for condition in line.excluded],
        }
        for line in report.lines
    ]


def scope_counts(report: HiddenReport) -> dict[str, int]:
    """How often each flag scope appears across the findings.

    Retail mixes world state with party-composition and engine checks;
    seeing the mix is what tells you whether a ``--scope`` filter would
    sharpen the ranking.
    """
    counts: dict[str, int] = {}
    for line in report.lines:
        for condition in line.conditions:
            scope = condition.scope or "(none)"
            counts[scope] = counts.get(scope, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def format_report(
    report: HiddenReport,
    limit: int = 40,
    width: int = 96,
    max_conditions: int = 8,
) -> str:
    # ASCII-only output: these strings land in Windows consoles whose
    # OEM codepage mangles anything fancier.
    lines = ["Hidden dialog content", "---------------------"]
    lines.append(
        f"scanned {report.dialogs_scanned:,} dialog(s); "
        f"{report.gated_nodes:,} node(s) carry conditions; "
        f"found {len(report.lines):,} line(s)"
    )
    if report.nested_entries:
        lines.append(
            f"{report.nested_entries:,} line(s) dropped: entered from another "
            "dialog through a Nested Dialog node"
        )
    counts = scope_counts(report)
    if counts:
        summary = ", ".join(f"{scope} {count:,}" for scope, count in counts.items())
        lines.append(f"conditions by scope: {summary}")
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
        tag = (
            "unreachable" if line.kind == "unreachable" else f"gated x{line.gate_count}"
        )
        speaker = "speaker ?" if line.speaker is None else f"speaker {line.speaker}"
        lines.append(f"  {tag:<13}{speaker:<11}{_quote(line.text, width)}")
        lines.extend(_requires(line, width, max_conditions))
    remaining = len(report.lines) - len(shown)
    if remaining > 0:
        lines.append("")
        lines.append(f"... and {remaining:,} more (raise --limit to see them)")
    return "\n".join(lines + _failures(report))


def _requires(line: HiddenLine, width: int, max_conditions: int) -> list[str]:
    """The condition block: what must be true, then what must not be.

    Split because the two are not equally interesting.  A retail
    greeting stack carries twenty ``not`` checks that merely say "no
    more specific line applies"; printing them first buried the two
    positive conditions that actually describe the branch.  Each side is
    wrapped and capped; ``--json`` always carries the full set.
    """
    block: list[str] = []
    for label, conditions in (("requires", line.required), ("unless", line.excluded)):
        if not conditions:
            continue
        shown = [condition.label for condition in conditions[:max_conditions]]
        remaining = len(conditions) - len(shown)
        if remaining > 0:
            shown.append(f"(+{remaining:,} more)")
        indent = " " * 15
        block.extend(
            textwrap.wrap(
                f"{label:<9}" + ", ".join(shown),
                width=max(40, width),
                initial_indent=indent,
                subsequent_indent=indent + " " * 9,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return block


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
