"""Class descriptions — the class/subclass metadata behind spell learning.

A ``ClassDescription`` ties a class to its progression table
(``ProgressionTableUUID``) and to the spell machinery: ``SpellList`` is
the class's learnable/preparable pool (for the Wizard, the pool scroll
transcription draws from — ``CanLearnSpells``), and ``MustPrepareSpells``
distinguishes prepared casters from selection casters.  Subclasses carry
``ParentGuid`` pointing at their class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from .lsx import LsxDocument


def _to_bool(raw: str | None) -> bool:
    return (raw or "").lower() in ("true", "1")


def _to_int(raw: str | None) -> int | None:
    try:
        return int(raw) if raw not in (None, "") else None
    except ValueError:
        return None


@dataclass
class ClassDescription:
    uuid: str
    name: str
    parent_uuid: str | None = None
    spell_list_uuid: str | None = None
    can_learn_spells: bool = False
    must_prepare_spells: bool = False
    progression_table_uuid: str | None = None
    primary_ability: int | None = None
    spellcasting_ability: int | None = None
    base_hp: int | None = None
    hp_per_level: int | None = None
    display_name_handle: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    source: str | None = None

    # Resolved lazily against the loca table when linked to a Game.
    display_name: str = ""

    def _link(self, game) -> None:
        self._game = game

    @cached_property
    def spell_list(self):
        """The class's learnable/preparable :class:`SpellList` (or None)."""
        game = getattr(self, "_game", None)
        if game is None or not self.spell_list_uuid:
            return None
        return game.spell_lists.get(self.spell_list_uuid)

    @cached_property
    def progressions(self) -> list:
        """This class's level records, ordered by level."""
        game = getattr(self, "_game", None)
        if game is None or not self.progression_table_uuid:
            return []
        return game.progressions.by_table(self.progression_table_uuid)

    @cached_property
    def parent(self):
        """The parent class for a subclass (or None)."""
        game = getattr(self, "_game", None)
        if game is None or not self.parent_uuid:
            return None
        for cls in game.classes:
            if cls.uuid == self.parent_uuid:
                return cls
        return None

    @cached_property
    def subclasses(self) -> list["ClassDescription"]:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [cls for cls in game.classes if cls.parent_uuid == self.uuid]


def parse_class_descriptions(
    document: LsxDocument, source: str | None = None
) -> list[ClassDescription]:
    descriptions = []
    for node in document.find_all("ClassDescription"):
        uuid = node.get("UUID")
        name = node.get("Name")
        if not uuid or not name:
            continue
        fields = {
            attr.id: attr.text
            for attr in node.attributes.values()
            if attr.text is not None
        }
        display = node.attributes.get("DisplayName")
        descriptions.append(
            ClassDescription(
                uuid=uuid.lower(),
                name=name,
                parent_uuid=(node.get("ParentGuid") or "").lower() or None,
                spell_list_uuid=(node.get("SpellList") or "").lower() or None,
                can_learn_spells=_to_bool(node.get("CanLearnSpells")),
                must_prepare_spells=_to_bool(node.get("MustPrepareSpells")),
                progression_table_uuid=(
                    (node.get("ProgressionTableUUID") or "").lower() or None
                ),
                primary_ability=_to_int(node.get("PrimaryAbility")),
                spellcasting_ability=_to_int(node.get("SpellCastingAbility")),
                base_hp=_to_int(node.get("BaseHp")),
                hp_per_level=_to_int(node.get("HpPerLevel")),
                display_name_handle=display.handle if display is not None else None,
                fields=fields,
                source=source,
            )
        )
    return descriptions
