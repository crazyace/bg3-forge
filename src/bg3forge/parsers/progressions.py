"""Extract class/race progression tables from Progressions LSX files."""

from __future__ import annotations

from dataclasses import dataclass, field

from .lsx import LsxDocument


@dataclass
class Progression:
    uuid: str
    name: str
    table_uuid: str
    level: int
    progression_type: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def boosts(self) -> str | None:
        return self.fields.get("Boosts")

    @property
    def passives_added(self) -> list[str]:
        raw = self.fields.get("PassivesAdded", "")
        return [p for p in raw.split(";") if p]


def parse_progressions(document: LsxDocument) -> list[Progression]:
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
        progressions.append(
            Progression(
                uuid=uuid,
                name=node.get("Name", "") or "",
                table_uuid=node.get("TableUUID", "") or "",
                level=int(node.get("Level", "0") or 0),
                progression_type=int(node.get("ProgressionType", "0") or 0),
                fields=fields,
            )
        )
    return progressions
