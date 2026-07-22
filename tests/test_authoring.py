import pytest

from bg3forge import Mod
from bg3forge.pak.reader import PakReader
from bg3forge.parsers import (
    Localization,
    parse_lsx,
    parse_meta,
    parse_resource,
    parse_root_templates,
    parse_stats,
    parse_treasure_tables,
)


def test_mod_builds_a_loadable_item_pak(tmp_path):
    """The capstone end to end: assemble an item, pack it, read the pak back,
    and confirm every cross-reference resolves."""
    mod = Mod("SunforgedArmors", author="Me", description="A test mod.")
    template_uuid = mod.new_armor(
        "ARM_Sunforged_Plate",
        armor_class=21,
        stats_using="_Armor",
        parent_template="0000base-0000-0000-0000-00000000000f",
        display_name="Sunforged Plate",
        description="Warm to the touch.",
        icon="Item_Plate_Body",
    )
    pak = mod.build(tmp_path / "SunforgedArmors.pak")
    assert pak.exists()

    with PakReader(pak) as reader:
        names = reader.names()
        # files land under the folder convention the engine expects
        assert "Mods/SunforgedArmors/meta.lsx" in names
        stats_path = "Public/SunforgedArmors/Stats/Generated/Data/SunforgedArmors.txt"
        # BG3 loads RootTemplates only from a binary LSF named _merged.lsf
        template_path = "Public/SunforgedArmors/RootTemplates/_merged.lsf"
        loca_path = "Localization/English/SunforgedArmors.loca"
        assert {stats_path, template_path, loca_path} <= set(names)

        # stats: binds its RootTemplate and inherits from the base entry
        entry = parse_stats(reader.read(stats_path).decode("utf-8"))[0]
        assert entry.name == "ARM_Sunforged_Plate"
        assert entry.type == "Armor"
        assert entry.using == "_Armor"
        assert entry.get("ArmorClass") == "21"
        assert entry.get("RootTemplate") == template_uuid

        # template: points back at the stats entry and reuses the base visuals
        # (_merged.lsf is binary LSF; parse_resource sniffs the format)
        template = parse_root_templates(parse_resource(reader.read(template_path)))[0]
        assert template.map_key == template_uuid
        assert template.stats_name == "ARM_Sunforged_Plate"
        assert template.parent_id == "0000base-0000-0000-0000-00000000000f"
        assert template.icon == "Item_Plate_Body"

        # localization: the template's DisplayName handle resolves to the text
        loca = Localization()
        loca.load_bytes(reader.read(loca_path))
        assert loca.resolve(template.display_name_handle) == "Sunforged Plate"
        assert loca.resolve(template.description_handle) == "Warm to the touch."

        # manifest identity survives the round trip
        meta = parse_meta(parse_lsx(reader.read("Mods/SunforgedArmors/meta.lsx").decode("utf-8")))
        assert meta.name == "SunforgedArmors"
        assert meta.uuid == mod.uuid


def test_mod_identifiers_are_stable_across_rebuilds():
    """UUID5 minting means the same mod definition reproduces the same ids."""
    a = Mod("SunforgedArmors")
    b = Mod("SunforgedArmors")
    assert a.uuid == b.uuid
    assert a.new_armor("ARM_X") == b.new_armor("ARM_X")
    assert a.add_string("k", "text") == b.add_string("k", "text")


def test_empty_mod_still_produces_a_manifest(tmp_path):
    pak = Mod("EmptyMod").build(tmp_path / "EmptyMod.pak")
    with PakReader(pak) as reader:
        assert reader.names() == ["Mods/EmptyMod/meta.lsx"]


def test_folder_defaults_to_name_and_can_be_overridden(tmp_path):
    mod = Mod("My Mod", folder="MyMod")
    files = mod.files()
    assert "Mods/MyMod/meta.lsx" in files
    assert mod.module.folder == "MyMod"


def _stats_entry(mod):
    txt = mod.files()[
        f"Public/{mod.folder}/Stats/Generated/Data/{mod.folder}.txt"
    ].decode("utf-8")
    return parse_stats(txt)[0]


def test_ability_params_populate_equip_fields():
    """boosts / grants_spells / passives / statuses land in the right stats
    fields (verified in game: a +2 STR boost applied to the character)."""
    mod = Mod("AbilityMod")
    mod.new_armor(
        "ARM_Test",
        armor_class=18,
        boosts=["Ability(Strength,2)", "AC(1)"],
        grants_spells=["Target_Fireball"],
        passives=["SavageAttacker"],
        statuses=["MAG_BLADE_WARD"],
    )
    entry = _stats_entry(mod)
    assert entry.get("ArmorClass") == "18"
    assert entry.get("Boosts") == "Ability(Strength,2);AC(1);UnlockSpell(Target_Fireball)"
    assert entry.get("PassivesOnEquip") == "SavageAttacker"
    assert entry.get("StatusOnEquip") == "MAG_BLADE_WARD"


def test_ability_params_merge_with_explicit_data():
    mod = Mod("MergeMod")
    mod.new_item("I", data={"Boosts": "AC(2)"}, boosts=["Ability(Dexterity,1)"])
    assert _stats_entry(mod).get("Boosts") == "AC(2);Ability(Dexterity,1)"


def test_no_ability_params_leaves_fields_absent():
    mod = Mod("PlainMod")
    mod.new_armor("ARM_Plain", armor_class=12)
    entry = _stats_entry(mod)
    assert entry.get("Boosts") is None
    assert entry.get("PassivesOnEquip") is None


def test_treasure_param_makes_item_obtainable():
    """`treasure=` injects the item into an existing table with CanMerge so it
    drops from a base-game container (e.g. the tutorial chest)."""
    mod = Mod("TreasureMod")
    mod.new_armor("ARM_Test", armor_class=18, treasure="TUT_Chest_Potions")
    text = mod.files()[
        "Public/TreasureMod/Stats/Generated/TreasureTable.txt"
    ].decode("utf-8")
    table = parse_treasure_tables(text)[0]
    assert table.name == "TUT_Chest_Potions"
    assert table.can_merge
    assert table.items() == ["ARM_Test"]  # I_ prefix stripped


def test_no_treasure_means_no_treasure_file():
    mod = Mod("NoDrop")
    mod.new_armor("ARM_Test", armor_class=18)
    assert not any("TreasureTable" in name for name in mod.files())


def test_new_weapon_sets_weapon_fields_and_mainhand_boosts():
    """Weapons carry damage/properties, and on-wield effects go in
    BoostsOnEquipMainHand (not Boosts), matching retail weapon stats."""
    mod = Mod("WeaponMod")
    mod.new_weapon(
        "WPN_Divine_Greatsword",
        damage="2d6",
        damage_type="Slashing",
        weapon_properties=["Twohanded", "Heavy", "Melee"],
        boosts=["Ability(Strength,2)"],
        grants_spells=["Target_PommelStrike", "Zone_Cleave"],
        default_boosts=["WeaponProperty(Magical)"],
    )
    entry = parse_stats(
        mod.files()["Public/WeaponMod/Stats/Generated/Data/WeaponMod.txt"].decode("utf-8")
    )[0]
    assert entry.type == "Weapon"
    assert entry.get("Damage") == "2d6"
    assert entry.get("Damage Type") == "Slashing"
    assert entry.get("Weapon Properties") == "Twohanded;Heavy;Melee"
    assert entry.get("DefaultBoosts") == "WeaponProperty(Magical)"
    # weapon on-wield effects land in BoostsOnEquipMainHand, and Boosts stays clear
    assert entry.get("BoostsOnEquipMainHand") == (
        "Ability(Strength,2);UnlockSpell(Target_PommelStrike);UnlockSpell(Zone_Cleave)"
    )
    assert entry.get("Boosts") is None


def test_new_weapon_binds_template_and_can_be_placed_in_treasure():
    mod = Mod("WpnDrop")
    mod.new_weapon("WPN_Test", damage="1d8", stats_using="WPN_Longsword",
                   treasure="TUT_Chest_Potions")
    entry = parse_stats(
        mod.files()["Public/WpnDrop/Stats/Generated/Data/WpnDrop.txt"].decode("utf-8")
    )[0]
    assert entry.using == "WPN_Longsword"
    assert entry.get("RootTemplate")  # template UUID bound
    table = parse_treasure_tables(
        mod.files()["Public/WpnDrop/Stats/Generated/TreasureTable.txt"].decode("utf-8")
    )[0]
    assert table.items() == ["WPN_Test"]


def _entries_by_name(mod):
    txt = mod.files()[
        f"Public/{mod.folder}/Stats/Generated/Data/{mod.folder}.txt"
    ].decode("utf-8")
    return {e.name: e for e in parse_stats(txt)}


def test_new_passive_defines_passivedata_with_resolving_name():
    mod = Mod("PassiveMod")
    name = mod.new_passive(
        "MY_Warding",
        display_name="Warding",
        description="Take less damage.",
        boosts=["DamageReduction(All, Flat, 3)"],
    )
    assert name == "MY_Warding"
    entry = _entries_by_name(mod)["MY_Warding"]
    assert entry.type == "PassiveData"
    assert entry.get("Boosts") == "DamageReduction(All, Flat, 3)"
    assert entry.get("Properties") == "Highlighted"  # shows on the sheet by default
    # DisplayName is a handle carrying a ;version suffix, and it resolves
    display = entry.get("DisplayName")
    assert display.startswith("h") and display.endswith(";1")
    loca = Localization()
    loca.load_bytes(mod.files()["Localization/English/PassiveMod.loca"])
    assert loca.resolve(display) == "Warding"


def test_item_can_grant_a_custom_passive():
    mod = Mod("GrantMod")
    passive = mod.new_passive("MY_Warding", boosts=["AC(1)"])
    mod.new_armor("ARM_Warded", armor_class=15, passives=[passive])
    entries = _entries_by_name(mod)
    assert entries["MY_Warding"].type == "PassiveData"
    assert entries["ARM_Warded"].get("PassivesOnEquip") == "MY_Warding"


def _template_actions(mod, name):
    """Parse the built pak's _merged.lsf and return (node, actions) for name."""
    blob = mod.files()[f"Public/{mod.folder}/RootTemplates/_merged.lsf"]
    doc = parse_resource(blob)
    node = next(n for n in doc.find_all("GameObjects") if n.get("Name") == name)
    onuse = next((c for c in node.children if c.id == "OnUsePeaceActions"), None)
    return node, (onuse.children if onuse else [])


def test_new_potion_emits_consume_action():
    """Potion = Object stats (using _Potion) + template Consume action
    (ActionType 7, StatsId, StatusDuration 0) — the retail mechanism,
    surviving the LSF v7 round trip with typed attributes."""
    mod = Mod("PotionMod")
    mod.new_potion("OBJ_My_Potion", status="MY_BREW", display_name="My Brew")
    entry = _entries_by_name(mod)["OBJ_My_Potion"]
    assert entry.type == "Object"
    assert entry.using == "_Potion"
    node, actions = _template_actions(mod, "OBJ_My_Potion")
    assert len(actions) == 1
    action = actions[0]
    assert action.get("ActionType") == "7"
    assert action.attributes["ActionType"].type == "int32"
    attrs = action.children[0]  # <Attributes>
    assert attrs.get("StatsId") == "MY_BREW"
    assert attrs.get("StatusDuration") == "0"
    assert attrs.attributes["StatusDuration"].type == "int32"
    assert attrs.attributes["Consume"].type == "bool"


def test_new_elixir_lasts_until_long_rest():
    mod = Mod("ElixirMod")
    mod.new_elixir("OBJ_My_Elixir", status="MY_TONIC")
    _, actions = _template_actions(mod, "OBJ_My_Elixir")
    attrs = actions[0].children[0]
    assert attrs.get("StatusDuration") == "-1"


def test_new_scroll_emits_cast_action():
    """Scroll = OBJ_Scroll stats + cast-from-scroll action (ActionType 12,
    SkillID, CanUseSpellScroll condition, shared retail ClassId)."""
    from bg3forge.parsers import SCROLL_CLASS_ID

    mod = Mod("ScrollMod")
    mod.new_scroll("OBJ_Scroll_MyFireball", spell="Projectile_Fireball",
                   treasure="TUT_Chest_Potions")
    entry = _entries_by_name(mod)["OBJ_Scroll_MyFireball"]
    assert entry.using == "OBJ_Scroll"
    _, actions = _template_actions(mod, "OBJ_Scroll_MyFireball")
    assert len(actions) == 2  # cast (12) + learn (33), the retail pair
    action = actions[0]
    assert action.get("ActionType") == "12"
    attrs = action.children[0]
    assert attrs.get("SkillID") == "Projectile_Fireball"
    assert attrs.get("Conditions") == 'CanUseSpellScroll("Projectile_Fireball")'
    assert attrs.get("ClassId") == SCROLL_CLASS_ID
    assert attrs.attributes["ClassId"].type == "guid"
    learn = actions[1]
    assert learn.get("ActionType") == "33"
    learn_attrs = learn.children[0]
    assert learn_attrs.get("SpellId") == "Projectile_Fireball"  # not SkillID
    assert learn_attrs.get("Consume") == "True"
    assert learn_attrs.get("Conditions") == ""
    # obtainable like any other item
    table = parse_treasure_tables(
        mod.files()[f"Public/ScrollMod/Stats/Generated/TreasureTable.txt"].decode("utf-8")
    )[0]
    assert table.items() == ["OBJ_Scroll_MyFireball"]


def test_cast_only_scroll_omits_learn_action():
    """learnable=False matches retail's cast-only scrolls (54 of 165 ship
    no ActionType 33 — spells wizards can't transcribe)."""
    mod = Mod("ScrollMod")
    mod.new_scroll("OBJ_Scroll_NoLearn", spell="Target_CureWounds",
                   learnable=False)
    _, actions = _template_actions(mod, "OBJ_Scroll_NoLearn")
    assert [a.get("ActionType") for a in actions] == ["12"]


def test_new_status_defines_statusdata_with_retail_shape():
    """Custom StatusData: BOOST type, StackId defaulting to the name,
    Boosts + instant OnApplyFunctors, and a resolving ;version handle."""
    mod = Mod("StatusMod")
    name = mod.new_status(
        "FORGE_FIRE",
        boosts=["Ability(Strength,2)", "Resistance(Fire,Resistant)"],
        on_apply=["RegainHitPoints(1d4)"],
        display_name="Forgefire",
        description="Burning with creativity.",
        icon="GenericIcon_Intent_Buff",
    )
    assert name == "FORGE_FIRE"
    entry = _entries_by_name(mod)["FORGE_FIRE"]
    assert entry.type == "StatusData"
    assert entry.get("StatusType") == "BOOST"
    assert entry.get("StackId") == "FORGE_FIRE"  # defaults to the name
    assert entry.get("Boosts") == "Ability(Strength,2);Resistance(Fire,Resistant)"
    assert entry.get("OnApplyFunctors") == "RegainHitPoints(1d4)"
    display = entry.get("DisplayName")
    assert display.startswith("h") and display.endswith(";1")
    loca = Localization()
    loca.load_bytes(mod.files()["Localization/English/StatusMod.loca"])
    assert loca.resolve(display) == "Forgefire"


def test_new_status_visibility_knobs():
    """apply_effect becomes ApplyEffect (VFX on application) and
    property_flags fills StatusPropertyFlags; neither is emitted by default,
    so a custom status announces itself (overhead/log/portrait)."""
    mod = Mod("VisMod")
    mod.new_status("LOUD", boosts=["AC(1)"])
    loud = _entries_by_name(mod)["LOUD"]
    assert loud.get("StatusPropertyFlags") is None
    assert loud.get("ApplyEffect") is None

    mod2 = Mod("QuietMod")
    mod2.new_status(
        "QUIET",
        boosts=["AC(1)"],
        apply_effect="89f2d0ac-9295-4657-bfa6-fb6d61adf59c",
        property_flags=["DisableOverhead", "DisableCombatlog"],
    )
    quiet = _entries_by_name(mod2)["QUIET"]
    assert quiet.get("ApplyEffect") == "89f2d0ac-9295-4657-bfa6-fb6d61adf59c"
    assert quiet.get("StatusPropertyFlags") == "DisableOverhead;DisableCombatlog"


def test_custom_status_wires_into_elixir():
    """The fully-original consumable: an elixir applying a status the base
    game has never seen."""
    mod = Mod("BrewMod")
    status = mod.new_status("FORGE_FIRE", boosts=["Ability(Strength,2)"])
    mod.new_elixir("OBJ_Forgefire_Brew", status=status,
                   display_name="Forgefire Brew", treasure="TUT_Chest_Potions")
    entries = _entries_by_name(mod)
    assert entries["FORGE_FIRE"].type == "StatusData"
    _, actions = _template_actions(mod, "OBJ_Forgefire_Brew")
    attrs = actions[0].children[0]
    assert attrs.get("StatsId") == "FORGE_FIRE"      # the custom status
    assert attrs.get("StatusDuration") == "-1"       # until long rest


def test_new_spell_clones_a_base_spell():
    """Custom SpellData, clone-and-tweak: `using` a retail base inherits
    targeting/animation/VFX; overrides carry the damage and identity, with
    resolving ;version handles like passives and statuses."""
    mod = Mod("SpellMod")
    name = mod.new_spell(
        "Projectile_Forge_Bolt",
        using="Projectile_FireBolt",
        display_name="Forge Bolt",
        description="A bolt of molten forge-fire.",
        icon="Spell_Evocation_FireBolt",
        spell_success=["DealDamage(2d10,Fire,Magical)"],
        tooltip_damage=["DealDamage(2d10,Fire)"],
        damage_type="Fire",
    )
    assert name == "Projectile_Forge_Bolt"
    entry = _entries_by_name(mod)["Projectile_Forge_Bolt"]
    assert entry.type == "SpellData"
    assert entry.using == "Projectile_FireBolt"
    assert entry.get("SpellSuccess") == "DealDamage(2d10,Fire,Magical)"
    assert entry.get("TooltipDamageList") == "DealDamage(2d10,Fire)"
    assert entry.get("DamageType") == "Fire"
    assert entry.get("SpellType") is None  # inherited from the base
    display = entry.get("DisplayName")
    assert display.startswith("h") and display.endswith(";1")
    loca = Localization()
    loca.load_bytes(mod.files()["Localization/English/SpellMod.loca"])
    assert loca.resolve(display) == "Forge Bolt"


def test_new_spell_from_scratch_requires_spell_type():
    mod = Mod("SpellMod")
    with pytest.raises(ValueError):
        mod.new_spell("Projectile_Orphan")
    mod.new_spell(
        "Shout_Forge_Cry",
        spell_type="Shout",
        level=1,
        spell_school="Evocation",
        spell_properties=["ApplyStatus(FORGE_FIRE,100,10)"],
        use_costs="ActionPoint:1",
    )
    entry = _entries_by_name(mod)["Shout_Forge_Cry"]
    assert entry.using is None
    assert entry.get("SpellType") == "Shout"
    assert entry.get("Level") == "1"
    assert entry.get("SpellProperties") == "ApplyStatus(FORGE_FIRE,100,10)"
    assert entry.get("UseCosts") == "ActionPoint:1"


def test_scroll_of_a_custom_spell():
    """The fully-original scroll: the cast action's SkillID references a
    SpellData entry this same mod defines."""
    mod = Mod("ForgeSpells")
    spell = mod.new_spell(
        "Projectile_Forge_Bolt",
        using="Projectile_FireBolt",
        spell_success=["DealDamage(2d10,Fire,Magical)"],
    )
    mod.new_scroll("OBJ_Scroll_ForgeBolt", spell=spell,
                   display_name="Scroll of Forge Bolt")
    entries = _entries_by_name(mod)
    assert entries["Projectile_Forge_Bolt"].type == "SpellData"
    _, actions = _template_actions(mod, "OBJ_Scroll_ForgeBolt")
    attrs = actions[0].children[0]
    assert attrs.get("SkillID") == "Projectile_Forge_Bolt"
    assert attrs.get("Conditions") == 'CanUseSpellScroll("Projectile_Forge_Bolt")'


def test_new_spell_item_freecast_recipe():
    """The retail item free-cast pattern (Misty Step amulets/boots): no
    slot in UseCosts, recharge on the spell's Cooldown — the granting item
    needs only the bare UnlockSpell form."""
    mod = Mod("StepMod")
    s = mod.new_spell(
        "Target_Forge_Step",
        using="Target_MistyStep",
        use_costs="BonusActionPoint:1",
        cooldown="OncePerShortRestPerItem",
    )
    entry = _entries_by_name(mod)["Target_Forge_Step"]
    assert entry.get("UseCosts") == "BonusActionPoint:1"
    assert entry.get("Cooldown") == "OncePerShortRestPerItem"
    mod.new_armor("ARM_Step_Amulet", grants_spells=[s])
    amulet = _entries_by_name(mod)["ARM_Step_Amulet"]
    assert amulet.get("Boosts") == "UnlockSpell(Target_Forge_Step)"


def test_new_spell_empty_use_costs_is_an_override():
    """use_costs='' must emit an empty override (retail's
    Target_MistyStep_Free is a fully free cast); None omits the field."""
    mod = Mod("FreeMod")
    mod.new_spell("Target_Free", using="Target_MistyStep", use_costs="")
    assert _entries_by_name(mod)["Target_Free"].get("UseCosts") == ""
    mod.new_spell("Target_Inherit", using="Target_MistyStep")
    assert _entries_by_name(mod)["Target_Inherit"].get("UseCosts") is None


def test_teachable_spell_replaces_wizard_list():
    """Wizard scroll-learning: the ClassDescription's SpellList is the
    transcription pool, so re-shipping that list with a custom spell
    appended makes the spell's scroll teachable."""
    from bg3forge.parsers import WIZARD_LEARNABLE_LIST, parse_spell_lists

    mod = Mod("TeachMod")
    s = mod.new_spell("Target_Forge_Step", using="Target_MistyStep")
    mod.replace_spell_list(
        WIZARD_LEARNABLE_LIST, ["Target_MistyStep", s], name="Wizard spells"
    )
    text = mod.files()["Public/TeachMod/Lists/SpellLists.lsx"].decode("utf-8")
    lists = parse_spell_lists(parse_lsx(text))
    assert len(lists) == 1
    assert lists[0].uuid == WIZARD_LEARNABLE_LIST
    assert lists[0].spell_names == ["Target_MistyStep", "Target_Forge_Step"]
    assert lists[0].display_name == "Wizard spells"


def test_no_spell_list_means_no_lists_file():
    mod = Mod("PlainMod")
    mod.new_item("OBJ_Thing")
    assert not any("Lists/" in name for name in mod.files())


def test_item_grants_a_custom_spell():
    """The other delivery path (retail-verified for base-game spells): an
    equipped item unlocks the custom spell."""
    mod = Mod("ForgeSpells")
    spell = mod.new_spell("Projectile_Forge_Bolt", using="Projectile_FireBolt")
    mod.new_armor("ARM_Caster_Vest", grants_spells=[spell])
    entry = _entries_by_name(mod)["ARM_Caster_Vest"]
    assert entry.get("Boosts") == "UnlockSpell(Projectile_Forge_Bolt)"


def test_effect_description_fills_technical_description_slot():
    """BG3's golden effect blurb is TechnicalDescription (retail: Bloodlust's
    'Drink to enter a bloodlust...'); OnUseDescription is just the use-verb
    label ('Drink'). LSTag hyperlink markup passes through verbatim."""
    mod = Mod("SlotMod")
    mod.new_elixir(
        "OBJ_Slot_Brew",
        status="FORGE_FIRE",
        effect_description=(
            'Drink to ignite <LSTag Type="Status" Tooltip="FORGE_FIRE">'
            "Forgefire</LSTag>: +2 Strength until long rest."
        ),
        on_use_description="Drink",
    )
    node, _ = _template_actions(mod, "OBJ_Slot_Brew")
    tech = node.attributes["TechnicalDescription"]
    verb = node.attributes["OnUseDescription"]
    loca = Localization()
    loca.load_bytes(mod.files()["Localization/English/SlotMod.loca"])
    assert '<LSTag Type="Status" Tooltip="FORGE_FIRE">' in loca.resolve(tech.handle)
    assert loca.resolve(verb.handle) == "Drink"


def test_status_description_params():
    mod = Mod("ParamMod")
    mod.new_status("P", boosts=["AC(1)"], description_params=[5, 10])
    assert _entries_by_name(mod)["P"].get("DescriptionParams") == "5;10"


def test_on_use_description_is_authored_and_resolves():
    """The item-tooltip effect blurb: without it, a cloned consumable shows
    the base's blurb (the healing potion's 'Heals and removes Burning')."""
    mod = Mod("BlurbMod")
    mod.new_elixir(
        "OBJ_Blurb_Brew",
        status="FORGE_FIRE",
        display_name="Blurb Brew",
        on_use_description="Grants Forgefire: +2 Strength and Fire resistance until long rest.",
    )
    node, _ = _template_actions(mod, "OBJ_Blurb_Brew")
    attr = node.attributes["OnUseDescription"]
    assert attr.handle and attr.handle.startswith("h")
    loca = Localization()
    loca.load_bytes(mod.files()["Localization/English/BlurbMod.loca"])
    assert loca.resolve(attr.handle).startswith("Grants Forgefire")


def test_on_use_description_absent_when_unset():
    mod = Mod("NoBlurb")
    mod.new_potion("OBJ_Plain_Brew", status="X")
    node, _ = _template_actions(mod, "OBJ_Plain_Brew")
    assert "OnUseDescription" not in node.attributes  # inherits the base's


def test_place_in_treasure_accumulates_across_items():
    mod = Mod("Multi")
    mod.new_armor("ARM_A", treasure="TUT_Chest_Potions")
    mod.new_item("WPN_B", treasure="TUT_Chest_Potions")
    table = parse_treasure_tables(
        mod.files()["Public/Multi/Stats/Generated/TreasureTable.txt"].decode("utf-8")
    )[0]
    assert sorted(table.items()) == ["ARM_A", "WPN_B"]


def test_scroll_class_id_is_optional():
    """31 retail scrolls omit ClassId entirely (wiring survey), so None
    must leave the attribute out rather than writing a null GUID."""
    from bg3forge.parsers import build_use_spell_action

    action = build_use_spell_action("Projectile_Fireball", class_id=None)
    attrs = action.children[0]
    assert "ClassId" not in attrs.attributes
    assert attrs.get("SkillID") == "Projectile_Fireball"
