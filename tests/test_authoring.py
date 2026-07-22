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


def test_place_in_treasure_accumulates_across_items():
    mod = Mod("Multi")
    mod.new_armor("ARM_A", treasure="TUT_Chest_Potions")
    mod.new_item("WPN_B", treasure="TUT_Chest_Potions")
    table = parse_treasure_tables(
        mod.files()["Public/Multi/Stats/Generated/TreasureTable.txt"].decode("utf-8")
    )[0]
    assert sorted(table.items()) == ["ARM_A", "WPN_B"]
