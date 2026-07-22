"""Extract game objects from RootTemplate LSX documents.

RootTemplates live under ``Public/<Mod>/RootTemplates/`` and describe the
game objects (items, characters, projectiles …) that stats entries are
attached to.  Templates inherit from a parent template via
``ParentTemplateId``; :class:`RootTemplateIndex` resolves that chain.
Placed objects from ``Mods/*/{Globals,Levels}/*`` use ``TemplateName`` to
reference a RootTemplate; the same index can resolve that link when both are
loaded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .lsx import LsxAttribute, LsxDocument, LsxNode

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))

_FIELDS = (
    "Name",
    "DisplayName",
    "Description",
    "Stats",
    "Icon",
    "Type",
    "ParentTemplateId",
    "TemplateName",
    "LevelName",
    "Equipment",
    "Archetype",
)

# Serialization type for each scalar field.  Anything not listed here (and
# not a TranslatedString handle) defaults to FixedString, matching retail.
_FIELD_TYPES = {
    "Name": "LSString",
    "MapKey": "FixedString",
    "Stats": "FixedString",
    "Icon": "FixedString",
    "Type": "FixedString",
    "ParentTemplateId": "FixedString",
    "TemplateName": "FixedString",
    "LevelName": "FixedString",
    "Equipment": "FixedString",
    "Archetype": "FixedString",
}
# Fields carried as TranslatedString handles rather than plain values.
_HANDLE_FIELDS = ("DisplayName", "Description")


@dataclass
class RootTemplate:
    map_key: str
    fields: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)  # tag UUIDs
    inventory: list[str] = field(default_factory=list)  # InventoryList Object refs

    @property
    def name(self) -> str | None:
        return self.fields.get("Name")

    @property
    def display_name_handle(self) -> str | None:
        return self.fields.get("DisplayName")

    @property
    def description_handle(self) -> str | None:
        return self.fields.get("Description")

    @property
    def stats_name(self) -> str | None:
        return self.fields.get("Stats")

    @property
    def icon(self) -> str | None:
        return self.fields.get("Icon")

    @property
    def parent_id(self) -> str | None:
        return self.fields.get("ParentTemplateId")

    @property
    def template_name(self) -> str | None:
        """Referenced RootTemplate for a placed global object, if any."""
        return self.fields.get("TemplateName")

    @property
    def treasure_tables(self) -> list[str]:
        """Inventory references that name a treasure table (e.g. a container
        that fills from ``"TUT_Chest_Potions"``).  A subset of
        :attr:`inventory` — direct-object inventory entries are UUIDs."""
        return [obj for obj in self.inventory if not _looks_like_uuid(obj)]

    @classmethod
    def from_node(cls, node: LsxNode) -> "RootTemplate | None":
        map_key = node.get("MapKey")
        if not map_key:
            return None
        fields = {}
        for key in _FIELDS:
            value = node.get(key)
            if value is not None:
                fields[key] = value
        tags = []
        inventory = []
        for child in node.children:
            if child.id == "Tags":
                for tag_node in child.find_all("Tag"):
                    tag = tag_node.get("Object")
                    if tag:
                        tags.append(tag)
            elif child.id == "InventoryList":
                for item_node in child.find_all("InventoryItem"):
                    obj = item_node.get("Object")
                    if obj:
                        inventory.append(obj)
        return cls(map_key=map_key, fields=fields, tags=tags, inventory=inventory)


def parse_root_templates(document: LsxDocument) -> list[RootTemplate]:
    templates = []
    for node in document.find_all("GameObjects"):
        template = RootTemplate.from_node(node)
        if template is not None:
            templates.append(template)
    return templates


def build_root_template_node(
    map_key: str,
    name: str,
    *,
    template_type: str = "item",
    stats: str | None = None,
    icon: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    parent_template_id: str | None = None,
    tags: Iterable[str] = (),
    on_use: Iterable[LsxNode] = (),
    handle_version: int = 1,
    fields: dict[str, str] | None = None,
) -> LsxNode:
    """Build one ``GameObjects`` RootTemplate node, the inverse of
    :meth:`RootTemplate.from_node`.

    ``display_name`` and ``description`` are TranslatedString *handles*
    (``h...``); ``parent_template_id`` is the base template this object
    inherits from — the usual way to reuse an existing item's visuals.
    ``fields`` passes through any additional scalar attributes (``Equipment``,
    ``Archetype``, …).  ``on_use`` takes ``Action`` nodes (from
    :func:`build_consume_action` / :func:`build_use_spell_action`) and wraps
    them in an ``OnUsePeaceActions`` child — the consumable use mechanism.
    Serialize the node inside a document from
    :func:`build_templates_document`.
    """
    attributes: dict[str, LsxAttribute] = {}

    def put(field_id: str, value: str | None) -> None:
        if value is not None:
            attributes[field_id] = LsxAttribute(
                id=field_id,
                type=_FIELD_TYPES.get(field_id, "FixedString"),
                value=value,
            )

    put("MapKey", map_key)
    put("Name", name)
    put("Type", template_type)
    put("Stats", stats)
    put("Icon", icon)
    put("ParentTemplateId", parent_template_id)
    for field_id, handle in (("DisplayName", display_name), ("Description", description)):
        if handle is not None:
            attributes[field_id] = LsxAttribute(
                id=field_id,
                type="TranslatedString",
                value=None,
                handle=handle,
                version=handle_version,
            )
    for field_id, value in (fields or {}).items():
        put(field_id, value)

    children: list[LsxNode] = []
    action_nodes = list(on_use)
    if action_nodes:
        children.append(LsxNode(id="OnUsePeaceActions", children=action_nodes))
    tag_nodes = [
        LsxNode(
            id="Tag",
            attributes={"Object": LsxAttribute(id="Object", type="guid", value=tag)},
        )
        for tag in tags
    ]
    if tag_nodes:
        children.append(LsxNode(id="Tags", children=tag_nodes))

    return LsxNode(id="GameObjects", attributes=attributes, children=children)


#: The ClassId retail spell scrolls carry on their cast-from-scroll action
#: (identical across shipped scrolls).
SCROLL_CLASS_ID = "a865965f-501b-46e9-aa9e-4877c0e8094d"


def _use_action(action_type: int, attributes: dict[str, LsxAttribute]) -> LsxNode:
    return LsxNode(
        id="Action",
        attributes={
            "ActionType": LsxAttribute("ActionType", "int32", str(action_type))
        },
        children=[LsxNode(id="Attributes", attributes=attributes)],
    )


def build_consume_action(
    status_id: str, duration: int = 0, animation: str = ""
) -> LsxNode:
    """An ``OnUsePeaceActions`` Consume action (ActionType 7): using the item
    consumes it and applies ``status_id``.  ``duration`` 0 applies the
    status instantly (potions); ``-1`` keeps it until long rest (elixirs).
    Field names and attribute types match retail consumable templates.
    """
    return _use_action(
        7,
        {
            "Animation": LsxAttribute("Animation", "FixedString", animation),
            "Conditions": LsxAttribute("Conditions", "LSString", ""),
            "Consume": LsxAttribute("Consume", "bool", "True"),
            "StatsId": LsxAttribute("StatsId", "FixedString", status_id),
            "StatusDuration": LsxAttribute("StatusDuration", "int32", str(duration)),
        },
    )


def build_use_spell_action(
    spell_id: str, class_id: str = SCROLL_CLASS_ID
) -> LsxNode:
    """An ``OnUsePeaceActions`` cast-from-item action (ActionType 12): using
    the item casts ``spell_id`` and consumes it — the spell-scroll pattern,
    gated by the same ``CanUseSpellScroll`` condition retail scrolls use.
    """
    return _use_action(
        12,
        {
            "Animation": LsxAttribute("Animation", "FixedString", ""),
            "ClassId": LsxAttribute("ClassId", "guid", class_id),
            "Conditions": LsxAttribute(
                "Conditions", "LSString", f'CanUseSpellScroll("{spell_id}")'
            ),
            "Consume": LsxAttribute("Consume", "bool", "True"),
            "SkillID": LsxAttribute("SkillID", "FixedString", spell_id),
        },
    )


def build_templates_document(nodes: Iterable[LsxNode]) -> LsxDocument:
    """Wrap ``GameObjects`` nodes in the ``Templates`` region a RootTemplate
    file uses.  Serialize with :func:`bg3forge.parsers.lsx.write_lsx`."""
    root = LsxNode(id="Templates", children=list(nodes))
    return LsxDocument(regions={"Templates": root})


class RootTemplateIndex:
    """MapKey → template lookup with parent-template inheritance."""

    def __init__(self):
        self._templates: dict[str, RootTemplate] = {}
        self._stats_index: dict[str, list[RootTemplate]] | None = None
        self._treasure_index: dict[str, list[RootTemplate]] | None = None

    def __len__(self) -> int:
        return len(self._templates)

    def __iter__(self) -> Iterator[RootTemplate]:
        return iter(self._templates.values())

    def __contains__(self, map_key: str) -> bool:
        return map_key in self._templates

    def get(self, map_key: str) -> RootTemplate | None:
        return self._templates.get(map_key)

    def add_document(self, document: LsxDocument) -> None:
        for template in parse_root_templates(document):
            self._templates[template.map_key] = template
        self._stats_index = None  # invalidate the reverse indexes
        self._treasure_index = None

    def resolved(self, map_key: str) -> dict[str, str]:
        """Effective fields for a template with ancestors merged in."""
        fields: dict[str, str] = {}
        for template in reversed(self._chain(map_key)):
            fields.update(template.fields)
        return fields

    def resolved_tags(self, map_key: str) -> list[str]:
        """Tag UUIDs for a template, merged across the ancestor chain.

        Ancestor tags come first; duplicates are dropped.
        """
        tags: list[str] = []
        for template in reversed(self._chain(map_key)):
            for tag in template.tags:
                if tag not in tags:
                    tags.append(tag)
        return tags

    def by_stats(self, stats_name: str) -> list[RootTemplate]:
        """Templates whose ``Stats`` field references the given stats entry."""
        if self._stats_index is None:
            index: dict[str, list[RootTemplate]] = {}
            for template in self._templates.values():
                stats = template.stats_name
                if stats:
                    index.setdefault(stats, []).append(template)
            self._stats_index = index
        return list(self._stats_index.get(stats_name, ()))

    def by_treasure_table(self, table_name: str) -> list[RootTemplate]:
        """Templates (usually placed containers) whose inventory fills from
        the named treasure table — e.g. ``"TUT_Chest_Potions"`` returns the
        tutorial chest, whose ``map_key`` is the object to spawn.

        Only meaningful on an index that includes placed objects
        (``game.item_templates``); ``game.templates`` holds RootTemplates
        only, where the treasure link isn't present.
        """
        if self._treasure_index is None:
            index: dict[str, list[RootTemplate]] = {}
            for template in self._templates.values():
                for table in template.treasure_tables:
                    index.setdefault(table, []).append(template)
            self._treasure_index = index
        return list(self._treasure_index.get(table_name, ()))

    def _chain(self, map_key: str) -> list[RootTemplate]:
        """Template plus its ancestors, nearest first; cycles are cut."""
        chain: list[RootTemplate] = []
        seen: set[str] = set()
        cursor: str | None = map_key
        while cursor and cursor not in seen:
            seen.add(cursor)
            template = self._templates.get(cursor)
            if template is None:
                break
            chain.append(template)
            # RootTemplates inherit through ParentTemplateId.  Placed objects
            # under Mods/*/{Globals,Levels}/* instead point back to their
            # RootTemplate through TemplateName; the runtime resolves both.
            cursor = template.parent_id or template.template_name
        return chain
