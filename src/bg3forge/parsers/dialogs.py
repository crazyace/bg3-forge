"""Parser for dialog resources (``Mods/<Mod>/Story/DialogsBinary/**.lsf``).

A dialog is a graph of nodes (greetings, questions, answers, jumps, …)
with speaker slots and localized text handles::

    <region id="dialog">
      <node id="dialog">
        <attribute id="UUID" type="FixedString" value="..." />
        <attribute id="category" type="LSString" value="..." />
        <children>
          <node id="speakerlist">
            <children>
              <node id="speaker">
                <attribute id="index" type="FixedString" value="0" />
                <attribute id="SpeakerMappingId" type="guid" value="..." />
          ...
          <node id="nodes">
            <children>
              <node id="node">
                <attribute id="UUID" type="FixedString" value="..." />
                <attribute id="constructor" type="FixedString" value="TagGreeting" />
                <attribute id="speaker" type="int32" value="0" />
                <children>
                  <node id="TaggedTexts">... TagText handles ...</node>
                  <node id="children">
                    <children><node id="child"><attribute id="UUID" .../></node></children>
                  </node>
                  <node id="checkflags">           (also: setflags)
                    <children>
                      <node id="flaggroup">
                        <attribute id="type" type="FixedString" value="Global" />
                        <children>
                          <node id="flag">
                            <attribute id="UUID" type="FixedString" value="..." />
                            <attribute id="value" type="bool" value="True" />
                  ...

This module models the *metadata* level — structure, speakers, flow
edges, text handles, and the flag conditions that gate each node — not
the wider scripting layer.  Localization joins are the caller's job; see
:meth:`bg3forge.game.DialogIndex` for the lazy, per-file access layer,
and :mod:`bg3forge.hidden` for the analysis built on the flag model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lsx import LsxDocument, LsxNode


class DialogError(ValueError):
    pass


@dataclass
class Speaker:
    index: int
    mapping_id: str | None = None
    list_value: str | None = None  # raw speaker list (guids)


@dataclass(frozen=True)
class FlagRef:
    """One flag inside a group: the flag's UUID and the value it must
    hold (checks) or is given (sets)."""

    uuid: str
    value: bool = True
    paramval: int | None = None  # per-flag parameter (party member index, ...)


@dataclass(frozen=True)
class FlagGroup:
    """A ``flaggroup`` — flags of one scope (Global, Object, Local,
    Dialog, Tag, Script, User, Quest, ...)."""

    type: str
    flags: tuple[FlagRef, ...] = ()


@dataclass
class DialogNode:
    uuid: str
    constructor: str = ""          # TagGreeting, TagQuestion, TagAnswer, Jump, ...
    speaker: int | None = None     # index into the dialog's speaker list
    is_root: bool = False
    is_end: bool = False
    text_handles: list[tuple[str, int]] = field(default_factory=list)  # (handle, version)
    child_uuids: list[str] = field(default_factory=list)
    jump_target: str | None = None  # Jump nodes: the node jumped to
    check_flags: list[FlagGroup] = field(default_factory=list)  # conditions to enter
    set_flags: list[FlagGroup] = field(default_factory=list)    # written when played
    group_id: str | None = None    # nodes sharing one form a group of alternatives
    group_index: int = 0           # position in that group; 0 is the leader
    nested_dialog_uuid: str | None = None  # 'Nested Dialog': another dialog file

    @property
    def checks(self) -> list[tuple[str, FlagRef]]:
        """(group type, flag) for every condition guarding this node."""
        return [(group.type, flag) for group in self.check_flags for flag in group.flags]

    @property
    def targets(self) -> list[str]:
        """Node UUIDs this one can hand control to (children + jump)."""
        targets = list(self.child_uuids)
        if self.jump_target:
            targets.append(self.jump_target)
        return targets


@dataclass
class Dialog:
    uuid: str
    category: str = ""
    timeline_id: str | None = None
    source: str | None = None      # archived path the dialog came from
    speakers: list[Speaker] = field(default_factory=list)
    nodes: list[DialogNode] = field(default_factory=list)
    _by_uuid: dict[str, DialogNode] = field(default_factory=dict, repr=False)
    _group_index: dict[str, list[DialogNode]] | None = field(default=None, repr=False)

    def __post_init__(self):
        self._by_uuid = {node.uuid: node for node in self.nodes}

    def node(self, uuid: str) -> DialogNode | None:
        return self._by_uuid.get(uuid)

    def targets_of(self, node: DialogNode) -> list[str]:
        """Flow edges out of ``node``, including its node group.

        Nodes sharing a ``GroupID`` are one group of alternative lines:
        only the leader is linked from elsewhere, and the rest are played
        through it.  Without this edge every non-leader member looks
        unreachable, and so does everything hanging below it.
        """
        targets = list(node.targets)
        if node.group_id and self._is_group_leader(node):
            for member in self._groups.get(node.group_id, ()):
                if member.uuid != node.uuid and member.uuid not in targets:
                    targets.append(member.uuid)
        return targets

    def _is_group_leader(self, node: DialogNode) -> bool:
        """The member other nodes link to: the one named by the GroupID,
        or failing that the lowest GroupIndex."""
        members = self._groups.get(node.group_id or "", ())
        named = [member for member in members if member.uuid == node.group_id]
        if named:
            return node.uuid == named[0].uuid
        return bool(members) and node.uuid == members[0].uuid

    @property
    def _groups(self) -> dict[str, list[DialogNode]]:
        if self._group_index is None:
            groups: dict[str, list[DialogNode]] = {}
            for node in self.nodes:
                if node.group_id:
                    groups.setdefault(node.group_id, []).append(node)
            for members in groups.values():
                members.sort(key=lambda member: (member.group_index, member.uuid))
            self._group_index = groups
        return self._group_index

    @property
    def roots(self) -> list[DialogNode]:
        return [node for node in self.nodes if node.is_root]

    @property
    def entry_points(self) -> list[DialogNode]:
        """Where playback can begin: the flagged roots, or — when a
        dialog marks none — every node nothing else links to.

        Retail dialogs are not uniform about ``Root``; falling back to
        the graph's own sources keeps traversal working instead of
        reporting an entire file as unreachable.
        """
        roots = self.roots
        if roots:
            return roots
        linked = self._linked_uuids()
        return [node for node in self.nodes if node.uuid not in linked]

    def orphans(self) -> list[DialogNode]:
        """Nodes no other node links to and no root flag marks.

        Normal dialog flow cannot reach these; they are cut lines,
        editor leftovers, or nodes only script can jump into.
        """
        linked = self._linked_uuids()
        return [
            node
            for node in self.nodes
            if not node.is_root and node.uuid not in linked
        ]

    def _linked_uuids(self) -> set[str]:
        """Every node UUID some other node links to."""
        linked: set[str] = set()
        for node in self.nodes:
            linked.update(self.targets_of(node))
        return linked

    def text_handles(self) -> list[tuple[str, int]]:
        """Every (handle, version) spoken anywhere in the dialog."""
        handles = []
        for node in self.nodes:
            handles.extend(node.text_handles)
        return handles

    def walk(self, start: DialogNode | None = None):
        """Yield nodes depth-first along flow edges (cycles are cut).

        Flow edges are child links plus Jump nodes' ``jumptarget`` —
        without the latter, traversal dead-ends at every Jump.
        Traversal starts from :attr:`entry_points`, so dialogs that mark
        no root still walk from their graph sources.
        """
        stack = [start] if start else list(reversed(self.entry_points))
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node is None or node.uuid in seen:
                continue
            seen.add(node.uuid)
            yield node
            for target_uuid in reversed(self.targets_of(node)):
                stack.append(self._by_uuid.get(target_uuid))


def parse_dialog(document: LsxDocument, source: str | None = None) -> Dialog:
    region = document.region("dialog")
    if region is None:
        # ASCII-only message: these strings end up in Windows consoles
        # whose OEM codepage mangles anything fancier.
        raise DialogError("no 'dialog' region - not a dialog resource")
    uuid = region.get("UUID")
    if not uuid:
        raise DialogError("dialog region has no UUID")

    speakers = []
    for speaker_node in region.find_all("speaker"):
        index_raw = speaker_node.get("index", "0") or "0"
        try:
            index = int(index_raw)
        except ValueError:
            continue
        speakers.append(
            Speaker(
                index=index,
                mapping_id=speaker_node.get("SpeakerMappingId"),
                list_value=speaker_node.get("list"),
            )
        )
    speakers.sort(key=lambda s: s.index)

    nodes = []
    nodes_container = next(
        (child for child in region.children if child.id == "nodes"), None
    )
    if nodes_container is not None:
        for node_el in nodes_container.children:
            if node_el.id != "node":
                continue
            parsed = _parse_node(node_el)
            if parsed is not None:
                nodes.append(parsed)

    return Dialog(
        uuid=uuid,
        category=region.get("category", "") or "",
        timeline_id=region.get("TimelineId"),
        source=source,
        speakers=speakers,
        nodes=nodes,
    )


def _parse_node(node_el: LsxNode) -> DialogNode | None:
    uuid = node_el.get("UUID")
    if not uuid:
        return None
    speaker_raw = node_el.get("speaker")
    try:
        speaker = int(speaker_raw) if speaker_raw is not None else None
    except ValueError:
        speaker = None

    text_handles = []
    for tag_text in node_el.find_all("TagText"):
        attr = tag_text.attributes.get("TagText")
        if attr is not None and attr.handle:
            text_handles.append((attr.handle, attr.version or 1))

    child_uuids = []
    for wrapper in node_el.children:
        if wrapper.id == "children":
            for child in wrapper.find_all("child"):
                child_uuid = child.get("UUID")
                if child_uuid:
                    child_uuids.append(child_uuid)

    return DialogNode(
        uuid=uuid,
        constructor=node_el.get("constructor", "") or "",
        speaker=speaker,
        is_root=_truthy(node_el.get("Root")),
        is_end=_truthy(node_el.get("endnode")),
        text_handles=text_handles,
        child_uuids=child_uuids,
        jump_target=node_el.get("jumptarget"),
        check_flags=_parse_flag_wrapper(node_el, "checkflags"),
        set_flags=_parse_flag_wrapper(node_el, "setflags"),
        group_id=node_el.get("GroupID"),
        group_index=_int_or_none(node_el.get("GroupIndex")) or 0,
        nested_dialog_uuid=node_el.get("NestedDialogNodeUUID"),
    )


def _parse_flag_wrapper(node_el: LsxNode, wrapper_id: str) -> list[FlagGroup]:
    """The ``checkflags``/``setflags`` wrapper as typed flag groups.

    Node ids and attribute ids are matched case-insensitively: the same
    document reaches us as LSX, LSJ, or LSF, and the three
    serializations do not agree on casing.
    """
    groups: list[FlagGroup] = []
    for wrapper in node_el.children:
        if wrapper.id.lower() != wrapper_id:
            continue
        for group_el in wrapper.children:
            if group_el.id.lower() != "flaggroup":
                continue
            flags = []
            for flag_el in group_el.children:
                if flag_el.id.lower() != "flag":
                    continue
                flag_uuid = _get_ci(flag_el, "UUID")
                if not flag_uuid:
                    continue
                flags.append(
                    FlagRef(
                        uuid=flag_uuid,
                        value=_truthy(_get_ci(flag_el, "value")),
                        paramval=_int_or_none(_get_ci(flag_el, "paramval")),
                    )
                )
            groups.append(
                FlagGroup(type=_get_ci(group_el, "type") or "", flags=tuple(flags))
            )
    return groups


def _get_ci(node_el: LsxNode, attribute_id: str) -> str | None:
    value = node_el.get(attribute_id)
    if value is not None:
        return value
    wanted = attribute_id.lower()
    for name, attr in node_el.attributes.items():
        if name.lower() == wanted:
            return attr.text
    return None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in ("true", "1")
