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
from .parsers.lsf import write_lsf
from .parsers.lsx import write_lsx
from .parsers.meta import ModuleInfo, build_meta_document
from .parsers.roottemplates import (
    build_consume_action,
    build_root_template_node,
    build_templates_document,
    build_use_spell_action,
)
from .parsers.stats import StatsDocument, StatsEntry, write_stats_document
from .parsers.treasure import (
    TreasureObject,
    TreasureSubtable,
    TreasureTable,
    write_treasure_tables,
)
from .pak.writer import PakWriter

# Fixed namespace so a given mod name always mints the same UUIDs/handles.
_NAMESPACE = uuid.UUID("f9e6c7a2-1b3d-5e4f-8a09-abcdef012345")

# BG3 loads a module's RootTemplates from a binary LSF named exactly
# `_merged.lsf` -- an arbitrary `.lsx` in that folder is ignored. Version 7
# (VerBG3Patch3) matches current retail (Patch 8) output.
_ROOTTEMPLATE_LSF_VERSION = 7


def _merge_semicolon(existing: str | None, *groups) -> str:
    """Join an existing ``;``-separated stats field with more entries."""
    parts: list[str] = []
    if existing:
        parts.extend(p.strip() for p in existing.split(";") if p.strip())
    for group in groups:
        parts.extend(group)
    return ";".join(parts)


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
        self._treasure: dict[str, TreasureTable] = {}

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

    def place_in_treasure(
        self, table_name: str, item_name: str, *, frequency: int = 1
    ) -> None:
        """Make an item obtainable by injecting it into an existing treasure
        table (e.g. ``"TUT_Chest_Potions"`` for the tutorial chest).

        The table is emitted with ``CanMerge`` so the item is *added* to the
        base-game container rather than replacing it.
        """
        table = self._treasure.get(table_name)
        if table is None:
            table = TreasureTable(name=table_name, can_merge=True)
            self._treasure[table_name] = table
        table.subtables.append(
            TreasureSubtable(
                drop_counts="-1",
                objects=[TreasureObject(name=f"I_{item_name}", frequency=frequency)],
            )
        )

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
        effect_description: str | None = None,
        on_use_description: str | None = None,
        icon: str | None = None,
        tags=(),
        boosts=(),
        passives=(),
        statuses=(),
        grants_spells=(),
        treasure: str | None = None,
        on_use=(),
        template_type: str = "item",
        data: dict[str, str] | None = None,
    ) -> str:
        """Add an item (a stats entry plus its RootTemplate) and return its
        template UUID.  ``name`` is the internal stats/template identifier;
        ``display_name`` is the localized name shown in game.

        The text slots match BG3's tooltip layout: ``display_name`` is the
        item name, ``description`` the *italic flavor* line,
        ``effect_description`` the golden effect blurb
        (``TechnicalDescription`` — supports ``<LSTag ...>`` hyperlinks),
        and ``on_use_description`` the use-verb label (retail: "Drink").
        When cloning via ``parent_template``, unset slots inherit the
        base's text.

        Pass ``treasure="<TableName>"`` to make the item obtainable by
        injecting it into an existing treasure table (see
        :meth:`place_in_treasure`).

        The ability parameters apply when the item is equipped:
        ``boosts`` are boost functions (``"Ability(Strength,2)"``, ``"AC(1)"``,
        …), ``grants_spells`` are spell names added as ``UnlockSpell(...)``
        boosts, ``passives`` populate ``PassivesOnEquip``, and ``statuses``
        populate ``StatusOnEquip``.  Each merges with any matching key already
        in ``data``.
        """
        template_uuid = self.new_uuid(f"template:{name}")
        stats_data = dict(data or {})
        stats_data.setdefault("RootTemplate", template_uuid)

        boost_field = _merge_semicolon(
            stats_data.get("Boosts"), boosts, [f"UnlockSpell({s})" for s in grants_spells]
        )
        if boost_field:
            stats_data["Boosts"] = boost_field
        passive_field = _merge_semicolon(stats_data.get("PassivesOnEquip"), passives)
        if passive_field:
            stats_data["PassivesOnEquip"] = passive_field
        status_field = _merge_semicolon(stats_data.get("StatusOnEquip"), statuses)
        if status_field:
            stats_data["StatusOnEquip"] = status_field

        self._stats.append(
            StatsEntry(name=name, type=item_type, using=stats_using, data=stats_data)
        )

        display_handle = (
            self.add_string(f"{name}:DisplayName", display_name) if display_name else None
        )
        description_handle = (
            self.add_string(f"{name}:Description", description) if description else None
        )
        effect_handle = (
            self.add_string(f"{name}:TechnicalDescription", effect_description)
            if effect_description
            else None
        )
        on_use_handle = (
            self.add_string(f"{name}:OnUseDescription", on_use_description)
            if on_use_description
            else None
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
                technical_description=effect_handle,
                on_use_description=on_use_handle,
                parent_template_id=parent_template,
                tags=tags,
                on_use=on_use,
            )
        )
        if treasure:
            self.place_in_treasure(treasure, name)
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
        boosts=(),
        passives=(),
        statuses=(),
        grants_spells=(),
        treasure: str | None = None,
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
            boosts=boosts,
            passives=passives,
            statuses=statuses,
            grants_spells=grants_spells,
            treasure=treasure,
            data=stats_data,
        )

    def new_weapon(
        self,
        name: str,
        *,
        damage: str | None = None,
        damage_type: str | None = None,
        weapon_properties=(),
        stats_using: str | None = None,
        parent_template: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        tags=(),
        boosts=(),
        grants_spells=(),
        default_boosts=(),
        passives=(),
        statuses=(),
        treasure: str | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        """Convenience over :meth:`new_item` for ``type "Weapon"`` entries.

        ``damage`` (e.g. ``"2d6"``), ``damage_type`` (e.g. ``"Slashing"``),
        and ``weapon_properties`` (e.g. ``["Twohanded", "Heavy", "Melee"]``)
        set the corresponding stats fields.  Unlike armor, a weapon's on-wield
        effects live in ``BoostsOnEquipMainHand``: ``boosts`` and
        ``grants_spells`` (weapon actions added as ``UnlockSpell(...)``) go
        there, while ``default_boosts`` (always-on, e.g.
        ``"WeaponProperty(Magical)"``) go in ``DefaultBoosts``.
        """
        stats_data = dict(data or {})
        if damage is not None:
            stats_data["Damage"] = damage
        if damage_type is not None:
            stats_data["Damage Type"] = damage_type
        if weapon_properties:
            stats_data["Weapon Properties"] = _merge_semicolon(
                stats_data.get("Weapon Properties"), weapon_properties
            )
        mainhand = _merge_semicolon(
            stats_data.get("BoostsOnEquipMainHand"),
            boosts,
            [f"UnlockSpell({s})" for s in grants_spells],
        )
        if mainhand:
            stats_data["BoostsOnEquipMainHand"] = mainhand
        if default_boosts:
            stats_data["DefaultBoosts"] = _merge_semicolon(
                stats_data.get("DefaultBoosts"), default_boosts
            )
        # passives/statuses share field names with armor; the weapon's
        # on-wield boosts are already folded into stats_data above.
        return self.new_item(
            name,
            item_type="Weapon",
            stats_using=stats_using,
            parent_template=parent_template,
            display_name=display_name,
            description=description,
            icon=icon,
            tags=tags,
            passives=passives,
            statuses=statuses,
            treasure=treasure,
            data=stats_data,
        )

    def new_potion(
        self,
        name: str,
        *,
        status: str,
        duration: int = 0,
        stats_using: str | None = "_Potion",
        parent_template: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        effect_description: str | None = None,
        on_use_description: str | None = None,
        icon: str | None = None,
        treasure: str | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        """A drinkable consumable: using it applies ``status`` (a StatusData
        name) and consumes the item.  ``duration`` follows retail usage:
        ``0`` = instant/permanent-style, ``-1`` = until long rest, or a
        positive number of turns (retail uses 1-50 and beyond).

        The mechanism matches retail potions — an ``OnUsePeaceActions``
        Consume action on the template with ``StatsId``/``StatusDuration``,
        while the stats entry (``using "_Potion"`` by default) carries the
        bonus-action cost, Consumable tab, and use conditions.

        Set ``effect_description`` to the golden effect blurb shown on the
        item tooltip (``TechnicalDescription``; supports ``<LSTag ...>``
        hyperlinks).  When cloning a base via ``parent_template``, leaving
        it unset inherits the *base's* blurb (e.g. the healing potion's
        "Heals and removes Burning").  ``on_use_description`` is only the
        use-verb label ("Drink").
        """
        return self.new_item(
            name,
            item_type="Object",
            stats_using=stats_using,
            parent_template=parent_template,
            display_name=display_name,
            description=description,
            effect_description=effect_description,
            on_use_description=on_use_description,
            icon=icon,
            treasure=treasure,
            on_use=[build_consume_action(status, duration)],
            data=data,
        )

    def new_elixir(
        self,
        name: str,
        *,
        status: str,
        stats_using: str | None = "_Potion",
        parent_template: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        effect_description: str | None = None,
        on_use_description: str | None = None,
        icon: str | None = None,
        treasure: str | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        """A potion whose ``status`` lasts until long rest
        (``StatusDuration -1``), the retail elixir pattern."""
        return self.new_potion(
            name,
            status=status,
            duration=-1,
            stats_using=stats_using,
            parent_template=parent_template,
            display_name=display_name,
            description=description,
            effect_description=effect_description,
            on_use_description=on_use_description,
            icon=icon,
            treasure=treasure,
            data=data,
        )

    def new_scroll(
        self,
        name: str,
        *,
        spell: str,
        stats_using: str | None = "OBJ_Scroll",
        parent_template: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        effect_description: str | None = None,
        on_use_description: str | None = None,
        icon: str | None = None,
        treasure: str | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        """A spell scroll: using it casts ``spell`` (a SpellData name) and
        consumes the item — the retail cast-from-scroll action, gated by
        ``CanUseSpellScroll``."""
        return self.new_item(
            name,
            item_type="Object",
            stats_using=stats_using,
            parent_template=parent_template,
            display_name=display_name,
            description=description,
            effect_description=effect_description,
            on_use_description=on_use_description,
            icon=icon,
            treasure=treasure,
            on_use=[build_use_spell_action(spell)],
            data=data,
        )

    def new_status(
        self,
        name: str,
        *,
        boosts=(),
        on_apply=(),
        display_name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        status_type: str = "BOOST",
        stack_id: str | None = None,
        apply_effect: str | None = None,
        description_params=(),
        property_flags=(),
        data: dict[str, str] | None = None,
    ) -> str:
        """Define a *custom* status (a ``type "StatusData"`` entry) and return
        its name, for use in ``new_potion(status=...)`` / ``new_elixir`` or an
        item's ``statuses=[...]``.

        ``boosts`` are effects active while the status lasts (e.g.
        ``"Ability(Strength,2)"``); ``on_apply`` are instant
        ``OnApplyFunctors`` (e.g. ``"RegainHitPoints(2d4+2)"``).  ``StackId``
        defaults to the status name, matching retail statuses.  Handles carry
        the ``;version`` suffix StatusData uses.

        Visibility: with no ``property_flags`` the status announces itself —
        overhead floating name, combat-log line, and portrait indicator (the
        channels retail's ``POTION_OF_HEALING`` explicitly disables with
        ``DisableOverhead;DisableCombatlog;DisablePortraitIndicator``).
        ``apply_effect`` plays a VFX on application (a resource GUID — e.g.
        the healing potion's swirl).
        """
        stats_data = dict(data or {})
        stats_data.setdefault("StatusType", status_type)
        stats_data.setdefault("StackId", stack_id or name)
        if display_name:
            handle = self.add_string(f"{name}:DisplayName", display_name)
            stats_data["DisplayName"] = f"{handle};1"
        if description:
            handle = self.add_string(f"{name}:Description", description)
            stats_data["Description"] = f"{handle};1"
        boost_field = _merge_semicolon(stats_data.get("Boosts"), boosts)
        if boost_field:
            stats_data["Boosts"] = boost_field
        apply_field = _merge_semicolon(stats_data.get("OnApplyFunctors"), on_apply)
        if apply_field:
            stats_data["OnApplyFunctors"] = apply_field
        if icon:
            stats_data["Icon"] = icon
        if apply_effect:
            stats_data["ApplyEffect"] = apply_effect
        if description_params:
            # values substituted into [1], [2], ... placeholders in the text
            stats_data["DescriptionParams"] = ";".join(
                str(v) for v in description_params
            )
        flags_field = _merge_semicolon(
            stats_data.get("StatusPropertyFlags"), property_flags
        )
        if flags_field:
            stats_data["StatusPropertyFlags"] = flags_field
        self._stats.append(
            StatsEntry(name=name, type="StatusData", using=None, data=stats_data)
        )
        return name

    def new_passive(
        self,
        name: str,
        *,
        using: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        boosts=(),
        properties=("Highlighted",),
        icon: str | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        """Define a *custom* passive (a ``type "PassiveData"`` stats entry) and
        return its name, for use in an item's ``passives=[...]``.

        ``boosts`` are the effects it applies (e.g.
        ``"DamageReduction(All, Flat, 3)"``).  ``properties`` default to
        ``"Highlighted"`` so the passive shows on the character sheet.  A
        passive is stats-only — it has no template and isn't obtainable on its
        own; grant it through an item.  Note BG3 references a PassiveData
        ``DisplayName``/``Description`` handle with a ``;<version>`` suffix.
        """
        stats_data = dict(data or {})
        if display_name:
            handle = self.add_string(f"{name}:DisplayName", display_name)
            stats_data["DisplayName"] = f"{handle};1"
        if description:
            handle = self.add_string(f"{name}:Description", description)
            stats_data["Description"] = f"{handle};1"
        boost_field = _merge_semicolon(stats_data.get("Boosts"), boosts)
        if boost_field:
            stats_data["Boosts"] = boost_field
        if properties:
            stats_data["Properties"] = _merge_semicolon(
                stats_data.get("Properties"), properties
            )
        if icon:
            stats_data["Icon"] = icon
        self._stats.append(
            StatsEntry(name=name, type="PassiveData", using=using, data=stats_data)
        )
        return name

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
                f"Public/{self.folder}/RootTemplates/_merged.lsf"
            ] = write_lsf(
                build_templates_document(self._templates),
                version=_ROOTTEMPLATE_LSF_VERSION,
            )
        if self._loca:
            entries[
                f"Localization/{self.language}/{self.folder}.loca"
            ] = write_loca(self._loca)
        if self._treasure:
            entries[
                f"Public/{self.folder}/Stats/Generated/TreasureTable.txt"
            ] = write_treasure_tables(list(self._treasure.values())).encode("utf-8")
        return entries

    def build(self, output: str | Path) -> Path:
        """Pack the mod into a ``.pak`` at ``output`` and return its path."""
        writer = PakWriter()
        for name, data in self.files().items():
            writer.add(name, data)
        return writer.write(output)
