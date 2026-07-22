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
    action = actions[0]
    assert action.get("ActionType") == "12"
    attrs = action.children[0]
    assert attrs.get("SkillID") == "Projectile_Fireball"
    assert attrs.get("Conditions") == 'CanUseSpellScroll("Projectile_Fireball")'
    assert attrs.get("ClassId") == SCROLL_CLASS_ID
    assert attrs.attributes["ClassId"].type == "guid"
    # obtainable like any other item
    table = parse_treasure_tables(
        mod.files()[f"Public/ScrollMod/Stats/Generated/TreasureTable.txt"].decode("utf-8")
    )[0]
    assert table.items() == ["OBJ_Scroll_MyFireball"]


def test_place_in_treasure_accumulates_across_items():
    mod = Mod("Multi")
    mod.new_armor("ARM_A", treasure="TUT_Chest_Potions")
    mod.new_item("WPN_B", treasure="TUT_Chest_Potions")
    table = parse_treasure_tables(
        mod.files()["Public/Multi/Stats/Generated/TreasureTable.txt"].decode("utf-8")
    )[0]
    assert sorted(table.items()) == ["ARM_A", "WPN_B"]
