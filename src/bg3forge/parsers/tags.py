"""Parser for the tag registry (``Public/<Mod>/Tags/*.lsf``).

Each file defines one tag: the UUID that templates reference from their
``Tags`` children, a stable engine name (``PALADIN``, ``WPN_LONGSWORD``),
optional localized display strings, and category memberships::

    <region id="Tags">
      <node id="Tags">
        <attribute id="UUID" type="guid" value="..." />
        <attribute id="Name" type="FixedString" value="PALADIN" />
        <attribute id="Description" type="LSString" value="..." />
        <attribute id="DisplayName" type="TranslatedString" handle="h..." />
        <attribute id="DisplayDescription" type="TranslatedString" handle="h..." />
        <attribute id="Icon" type="FixedString" value="" />
        <children>
          <node id="Categories">
            <children>
              <node id="Category">
                <attribute id="Name" type="LSString" value="Class" />
    ...

Resolving the ``DisplayName``/``DisplayDescription`` handles against
localization is the caller's job (:class:`bg3forge.game.Game` does it);
this module stays a pure format parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterator

from .lsx import LsxDocument


@dataclass
class Tag:
    uuid: str
    name: str = ""
    description: str = ""             # authoring description (unlocalized)
    icon: str | None = None
    categories: list[str] = field(default_factory=list)
    display_name_handle: str | None = None
    display_description_handle: str | None = None
    display_name: str = ""            # localized, filled by Game
    display_description: str = ""     # localized, filled by Game

    def _link(self, game) -> None:
        # Non-field attribute so dataclass serialization stays clean.
        self._game = game

    @cached_property
    def items(self) -> list:
        """Items whose root-template chain carries this tag (reverse edge)."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.items_with_tag(self.uuid)


def parse_tags(document: LsxDocument) -> list[Tag]:
    tags = []
    for node in document.find_all("Tags"):
        uuid = node.get("UUID")
        if not uuid:
            continue
        categories = [
            name
            for category in node.find_all("Category")
            if (name := category.get("Name"))
        ]
        tags.append(
            Tag(
                uuid=uuid,
                name=node.get("Name", "") or "",
                description=node.get("Description", "") or "",
                icon=node.get("Icon") or None,
                categories=categories,
                display_name_handle=node.get("DisplayName"),
                display_description_handle=node.get("DisplayDescription"),
            )
        )
    return tags


class TagRegistry:
    """UUID → tag lookup that also answers to engine names.

    ``registry["64bd4b15-..."]`` and ``registry["PALADIN"]`` both work;
    iteration yields tags in insertion order.
    """

    def __init__(self):
        self._by_uuid: dict[str, Tag] = {}
        self._by_name: dict[str, Tag] = {}

    def __len__(self) -> int:
        return len(self._by_uuid)

    def __iter__(self) -> Iterator[Tag]:
        return iter(self._by_uuid.values())

    def __contains__(self, key: str) -> bool:
        return key in self._by_uuid or key in self._by_name

    def __getitem__(self, key: str) -> Tag:
        tag = self.get(key)
        if tag is None:
            raise KeyError(f"no tag with UUID or name {key!r}")
        return tag

    def get(self, key: str, default: Tag | None = None) -> Tag | None:
        return self._by_uuid.get(key) or self._by_name.get(key, default)

    def add(self, tag: Tag) -> None:
        self._by_uuid[tag.uuid] = tag
        if tag.name:
            self._by_name[tag.name] = tag

    def add_document(self, document: LsxDocument) -> None:
        for tag in parse_tags(document):
            self.add(tag)
