from bg3forge import Mod
from bg3forge.pak.reader import PakReader
from bg3forge.parsers import (
    Localization,
    parse_lsx,
    parse_meta,
    parse_root_templates,
    parse_stats,
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
        template_path = "Public/SunforgedArmors/RootTemplates/SunforgedArmors.lsx"
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
        template = parse_root_templates(parse_lsx(reader.read(template_path).decode("utf-8")))[0]
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
