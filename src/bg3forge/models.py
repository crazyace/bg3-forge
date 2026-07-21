"""Typed domain models built on top of the raw parsers.

Each model wraps a resolved stats entry (inheritance applied) plus, where
available, localized display text and the owning root template.  Models
are plain dataclasses so they serialize cleanly through the exporters via
:func:`to_record`.

Models built by :class:`~bg3forge.game.Game` are linked back to it, so
cross-source references resolve without knowing where the data lives::

    sword = game.items["WPN_Longsword_Magic"]
    sword.passives   # [Passive(...)]  from PassivesOnEquip
    sword.statuses   # [Status(...)]   from StatusOnEquip
    sword.spells     # [Spell(...)]    from UnlockSpell(...) boosts
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, TypeVar

# Stats `type` values that map to each model.
ITEM_TYPES = ("Armor", "Weapon", "Object")
SPELL_TYPE = "SpellData"
PASSIVE_TYPE = "PassiveData"
STATUS_TYPE = "StatusData"
INTERRUPT_TYPE = "InterruptData"

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
    def passives(self) -> list["Passive"]:
        return self._resolve("passives", self.passive_names)

    @property
    def statuses(self) -> list["Status"]:
        return self._resolve("statuses", self.status_names)

    @property
    def spells(self) -> list["Spell"]:
        return self._resolve("spells", self.spell_names)

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
class Spell(GameObject):
    spell_type: str = ""        # e.g. "Projectile", "Target", "Shout"
    level: int = 0
    school: str | None = None
    damage: str | None = None
    use_costs: str | None = None

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

    The raw ``data`` mapping is folded in under ``data.<Key>`` columns so
    tabular exporters (CSV, SQLite) get stable scalar fields.
    """
    if isinstance(obj, dict):
        return dict(obj)
    record = asdict(obj)
    data = record.pop("data", {}) or {}
    for key, value in data.items():
        record[f"data.{key}"] = value
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
