"""Parser for Larian LSX documents (XML-serialized node trees).

LSX is the XML form of Larian's resource format, used for RootTemplates,
Progressions, texture atlas definitions, meta.lsx, and much more::

    <save>
      <version major="4" ... />
      <region id="Templates">
        <node id="Templates">
          <children>
            <node id="GameObjects">
              <attribute id="MapKey" type="FixedString" value="..." />
              <children>...</children>
            </node>
          </children>
        </node>
      </region>
    </save>

The binary sibling format (LSF) is not implemented yet; convert LSF
resources to LSX with lslib/divine before feeding them in.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class LsxAttribute:
    id: str
    type: str
    value: str | None
    handle: str | None = None  # TranslatedString handle
    version: int | None = None

    @property
    def text(self) -> str | None:
        """Best-effort display value (handle for translated strings)."""
        return self.value if self.value is not None else self.handle


@dataclass
class LsxNode:
    id: str
    attributes: dict[str, LsxAttribute] = field(default_factory=dict)
    children: list["LsxNode"] = field(default_factory=list)
    key: str | None = None  # key attribute name (LSF v7 keyed nodes)

    def get(self, attribute_id: str, default: str | None = None) -> str | None:
        attr = self.attributes.get(attribute_id)
        if attr is None:
            return default
        return attr.text if attr.text is not None else default

    def find_all(self, node_id: str) -> Iterator["LsxNode"]:
        """Depth-first search for descendant nodes with the given id."""
        for child in self.children:
            if child.id == node_id:
                yield child
            yield from child.find_all(node_id)


@dataclass
class LsxDocument:
    regions: dict[str, LsxNode] = field(default_factory=dict)

    def region(self, region_id: str) -> LsxNode | None:
        return self.regions.get(region_id)

    def find_all(self, node_id: str) -> Iterator[LsxNode]:
        for root in self.regions.values():
            if root.id == node_id:
                yield root
            yield from root.find_all(node_id)


class LsxError(ValueError):
    pass


def parse_lsx(source: str | bytes) -> LsxDocument:
    if isinstance(source, bytes):
        source = source.decode("utf-8-sig", errors="replace")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise LsxError(f"malformed LSX document: {exc}") from exc
    if root.tag != "save":
        raise LsxError(f"expected <save> root, found <{root.tag}>")
    document = LsxDocument()
    for region in root.findall("region"):
        region_id = region.get("id", "")
        node_el = region.find("node")
        if node_el is not None:
            document.regions[region_id] = _parse_node(node_el)
    return document


def load_lsx(path: str | Path) -> LsxDocument:
    return parse_lsx(Path(path).read_bytes())


def write_lsx(document: LsxDocument) -> str:
    """Serialize a document back to LSX XML (regions in insertion order)."""
    save = ET.Element("save")
    ET.SubElement(
        save, "version", major="4", minor="0", revision="9", build="330"
    )
    for region_id, root in document.regions.items():
        region_el = ET.SubElement(save, "region", id=region_id)
        _write_node(region_el, root)
    ET.indent(save)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
        save, encoding="unicode"
    ) + "\n"


def _write_node(parent_el: ET.Element, node: LsxNode) -> None:
    node_el = ET.SubElement(parent_el, "node", id=node.id)
    if node.key:
        node_el.set("key", node.key)
    for attr in node.attributes.values():
        attr_el = ET.SubElement(node_el, "attribute", id=attr.id, type=attr.type)
        if attr.handle is not None:
            attr_el.set("handle", attr.handle)
            if attr.version is not None:
                attr_el.set("version", str(attr.version))
        if attr.value is not None:
            attr_el.set("value", attr.value)
    if node.children:
        children_el = ET.SubElement(node_el, "children")
        for child in node.children:
            _write_node(children_el, child)


def _parse_node(element: ET.Element) -> LsxNode:
    node = LsxNode(id=element.get("id", ""), key=element.get("key"))
    for attr_el in element.findall("attribute"):
        attr = LsxAttribute(
            id=attr_el.get("id", ""),
            type=attr_el.get("type", ""),
            value=attr_el.get("value"),
            handle=attr_el.get("handle"),
            version=int(attr_el.get("version")) if attr_el.get("version") else None,
        )
        node.attributes[attr.id] = attr
    for children_el in element.findall("children"):
        for child_el in children_el.findall("node"):
            node.children.append(_parse_node(child_el))
    return node
