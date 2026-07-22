"""Assemble a complete mod from Forge's write primitives (experimental).

This is the orchestration layer over the format writers.  A :class:`Mod`
mints stable UUIDs and localization handles, lays files out under the
folder convention BG3 expects, and packs them with :class:`PakWriter`::

    from bg3forge.authoring import Mod

    mod = Mod("SunforgedArmors", author="you")
    mod.new_armor(
        "ARM_Sunforged_Plate",
        armor_class=21,
        stats_using="_Armor",              # inherit stats from a base entry
        parent_template="<base-template-uuid>",  # reuse an item's visuals
        display_name="Sunforged Plate",
        description="Warm to the touch.",
        icon="Item_Plate_Body",
    )
    mod.build("SunforgedArmors.pak")

It writes only to the output path you choose and never touches the game
install.  UUIDs and handles are derived with UUID5 from the mod name, so
rebuilding the same mod reproduces byte-identical identifiers.

Two distinct inheritance axes, deliberately kept separate:

* ``stats_using`` inherits *stats* from another stats entry (by name).
* ``parent_template`` inherits *visuals/mesh* from another RootTemplate
  (by UUID) — the usual way to reuse an existing item's appearance.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from .parsers.localization import LocaEntry, write_loca
from .parsers.lsx import write_lsx
from .parsers.meta import ModuleInfo, build_meta_document
from .parsers.roottemplates import build_root_template_node, build_templates_document
from .parsers.stats import StatsDocument, StatsEntry, write_stats_document
from .pak.writer import PakWriter

# Fixed namespace so a given mod name always mints the same UUIDs/handles.
_NAMESPACE = uuid.UUID("f9e6c7a2-1b3d-5e4f-8a09-abcdef012345")


class Mod:
    """A mod under construction: add content, then :meth:`build` a ``.pak``."""

    def __init__(
        self,
        name: str,
        *,
        author: str = "",
        description: str = "",
        folder: str | None = None,
        version: tuple[int, int, int, int] = (1, 0, 0, 0),
        language: str = "English",
    ):
        self.name = name
        self.folder = folder or name
        self.language = language
        self.uuid = self.new_uuid("module")
        self.module = ModuleInfo(
            name=name,
            uuid=self.uuid,
            folder=self.folder,
            author=author,
            description=description,
            version=version,
        )
        self._stats: list[StatsEntry] = []
        self._templates: list = []
        self._loca: list[LocaEntry] = []

    # -- identifier minting --------------------------------------------------

    def new_uuid(self, key: str) -> str:
        """A stable UUID for ``key``, unique to this mod."""
        return str(uuid.uuid5(_NAMESPACE, f"{self.name}:{key}"))

    def add_string(self, key: str, text: str, version: int = 1) -> str:
        """Register a localized string and return its handle.

        The handle uses BG3's ``h<guid-with-g-separators>`` form and is the
        same string written into both the ``.loca`` and the referencing
        template, so it resolves back on load.
        """
        handle = "h" + str(uuid.uuid5(_NAMESPACE, f"{self.name}:handle:{key}")).replace("-", "g")
        self._loca.append(LocaEntry(key=handle, version=version, text=text))
        return handle

    # -- content -------------------------------------------------------------

    def new_item(
        self,
        name: str,
        *,
        item_type: str = "Object",
        stats_using: str | None = None,
        parent_template: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        tags=(),
        template_type: str = "item",
        data: dict[str, str] | None = None,
    ) -> str:
        """Add an item (a stats entry plus its RootTemplate) and return its
        template UUID.  ``name`` is the internal stats/template identifier;
        ``display_name`` is the localized name shown in game."""
        template_uuid = self.new_uuid(f"template:{name}")
        stats_data = dict(data or {})
        stats_data.setdefault("RootTemplate", template_uuid)
        self._stats.append(
            StatsEntry(name=name, type=item_type, using=stats_using, data=stats_data)
        )

        display_handle = (
            self.add_string(f"{name}:DisplayName", display_name) if display_name else None
        )
        description_handle = (
            self.add_string(f"{name}:Description", description) if description else None
        )
        self._templates.append(
            build_root_template_node(
                template_uuid,
                name,
                template_type=template_type,
                stats=name,
                icon=icon,
                display_name=display_handle,
                description=description_handle,
                parent_template_id=parent_template,
                tags=tags,
            )
        )
        return template_uuid

    def new_armor(
        self,
        name: str,
        *,
        armor_class: int | None = None,
        stats_using: str | None = None,
        parent_template: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        tags=(),
        data: dict[str, str] | None = None,
    ) -> str:
        """Convenience over :meth:`new_item` for ``type "Armor"`` entries."""
        stats_data = dict(data or {})
        if armor_class is not None:
            stats_data["ArmorClass"] = str(armor_class)
        return self.new_item(
            name,
            item_type="Armor",
            stats_using=stats_using,
            parent_template=parent_template,
            display_name=display_name,
            description=description,
            icon=icon,
            tags=tags,
            data=stats_data,
        )

    # -- packaging -----------------------------------------------------------

    def files(self) -> dict[str, bytes]:
        """The mod's archive entries as ``path -> bytes`` (what gets packed)."""
        entries: dict[str, bytes] = {
            f"Mods/{self.folder}/meta.lsx": write_lsx(
                build_meta_document(self.module)
            ).encode("utf-8"),
        }
        if self._stats:
            entries[
                f"Public/{self.folder}/Stats/Generated/Data/{self.folder}.txt"
            ] = write_stats_document(StatsDocument(entries=self._stats)).encode("utf-8")
        if self._templates:
            entries[
                f"Public/{self.folder}/RootTemplates/{self.folder}.lsx"
            ] = write_lsx(build_templates_document(self._templates)).encode("utf-8")
        if self._loca:
            entries[
                f"Localization/{self.language}/{self.folder}.loca"
            ] = write_loca(self._loca)
        return entries

    def build(self, output: str | Path) -> Path:
        """Pack the mod into a ``.pak`` at ``output`` and return its path."""
        writer = PakWriter()
        for name, data in self.files().items():
            writer.add(name, data)
        return writer.write(output)
