"""Typed domain models built on top of the raw parsers.

Each model wraps a resolved stats entry (inheritance applied) plus, where
available, localized display text and the owning root template.  Models
are plain dataclasses so they serialize cleanly through the exporters via
:func:`to_record`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Stats `type` values that map to each model.
ITEM_TYPES = ("Armor", "Weapon", "Object")
SPELL_TYPE = "SpellData"
PASSIVE_TYPE = "PassiveData"
STATUS_TYPE = "StatusData"
INTERRUPT_TYPE = "InterruptData"


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


@dataclass
class Item(GameObject):
    map_key: str | None = None  # root template MapKey, when matched
    rarity: str = "Common"
    slot: str | None = None
    value: int | None = None
    weight: float | None = None

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
