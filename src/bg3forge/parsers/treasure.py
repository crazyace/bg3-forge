"""Parser for treasure table ``.txt`` files.

Format (``Public/<Mod>/Stats/Generated/TreasureTable.txt``)::

    new treasuretable "TUT_Chest_Potions"
    CanMerge 1
    new subtable "1,1"
    object category "I_OBJ_Potion_Healing",1,0,0,0,0,0,0,0
    object category "T_EmptyChest",3,0,0,0,0,0,0,0
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TABLE_RE = re.compile(r'^new treasuretable\s+"(?P<name>[^"]*)"')
_SUBTABLE_RE = re.compile(r'^new subtable\s+"(?P<counts>[^"]*)"')
_OBJECT_RE = re.compile(r'^object category\s+"(?P<name>[^"]*)"\s*,\s*(?P<rest>.*)$')


@dataclass
class TreasureObject:
    name: str
    frequency: int = 1

    @property
    def is_item(self) -> bool:
        """True for direct item drops (``I_`` prefix)."""
        return self.name.startswith("I_")


@dataclass
class TreasureSubtable:
    drop_counts: str
    objects: list[TreasureObject] = field(default_factory=list)


@dataclass
class TreasureTable:
    name: str
    can_merge: bool = False
    subtables: list[TreasureSubtable] = field(default_factory=list)

    def items(self) -> list[str]:
        """All directly dropped item stat names, stripped of the I_ prefix."""
        result = []
        for subtable in self.subtables:
            for obj in subtable.objects:
                if obj.is_item:
                    result.append(obj.name[2:])
        return result


#: The rarity/type header base-game treasure files declare up top.
DEFAULT_ITEM_TYPES = (
    "Common", "Uncommon", "Rare", "Epic", "Legendary", "Divine", "Unique",
)


def write_treasure_tables(
    tables: list[TreasureTable], item_types=DEFAULT_ITEM_TYPES
) -> str:
    """Serialize treasure tables back to ``TreasureTable.txt`` form.

    The inverse of :func:`parse_treasure_tables`.  A mod reuses an existing
    table name with ``can_merge`` set to *inject* drops into a base-game
    container rather than replace it; each object's name carries the ``I_``
    prefix for a direct item drop.
    """
    lines = ["treasure itemtypes " + ",".join(f'"{t}"' for t in item_types)]
    for table in tables:
        lines.append(f'new treasuretable "{table.name}"')
        if table.can_merge:
            lines.append("CanMerge 1")
        for subtable in table.subtables:
            lines.append(f'new subtable "{subtable.drop_counts}"')
            for obj in subtable.objects:
                lines.append(
                    f'object category "{obj.name}",{obj.frequency},0,0,0,0,0,0,0'
                )
    return "\n".join(lines) + "\n"


def parse_treasure_tables(text: str) -> list[TreasureTable]:
    tables: list[TreasureTable] = []
    table: TreasureTable | None = None
    subtable: TreasureSubtable | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if match := _TABLE_RE.match(line):
            table = TreasureTable(name=match.group("name"))
            tables.append(table)
            subtable = None
        elif table is None:
            continue
        elif line.startswith("CanMerge"):
            table.can_merge = line.split()[-1] not in ("0", "CanMerge")
        elif match := _SUBTABLE_RE.match(line):
            subtable = TreasureSubtable(drop_counts=match.group("counts"))
            table.subtables.append(subtable)
        elif match := _OBJECT_RE.match(line):
            if subtable is None:
                subtable = TreasureSubtable(drop_counts="1,1")
                table.subtables.append(subtable)
            frequency_raw = match.group("rest").split(",")[0].strip()
            frequency = int(frequency_raw) if frequency_raw.isdigit() else 1
            subtable.objects.append(
                TreasureObject(name=match.group("name"), frequency=frequency)
            )
    return tables
