"""Extract class/race progression tables from progression resources.

Progressions are level records.  ``TableUUID`` groups the records that
belong to one class, subclass, or race progression; selectors reference
spell-list UUIDs rather than spell stats names directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
import re
from typing import Iterable

from .lsx import LsxDocument


_SPELL_LIST_SELECTOR_RE = re.compile(
    r"\b(?P<kind>AddSpells|SelectSpells)\(\s*"
    r"(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


@dataclass
class Progression:
    uuid: str
    name: str
    table_uuid: str
    level: int
    progression_type: int
    fields: dict[str, str] = field(default_factory=dict)
    subclass_ids: list[str] = field(default_factory=list)
    source: str | None = None

    # Collection compatibility.  Progression names repeat across levels, so
    # ProgressionCollection indexes these objects by UUID instead.
    @property
    def display_name(self) -> str:
        return self.name

    def _link(self, game) -> None:
        self._game = game

    @property
    def boosts(self) -> list[str]:
        return _split_list(self.fields.get("Boosts"))

    @property
    def selectors(self) -> list[str]:
        return _split_list(self.fields.get("Selectors"))

    @property
    def passives_added(self) -> list[str]:
        return _split_list(self.fields.get("PassivesAdded"))

    @property
    def passives_removed(self) -> list[str]:
        return _split_list(self.fields.get("PassivesRemoved"))

    @property
    def is_multiclass(self) -> bool:
        return self.fields.get("IsMulticlass", "").lower() in ("true", "1")

    @property
    def allow_improvement(self) -> bool:
        return self.fields.get("AllowImprovement", "").lower() in ("true", "1")

    def _spell_list_ids(self, kind: str) -> list[str]:
        ids = []
        for selector in self.selectors:
            match = _SPELL_LIST_SELECTOR_RE.search(selector)
            if match and match.group("kind").lower() == kind.lower():
                ids.append(match.group("uuid").lower())
        return ids

    @property
    def added_spell_list_ids(self) -> list[str]:
        """Spell-list UUIDs used by ``AddSpells(...)`` selectors."""
        return self._spell_list_ids("AddSpells")

    @property
    def selectable_spell_list_ids(self) -> list[str]:
        """Spell-list UUIDs used by ``SelectSpells(...)`` selectors."""
        return self._spell_list_ids("SelectSpells")

    def _resolve_spell_lists(self, ids: list[str]) -> list:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [spell_list for uuid in ids if (spell_list := game.spell_lists.get(uuid))]

    @cached_property
    def added_spell_lists(self) -> list:
        return self._resolve_spell_lists(self.added_spell_list_ids)

    @cached_property
    def selectable_spell_lists(self) -> list:
        return self._resolve_spell_lists(self.selectable_spell_list_ids)

    @cached_property
    def passives(self) -> list:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [game.passives[name] for name in self.passives_added if name in game.passives]

    @cached_property
    def removed_passives(self) -> list:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [game.passives[name] for name in self.passives_removed if name in game.passives]

    @cached_property
    def spells(self) -> list:
        """Spells granted unconditionally through ``AddSpells(...)``.

        ``SelectSpells(...)`` options live in :attr:`selectable_spells` so a
        choice is never misrepresented as an automatic grant.
        """
        return _unique_spells(self.added_spell_lists)

    @cached_property
    def selectable_spells(self) -> list:
        return _unique_spells(self.selectable_spell_lists)


class ProgressionCollection(list[Progression]):
    """Progression records indexed by UUID and grouped by table/level.

    Names deliberately are not keys: one progression name normally occurs
    at many levels, and level one can have distinct single- and multiclass
    records.  UUID lookup and ``by_table`` therefore stay unambiguous.
    """

    def __init__(self, progressions: Iterable[Progression] = ()):
        super().__init__(progressions)
        self._by_uuid = {progression.uuid.lower(): progression for progression in self}
        self._by_table: dict[str, list[Progression]] = {}
        for progression in self:
            if not progression.table_uuid:
                continue
            self._by_table.setdefault(progression.table_uuid.lower(), []).append(
                progression
            )

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return self._by_uuid[key.lower()]
            except KeyError:
                raise KeyError(f"no progression with UUID {key!r}") from None
        return super().__getitem__(key)

    def __contains__(self, key) -> bool:
        if isinstance(key, str):
            return key.lower() in self._by_uuid
        return super().__contains__(key)

    def get(self, uuid: str, default=None):
        return self._by_uuid.get(uuid.lower(), default)

    @property
    def table_ids(self) -> list[str]:
        return list(self._by_table)

    def by_table(self, table_uuid: str) -> list[Progression]:
        """Records in one progression table, ordered by level."""
        return list(self._by_table.get(table_uuid.lower(), ()))

    def at_level(
        self, level: int, table_uuid: str | None = None
    ) -> list[Progression]:
        """Records at ``level``, optionally restricted to one table."""
        records = self.by_table(table_uuid) if table_uuid else self
        return [record for record in records if record.level == level]

    def find(self, query: str) -> list[Progression]:
        needle = query.lower()
        return [record for record in self if needle in record.name.lower()]


def _unique_spells(spell_lists) -> list:
    result = []
    seen: set[str] = set()
    for spell_list in spell_lists:
        for spell in spell_list.spells:
            if spell.name not in seen:
                result.append(spell)
                seen.add(spell.name)
    return result


def parse_progressions(
    document: LsxDocument, source: str | None = None
) -> list[Progression]:
    progressions = []
    for node in document.find_all("Progression"):
        uuid = node.get("UUID")
        if not uuid:
            continue
        fields = {
            attr.id: attr.text
            for attr in node.attributes.values()
            if attr.text is not None
        }
        subclass_ids = [
            value
            for subclass in node.find_all("SubClass")
            if (value := subclass.get("Object"))
        ]
        progressions.append(
            Progression(
                uuid=uuid.lower(),
                name=node.get("Name", "") or "",
                table_uuid=(node.get("TableUUID", "") or "").lower(),
                level=int(node.get("Level", "0") or 0),
                progression_type=int(node.get("ProgressionType", "0") or 0),
                fields=fields,
                subclass_ids=[value.lower() for value in subclass_ids],
                source=source,
            )
        )
    return progressions
