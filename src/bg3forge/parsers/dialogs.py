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

This module models the *metadata* level — structure, speakers, flow
edges, and text handles — not scripting (flag checks/sets are kept as
raw counts only).  Localization joins are the caller's job; see
:meth:`bg3forge.game.DialogIndex` for the lazy, per-file access layer.
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


@dataclass
class Dialog:
    uuid: str
    category: str = ""
    timeline_id: str | None = None
    source: str | None = None      # archived path the dialog came from
    speakers: list[Speaker] = field(default_factory=list)
    nodes: list[DialogNode] = field(default_factory=list)
    _by_uuid: dict[str, DialogNode] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._by_uuid = {node.uuid: node for node in self.nodes}

    def node(self, uuid: str) -> DialogNode | None:
        return self._by_uuid.get(uuid)

    @property
    def roots(self) -> list[DialogNode]:
        return [node for node in self.nodes if node.is_root]

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
        """
        stack = [start] if start else list(reversed(self.roots))
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node is None or node.uuid in seen:
                continue
            seen.add(node.uuid)
            yield node
            targets = list(node.child_uuids)
            if node.jump_target:
                targets.append(node.jump_target)
            for target_uuid in reversed(targets):
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
    )


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in ("true", "1")
