"""Parser for equipment set definitions.

``Public/<Mod>/Stats/Generated/Equipment.txt`` (note: *not* under
``Data/``) defines the equipment loadouts character templates reference
by name::

    new equipment "EQP_Gith_Soldier"
    add initialweaponset "Melee"
    add equipmentgroup
    add equipment entry "WPN_Greatsword"
    add equipmentgroup
    add equipment entry "ARM_ChainMail_Body_Githyanki"

Each ``add equipmentgroup`` starts a new slot group; the entries inside
it are stats names resolvable against the item collections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NEW_RE = re.compile(r'^new equipment\s+"(?P<name>[^"]*)"')
_WEAPONSET_RE = re.compile(r'^add initialweaponset\s+"(?P<name>[^"]*)"')
_ENTRY_RE = re.compile(r'^add equipment entry\s+"(?P<name>[^"]*)"')


@dataclass
class EquipmentSet:
    name: str
    initial_weapon_set: str | None = None
    groups: list[list[str]] = field(default_factory=list)  # stats names per slot group
    source: str | None = None

    # NamedCollection compatibility
    @property
    def display_name(self) -> str:
        return ""

    def entries(self) -> list[str]:
        """Every referenced stats name across all groups, in order."""
        return [entry for group in self.groups for entry in group]


def parse_equipment_sets(text: str, source: str | None = None) -> list[EquipmentSet]:
    sets: list[EquipmentSet] = []
    current: EquipmentSet | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if match := _NEW_RE.match(line):
            current = EquipmentSet(name=match.group("name"), source=source)
            sets.append(current)
        elif current is None:
            continue  # tolerate directives before any set
        elif match := _WEAPONSET_RE.match(line):
            current.initial_weapon_set = match.group("name")
        elif line == "add equipmentgroup":
            current.groups.append([])
        elif match := _ENTRY_RE.match(line):
            if not current.groups:
                current.groups.append([])
            current.groups[-1].append(match.group("name"))
    return sets
