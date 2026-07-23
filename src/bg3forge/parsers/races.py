"""Race records — the race/subrace half of the character-origin joins.

``Race`` nodes (from ``Races.lsx``) form a tree via ``ParentGuid``: the
root ``Humanoid`` has no progression table, playable races hang off it
with a ``ProgressionTableUUID``, and subraces hang off the races.  The
census over retail (Patch 8) shows exactly nine attributes; the bulky
children are character-creation cosmetics (hair/skin/eye color banks,
visuals), which are deliberately not modeled — only the ``Tags`` child
is captured, joining the tag registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from .lsx import LsxDocument


@dataclass
class Race:
    uuid: str
    name: str
    parent_uuid: str | None = None
    progression_table_uuid: str | None = None
    race_equipment: str | None = None
    display_name_handle: str | None = None
    description_handle: str | None = None
    tag_ids: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    source: str | None = None

    # Resolved against the loca table when linked to a Game.
    display_name: str = ""
    description: str = ""

    def _link(self, game) -> None:
        self._game = game

    @cached_property
    def parent(self):
        """The parent race (or None for roots like ``Humanoid``)."""
        game = getattr(self, "_game", None)
        if game is None or not self.parent_uuid:
            return None
        for race in game.races:
            if race.uuid == self.parent_uuid:
                return race
        return None

    @cached_property
    def subraces(self) -> list["Race"]:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [race for race in game.races if race.parent_uuid == self.uuid]

    @cached_property
    def progressions(self) -> list:
        """This race's level records, ordered by level."""
        game = getattr(self, "_game", None)
        if game is None or not self.progression_table_uuid:
            return []
        return game.progressions.by_table(self.progression_table_uuid)

    @cached_property
    def tags(self) -> list:
        """Resolved :class:`Tag` objects for the race's ``Tags`` children."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [tag for uuid in self.tag_ids if (tag := game.tags.get(uuid))]


def parse_races(document: LsxDocument, source: str | None = None) -> list[Race]:
    races = []
    for node in document.find_all("Race"):
        uuid = node.get("UUID")
        name = node.get("Name")
        if not uuid or not name:
            continue
        fields = {
            attr.id: attr.text
            for attr in node.attributes.values()
            if attr.text is not None
        }
        tag_ids = [
            obj
            for child in node.children
            if child.id == "Tags"
            for tag in child.children
            if (obj := tag.get("Object"))
        ]
        display = node.attributes.get("DisplayName")
        description = node.attributes.get("Description")
        races.append(
            Race(
                uuid=uuid.lower(),
                name=name,
                parent_uuid=(node.get("ParentGuid") or "").lower() or None,
                progression_table_uuid=(
                    (node.get("ProgressionTableUUID") or "").lower() or None
                ),
                race_equipment=node.get("RaceEquipment"),
                display_name_handle=display.handle if display is not None else None,
                description_handle=(
                    description.handle if description is not None else None
                ),
                tag_ids=tag_ids,
                fields=fields,
                source=source,
            )
        )
    return races
