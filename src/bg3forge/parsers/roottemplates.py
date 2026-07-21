"""Extract game objects from RootTemplate LSX documents.

RootTemplates live under ``Public/<Mod>/RootTemplates/`` and describe the
game objects (items, characters, projectiles …) that stats entries are
attached to.  Templates inherit from a parent template via
``ParentTemplateId``; :class:`RootTemplateIndex` resolves that chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from .lsx import LsxDocument, LsxNode

_FIELDS = (
    "Name",
    "DisplayName",
    "Description",
    "Stats",
    "Icon",
    "Type",
    "ParentTemplateId",
    "LevelName",
)


@dataclass
class RootTemplate:
    map_key: str
    fields: dict[str, str] = field(default_factory=dict)

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
        return cls(map_key=map_key, fields=fields)


def parse_root_templates(document: LsxDocument) -> list[RootTemplate]:
    templates = []
    for node in document.find_all("GameObjects"):
        template = RootTemplate.from_node(node)
        if template is not None:
            templates.append(template)
    return templates


class RootTemplateIndex:
    """MapKey → template lookup with parent-template inheritance."""

    def __init__(self):
        self._templates: dict[str, RootTemplate] = {}

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

    def resolved(self, map_key: str) -> dict[str, str]:
        """Effective fields for a template with ancestors merged in."""
        chain: list[RootTemplate] = []
        seen: set[str] = set()
        cursor: str | None = map_key
        while cursor and cursor not in seen:
            seen.add(cursor)
            template = self._templates.get(cursor)
            if template is None:
                break
            chain.append(template)
            cursor = template.parent_id
        fields: dict[str, str] = {}
        for template in reversed(chain):
            fields.update(template.fields)
        return fields
