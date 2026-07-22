"""Spell-list resources referenced by progression selectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from .lsx import LsxDocument


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
        return self.comment

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
