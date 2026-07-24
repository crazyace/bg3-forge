"""Typed domain models built on top of the raw parsers.

Each model wraps a resolved stats entry (inheritance applied) plus, where
available, localized display text and the owning root template.  Models
are plain dataclasses so they serialize cleanly through the exporters via
:func:`to_record`.

Models built by :class:`~bg3forge.game.Game` are linked back to it,
forming a relationship graph: forward links resolve an object's
references, reverse links answer "who references me?"::

    sword = game.items["WPN_Longsword_Magic"]
    sword.passives        # [Passive(...)]  from PassivesOnEquip
    sword.statuses        # [Status(...)]   from StatusOnEquip
    sword.spells          # [Spell(...)]    from UnlockSpell(...) boosts
    sword.owner_templates # [RootTemplate(...)] whose Stats point here
    sword.tags            # tag UUIDs, merged down the template chain

    game.passives["SavageAttacks"].items   # ← items granting it
    game.spells["Projectile_Fireball"].items
    game.statuses["BURNING"].items

Every relationship resolves lazily on first access and is cached on the
instance (they are snapshots — treat them as read-only).  Nothing is
resolved for objects you never touch.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import Any, Iterable, TypeVar

# Stats `type` values that map to each model.
ITEM_TYPES = ("Armor", "Weapon", "Object")
SPELL_TYPE = "SpellData"
PASSIVE_TYPE = "PassiveData"
STATUS_TYPE = "StatusData"
INTERRUPT_TYPE = "InterruptData"
CHARACTER_TYPE = "Character"

_UNLOCK_SPELL_RE = re.compile(r"UnlockSpell\(\s*([^),\s]+)")

T = TypeVar("T", bound="GameObject")


class NamedCollection(list[T]):
    """A list of models that also supports lookup by stats name.

    ``collection["WPN_Longsword"]`` returns the model with that name;
    integer indexing and iteration behave like a normal list.  Treat it
    as a read-only snapshot — mutating it will not update the index.
    """

    def __init__(self, items: Iterable[T] = ()):
        super().__init__(items)
        self._by_name: dict[str, T] = {obj.name: obj for obj in self}

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return self._by_name[key]
            except KeyError:
                raise KeyError(f"no entry named {key!r}") from None
        return super().__getitem__(key)

    def __contains__(self, key) -> bool:
        if isinstance(key, str):
            return key in self._by_name
        return super().__contains__(key)

    def get(self, name: str, default: T | None = None) -> T | None:
        return self._by_name.get(name, default)

    def find(self, query: str) -> list[T]:
        """Case-insensitive substring search over names and display names."""
        needle = query.lower()
        return [
            obj
            for obj in self
            if needle in obj.name.lower() or needle in obj.display_name.lower()
        ]


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


@dataclass
class GameObject:
    """Base for anything derived from a stats entry."""

    name: str            # stats entry name, e.g. "WPN_Longsword"
    stats_type: str      # stats `type`, e.g. "Weapon"
    display_name: str = ""
    description: str = ""
    icon: str | None = None
    data: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.data.get(key, default)

    def _link(self, game) -> None:
        # Plain attribute (not a dataclass field) so asdict()/to_record()
        # never serialize the back-reference.
        self._game = game

    def _resolve(self, collection_name: str, names: list[str]) -> list:
        game = getattr(self, "_game", None)
        if game is None or not names:
            return []
        collection = getattr(game, collection_name)
        return [collection[name] for name in names if name in collection]

    def _granted_by(self, relation: str) -> list:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.items_granting(relation, self.name)


@dataclass
class Item(GameObject):
    map_key: str | None = None  # root template MapKey, when matched
    rarity: str = "Common"
    slot: str | None = None
    value: int | None = None
    weight: float | None = None

    @property
    def passive_names(self) -> list[str]:
        return _split_list(self.data.get("PassivesOnEquip"))

    @property
    def status_names(self) -> list[str]:
        return _split_list(self.data.get("StatusOnEquip"))

    @property
    def boosts(self) -> list[str]:
        return _split_list(self.data.get("Boosts"))

    @property
    def spell_names(self) -> list[str]:
        """Spells granted by this item via UnlockSpell(...) boosts."""
        return [m.group(1) for m in _UNLOCK_SPELL_RE.finditer(self.data.get("Boosts", ""))]

    @property
    def requirements(self) -> list[str]:
        """Raw requirement expressions, e.g. ``["Str 13"]``."""
        return _split_list(self.data.get("Requirements"))

    @cached_property
    def passives(self) -> list["Passive"]:
        return self._resolve("passives", self.passive_names)

    @cached_property
    def statuses(self) -> list["Status"]:
        return self._resolve("statuses", self.status_names)

    @cached_property
    def spells(self) -> list["Spell"]:
        return self._resolve("spells", self.spell_names)

    @cached_property
    def tag_ids(self) -> list[str]:
        """Tag UUIDs merged across the item's root-template chain."""
        game = getattr(self, "_game", None)
        if game is None or not self.map_key:
            return []
        return game.templates.resolved_tags(self.map_key)

    @cached_property
    def tags(self) -> list:
        """Resolved :class:`~bg3forge.parsers.tags.Tag` objects for this
        item (UUIDs without a registry entry are omitted — see
        ``tag_ids`` for the raw list)."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [tag for uuid in self.tag_ids if (tag := game.tags.get(uuid))]

    @cached_property
    def owner_templates(self) -> list:
        """Root templates whose ``Stats`` field points at this entry."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.templates.by_stats(self.name)

    @classmethod
    def from_stats(cls, name, stats_type, data, display_name="", description="", map_key=None):
        return cls(
            name=name,
            stats_type=stats_type,
            display_name=display_name,
            description=description,
            icon=data.get("Icon"),
            data=data,
            map_key=map_key,
            rarity=data.get("Rarity", "Common"),
            slot=data.get("Slot"),
            value=_to_int(data.get("ValueOverride")),
            weight=_to_float(data.get("Weight")),
        )


@dataclass
class Character(GameObject):
    """An NPC/creature stat block, joined to its root template.

    Unlike items, character stats entries don't name their template —
    the template's ``Stats`` field points here — so the join runs
    through ``RootTemplateIndex.by_stats``.
    """

    map_key: str | None = None       # owning template MapKey, when matched
    level: int = 0
    vitality: int | None = None      # hit points
    armor: int | None = None         # armor class
    strength: int | None = None
    dexterity: int | None = None
    constitution: int | None = None
    intelligence: int | None = None
    wisdom: int | None = None
    charisma: int | None = None
    archetype: str | None = None     # from the template
    equipment_name: str | None = None  # equipment set, from the template

    @property
    def passive_names(self) -> list[str]:
        return _split_list(self.data.get("Passives"))

    @cached_property
    def passives(self) -> list["Passive"]:
        return self._resolve("passives", self.passive_names)

    @cached_property
    def tag_ids(self) -> list[str]:
        game = getattr(self, "_game", None)
        if game is None or not self.map_key:
            return []
        return game.templates.resolved_tags(self.map_key)

    @cached_property
    def tags(self) -> list:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [tag for uuid in self.tag_ids if (tag := game.tags.get(uuid))]

    @cached_property
    def equipment(self):
        """The :class:`~bg3forge.parsers.equipment.EquipmentSet` the
        character's template references, if any."""
        game = getattr(self, "_game", None)
        if game is None or not self.equipment_name:
            return None
        return game.equipment.get(self.equipment_name)

    @cached_property
    def equipment_items(self) -> list["Item"]:
        """The character's loadout resolved into Item models (entries
        without a stats definition are omitted)."""
        if self.equipment is None:
            return []
        return self._resolve("items", self.equipment.entries())

    @classmethod
    def from_stats(cls, name, data, display_name="", description="",
                   map_key=None, archetype=None, equipment_name=None):
        return cls(
            name=name,
            stats_type=CHARACTER_TYPE,
            display_name=display_name,
            description=description,
            icon=data.get("Icon"),
            data=data,
            map_key=map_key,
            level=_to_int(data.get("Level")) or 0,
            vitality=_to_int(data.get("Vitality")),
            armor=_to_int(data.get("Armor")),
            strength=_to_int(data.get("Strength")),
            dexterity=_to_int(data.get("Dexterity")),
            constitution=_to_int(data.get("Constitution")),
            intelligence=_to_int(data.get("Intelligence")),
            wisdom=_to_int(data.get("Wisdom")),
            charisma=_to_int(data.get("Charisma")),
            archetype=archetype,
            equipment_name=equipment_name,
        )


@dataclass
class Spell(GameObject):
    spell_type: str = ""        # e.g. "Projectile", "Target", "Shout"
    level: int = 0
    school: str | None = None
    damage: str | None = None
    use_costs: str | None = None

    @cached_property
    def items(self) -> list["Item"]:
        """Items that unlock this spell (reverse of ``Item.spells``)."""
        return self._granted_by("spells")

    @cached_property
    def progressions(self) -> list:
        """Progressions that grant this spell via ``AddSpells``."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.progressions_granting_spell(self.name)

    @cached_property
    def progression_choices(self) -> list:
        """Progressions where this spell is an option via ``SelectSpells``."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.progressions_offering_spell(self.name)

    @classmethod
    def from_stats(cls, name, data, display_name="", description=""):
        return cls(
            name=name,
            stats_type=SPELL_TYPE,
            display_name=display_name,
            description=description,
            icon=data.get("Icon"),
            data=data,
            spell_type=data.get("SpellType", ""),
            level=_to_int(data.get("Level")) or 0,
            school=data.get("SpellSchool"),
            damage=data.get("Damage"),
            use_costs=data.get("UseCosts"),
        )


@dataclass
class Passive(GameObject):
    properties: str | None = None
    boosts: str | None = None

    @cached_property
    def items(self) -> list["Item"]:
        """Items that grant this passive (reverse of ``Item.passives``)."""
        return self._granted_by("passives")

    @cached_property
    def characters(self) -> list["Character"]:
        """Characters with this passive (reverse of ``Character.passives``)."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.characters_with_passive(self.name)

    @cached_property
    def progressions(self) -> list:
        """Progressions whose ``PassivesAdded`` grants this passive."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.progressions_granting_passive(self.name)

    @classmethod
    def from_stats(cls, name, data, display_name="", description=""):
        return cls(
            name=name,
            stats_type=PASSIVE_TYPE,
            display_name=display_name,
            description=description,
            icon=data.get("Icon"),
            data=data,
            properties=data.get("Properties"),
            boosts=data.get("Boosts"),
        )


@dataclass
class Status(GameObject):
    status_type: str = ""       # e.g. "BOOST", "POLYMORPHED"
    stack_id: str | None = None
    boosts: str | None = None

    @cached_property
    def items(self) -> list["Item"]:
        """Items that apply this status on equip (reverse of ``Item.statuses``)."""
        return self._granted_by("statuses")

    @classmethod
    def from_stats(cls, name, data, display_name="", description=""):
        return cls(
            name=name,
            stats_type=STATUS_TYPE,
            display_name=display_name,
            description=description,
            icon=data.get("Icon"),
            data=data,
            status_type=data.get("StatusType", ""),
            stack_id=data.get("StackId"),
            boosts=data.get("Boosts"),
        )


def to_record(obj: Any) -> dict[str, Any]:
    """Flatten a model (or plain dict) into an export-friendly dict.

    Raw ``data`` and ``fields`` mappings are folded into namespaced columns
    (``data.<Key>`` / ``fields.<Key>``).  List-valued dataclass fields are
    joined with ``;`` — the delimiter BG3 uses for these source lists — so
    CSV, SQLite, and flattened JSON contain stable scalar values.

    Plain dictionaries are treated as already normalized and returned
    unchanged.
    """
    if isinstance(obj, dict):
        return dict(obj)
    record = asdict(obj)
    for mapping_name in ("data", "fields"):
        values = record.pop(mapping_name, {}) or {}
        for key, value in values.items():
            record[f"{mapping_name}.{key}"] = value
    for key, value in record.items():
        if isinstance(value, (list, tuple)):
            record[key] = ";".join(str(item) for item in value)
    return record

def _to_int(value: str | None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_float(value: str | None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
