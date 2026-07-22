"""Spell-list resources referenced by progression selectors.

Spell lists also drive wizard scroll learning: a class's
``ClassDescription`` carries ``CanLearnSpells`` and a ``SpellList`` UUID,
and a scroll offers "Learn Spell" when its spell is on that list.  The
builders here emit a mod's ``Lists/SpellLists.lsx``; the game replaces a
list wholesale by UUID, so extending a base-game list means re-shipping
its full spell set plus the additions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable

from .lsx import LsxAttribute, LsxDocument, LsxNode

#: ``ClassDescription.SpellList`` of the Wizard class — the pool a wizard
#: can learn/transcribe from (Patch 8; 112 spells in retail).
WIZARD_LEARNABLE_LIST = "beb9389e-24f8-49b0-86a5-e8d08b6fdc2e"


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


@dataclass
class SpellList:
    uuid: str
    spell_names: list[str] = field(default_factory=list)
    comment: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    source: str | None = None

    @property
    def name(self) -> str:
        return self.uuid

    @property
    def display_name(self) -> str:
        # Retail lists label themselves with a Name attribute (e.g.
        # "Cleric cantrips (Wisdom)"); Comment is a fallback.
        return self.fields.get("Name") or self.comment

    def _link(self, game) -> None:
        self._game = game

    @cached_property
    def spells(self) -> list:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [game.spells[name] for name in self.spell_names if name in game.spells]


def parse_spell_lists(
    document: LsxDocument, source: str | None = None
) -> list[SpellList]:
    spell_lists = []
    for node in document.find_all("SpellList"):
        uuid = node.get("UUID")
        if not uuid:
            continue
        fields = {
            attr.id: attr.text
            for attr in node.attributes.values()
            if attr.text is not None
        }
        spell_lists.append(
            SpellList(
                uuid=uuid.lower(),
                spell_names=_split_list(node.get("Spells")),
                comment=node.get("Comment", "") or "",
                fields=fields,
                source=source,
            )
        )
    return spell_lists


def build_spell_list_node(
    list_uuid: str, spells: Iterable[str], *, name: str = ""
) -> LsxNode:
    """A ``SpellList`` node in the retail shape (attribute types pinned
    from ``Public/Shared/Lists/SpellLists.lsx``: ``Name`` FixedString,
    ``Spells`` LSString, ``UUID`` guid)."""
    attributes = {
        "Name": LsxAttribute("Name", "FixedString", name),
        "Spells": LsxAttribute("Spells", "LSString", ";".join(spells)),
        "UUID": LsxAttribute("UUID", "guid", list_uuid),
    }
    return LsxNode(id="SpellList", attributes=attributes)


def build_spell_lists_document(nodes: Iterable[LsxNode]) -> LsxDocument:
    """Wrap ``SpellList`` nodes in the ``SpellLists`` region a
    ``Lists/SpellLists.lsx`` file uses.  Serialize with
    :func:`bg3forge.parsers.lsx.write_lsx`."""
    root = LsxNode(id="root", children=list(nodes))
    return LsxDocument(regions={"SpellLists": root})
