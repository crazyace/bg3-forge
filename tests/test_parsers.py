import pytest

from bg3forge.parsers import (
    Localization,
    LocaEntry,
    ModuleInfo,
    StatsCollection,
    StatsDocument,
    StatsEntry,
    StatsParseError,
    build_meta_document,
    build_root_template_node,
    build_templates_document,
    pack_version64,
    parse_loca,
    parse_lsx,
    parse_meta,
    parse_root_templates,
    parse_stats,
    parse_stats_document,
    parse_treasure_tables,
    unpack_version64,
    write_loca,
    write_lsx,
    write_stats,
    write_stats_document,
    RootTemplateIndex,
)
from bg3forge.parsers.progressions import parse_progressions
from bg3forge.parsers.spelllists import parse_spell_lists

from conftest import ROOTTEMPLATE_LSX, TREASURE_TXT, WEAPON_TXT


# -- stats -------------------------------------------------------------------

def test_parse_stats_basics():
    entries = parse_stats(WEAPON_TXT, source="Weapon.txt")
    assert [e.name for e in entries] == ["_BaseWeapon", "WPN_Longsword", "WPN_Longsword_Magic"]
    longsword = entries[1]
    assert longsword.type == "Weapon"
    assert longsword.using == "_BaseWeapon"
    assert longsword.get("Damage Type") == "Slashing"
    assert longsword.source == "Weapon.txt"


def test_stats_comments_and_blank_lines():
    entries = parse_stats('// header\n\nnew entry "A"\ntype "Weapon"\n// trailing\n')
    assert len(entries) == 1


def test_stats_trailing_comment_and_malformed_lines():
    """A trailing // comment outside quotes parses cleanly; a structural
    line that fails to parse raises instead of silently dropping data."""
    from bg3forge.parsers import StatsParseError

    entries = parse_stats(
        'new entry "A"  // introduced in patch 3\n'
        'type "Weapon"\n'
        'data "Damage" "1d8" // base damage\n'
        'data "Notes" "uses // safely inside quotes"\n'
    )
    assert entries[0].data["Damage"] == "1d8"
    assert entries[0].data["Notes"] == "uses // safely inside quotes"

    for bad in (
        'new entry "A"\ndata "Damage" "1d8" trailing-junk\n',
        'new entry "A"\ndata "Damage" "1d8\n',      # missing close quote
        'new entry "A"\ntype "Weapon" 12\n',
        'key "Global","1" extra\n',
    ):
        with pytest.raises(StatsParseError, match="malformed"):
            parse_stats(bad)

    # unmodeled directives are still tolerated, malformed or not
    entries = parse_stats('new itemcolor whatever\nnew entry "B"\ntype "Armor"\n')
    assert entries[0].name == "B"


def test_stats_data_outside_block_raises():
    with pytest.raises(StatsParseError, match="outside any"):
        parse_stats('data "Damage" "1d4"')


def test_write_stats_roundtrips_document():
    """parse -> write -> parse is an identity at the data-model level."""
    document = parse_stats_document(WEAPON_TXT)
    assert parse_stats_document(write_stats_document(document)) == document


def test_write_stats_pins_retail_layout():
    """The canonical fixture round-trips byte-for-byte, pinning the
    `new entry` / `type` / `using` / `data` line shape and blank-line
    separation the game reads back."""
    assert write_stats_document(parse_stats_document(WEAPON_TXT)) == WEAPON_TXT


def test_write_stats_omits_absent_type_and_using():
    text = write_stats([StatsEntry(name="ARM_Plain", type="Armor")])
    assert 'new entry "ARM_Plain"' in text
    assert 'type "Armor"' in text
    assert "using" not in text  # using is None -> no line invented


def test_write_stats_rejects_unrepresentable_strings():
    """The stats grammar has no escape syntax: a double quote or newline
    in any written string would silently reparse as *different* data —
    or inject whole directives.  The writer must refuse, not corrupt."""
    from bg3forge.parsers import StatsWriteError

    # The injection the guard prevents: without it, this value writes a
    # file where "GodMode" is a separate, legitimate-looking data line.
    sneaky = StatsEntry(
        name="WPN_Fine", data={"Notes": 'x"\ndata "GodMode" "1'}
    )
    with pytest.raises(StatsWriteError, match="Notes"):
        write_stats([sneaky])

    cases = [
        StatsEntry(name='A" "B'),                              # quote in name
        StatsEntry(name="A", type='Weapon"'),                  # quote in type
        StatsEntry(name="A", using='Base\n'),                  # newline in using
        StatsEntry(name="A", data={'K" "': "v"}),              # quote in key
        StatsEntry(name="A", data={"K": 'v" "w'}),             # quote in value
    ]
    for entry in cases:
        with pytest.raises(StatsWriteError):
            write_stats([entry])

    with pytest.raises(StatsWriteError, match="global"):
        write_stats([], globals={'Prof"Base': "2"})
    with pytest.raises(StatsWriteError, match="global"):
        write_stats([], globals={"ProfBase": "2\n3"})

    # StatsWriteError participates in the ValueError contract like every
    # other error in the pipeline.
    assert issubclass(StatsWriteError, ValueError)


def test_write_stats_emits_key_globals():
    """Globals serialize as consecutive `key "Name","Value"` lines and
    survive a round trip (the Data.txt / XPData.txt shape)."""
    document = StatsDocument(
        entries=[StatsEntry(name="A", type="Weapon")],
        globals={"ProficiencyBonusBase": "2"},
    )
    text = write_stats_document(document)
    assert 'key "ProficiencyBonusBase","2"' in text
    assert parse_stats_document(text) == document


def test_write_stats_authors_a_new_entry_from_scratch():
    """The mod-authoring path: build an entry in memory, serialize it, and
    confirm the game-readable text parses back to the same definition."""
    entry = StatsEntry(
        name="ARM_Sunforged_Plate",
        type="Armor",
        using="ARM_Plate_Body",
        data={"ArmorClass": "21", "RootTemplate": "abc"},
    )
    reparsed = parse_stats(write_stats([entry]))
    assert len(reparsed) == 1
    assert reparsed[0].using == "ARM_Plate_Body"
    assert reparsed[0].get("ArmorClass") == "21"


def test_stats_key_globals():
    """Retail Data.txt style: top-level `key "Name","Value"` constants
    (the exact shape that crashed on Public/PhotoMode/.../Data.txt)."""
    from bg3forge.parsers import parse_stats_document

    document = parse_stats_document(
        'key "ProficiencyBonusBase","2"\n'
        'key "FleeDistance" "13.0"\n'          # space-separated variant
        'new entry "A"\ntype "Weapon"\n'
    )
    assert document.globals == {"ProficiencyBonusBase": "2", "FleeDistance": "13.0"}
    assert [e.name for e in document.entries] == ["A"]
    # parse_stats stays entry-only and, crucially, no longer raises
    assert [e.name for e in parse_stats('key "X","1"')] == []


def test_stats_globals_merge_in_collection():
    stats = StatsCollection()
    stats.load_text('key "A","1"')
    stats.load_text('key "B","2"\nkey "A","3"')
    assert stats.globals == {"A": "3", "B": "2"}


def test_stats_unmodeled_blocks_are_skipped():
    """`new itemcolor` and friends parse harmlessly instead of raising."""
    entries = parse_stats(
        'new itemcolor "Red"\n'
        'data "Color" "ff0000"\n'
        'new entry "Real"\n'
        'type "Weapon"\n'
        'data "Damage" "1d6"\n'
    )
    assert [e.name for e in entries] == ["Real"]
    assert entries[0].data == {"Damage": "1d6"}


def test_stats_inheritance():
    stats = StatsCollection(parse_stats(WEAPON_TXT))
    resolved = stats.resolved("WPN_Longsword_Magic")
    assert resolved["Damage"] == "1d8"           # from WPN_Longsword
    assert resolved["Weight"] == "1.0"           # from _BaseWeapon
    assert resolved["Rarity"] == "Rare"          # overridden locally
    assert resolved["ValueOverride"] == "500"


def test_stats_inheritance_cycle_detected():
    stats = StatsCollection()
    stats.load_text('new entry "A"\ntype "Weapon"\nusing "B"\nnew entry "B"\ntype "Weapon"\nusing "A"')
    with pytest.raises(StatsParseError, match="cycle"):
        stats.resolved("A")


def test_stats_self_using_layers():
    """Retail patch layering: a later definition `using` its own name
    extends the earlier definition (the MAG_Frost_..._Gloves pattern)."""
    stats = StatsCollection()
    stats.load_text(
        'new entry "MAG_Gloves"\ntype "Armor"\nusing "_Base"\ndata "A" "1"\n'
        'new entry "_Base"\ntype "Armor"\ndata "Base" "yes"'
    )
    stats.load_text(  # patch file loaded later, extending the original
        'new entry "MAG_Gloves"\ntype "Armor"\nusing "MAG_Gloves"\ndata "B" "2"'
    )
    resolved = stats.resolved("MAG_Gloves")
    assert resolved == {"Base": "yes", "A": "1", "B": "2"}

    # a third layer stacks again
    stats.load_text('new entry "MAG_Gloves"\ntype "Armor"\nusing "MAG_Gloves"\ndata "C" "3"')
    assert stats.resolved("MAG_Gloves") == {"Base": "yes", "A": "1", "B": "2", "C": "3"}


def test_stats_self_using_without_earlier_layer():
    """A lone self-reference is a dangling using, not an infinite loop."""
    stats = StatsCollection()
    stats.load_text('new entry "X"\ntype "Armor"\nusing "X"\ndata "K" "V"')
    assert stats.resolved("X") == {"K": "V"}


def test_stats_later_definition_wins():
    stats = StatsCollection()
    stats.load_text('new entry "A"\ntype "Weapon"\ndata "K" "old"')
    stats.load_text('new entry "A"\ntype "Weapon"\ndata "K" "new"')
    assert stats.resolved("A")["K"] == "new"
    assert len(stats) == 1


def test_stats_by_type():
    stats = StatsCollection(parse_stats(WEAPON_TXT))
    assert len(stats.by_type("Weapon")) == 3
    assert stats.by_type("SpellData") == []


# -- loca --------------------------------------------------------------------

def test_loca_roundtrip():
    entries = [
        LocaEntry("h0aa", 1, "Hello"),
        LocaEntry("h0bb", 3, "Wörld ünïcode ✓"),
    ]
    blob = write_loca(entries)
    parsed = parse_loca(blob)
    assert [(e.key, e.version, e.text) for e in parsed] == [
        ("h0aa", 1, "Hello"),
        ("h0bb", 3, "Wörld ünïcode ✓"),
    ]


def test_tag_registry_uuid_case_insensitive():
    from bg3forge.parsers.tags import Tag, TagRegistry

    registry = TagRegistry()
    registry.add(Tag(uuid="AAAA1111-0000-0000-0000-000000000001", name="PALADIN"))
    assert "aaaa1111-0000-0000-0000-000000000001" in registry
    assert registry["aaaa1111-0000-0000-0000-000000000001"].name == "PALADIN"
    assert registry.get("AAAA1111-0000-0000-0000-000000000001").name == "PALADIN"
    # names remain case-sensitive: they are canonical engine identifiers
    assert registry.get("PALADIN") is not None
    assert registry.get("paladin") is None


def test_localization_merge_missing():
    from bg3forge.parsers.localization import Localization, LocaEntry, write_loca

    primary = Localization()
    primary.load_bytes(write_loca([LocaEntry("h0aaa", 2, "übersetzt")]))
    fallback = Localization()
    fallback.load_bytes(
        write_loca([LocaEntry("h0aaa", 9, "translated"), LocaEntry("h0bbb", 1, "extra")])
    )
    primary.merge_missing(fallback)
    assert primary.resolve("h0aaa") == "übersetzt"  # existing entries win
    assert primary.resolve("h0bbb") == "extra"      # missing filled in


def test_golden_loca_bytes():
    """Pin the .loca layout against drift: exact writer output for a
    known input, and the parse of those bytes back."""
    from bg3forge.parsers.localization import LocaEntry, parse_loca, write_loca

    blob = write_loca([LocaEntry("h0abc;2", 2, "Hi")])
    assert blob.hex() == (
        "4c4f4341"      # LOCA
        "01000000"      # num_entries
        "52000000"      # texts_offset: 12 + 70 = 82
        + "68306162633b32".ljust(128, "0")  # "h0abc;2" in 64 NUL-padded bytes
        + "0200"        # version u16
        + "03000000"    # length u32 ("Hi\0")
        + "486900"      # text block
    )
    [entry] = parse_loca(blob)
    assert (entry.key, entry.version, entry.text) == ("h0abc;2", 2, "Hi")


def test_loca_truncated_entry_table():
    """num_entries is an untrusted u32: a table that doesn't fit the data
    must raise LocaError up front, not struct.error mid-loop."""
    from bg3forge.parsers import LocaError

    header = b"LOCA" + (1000).to_bytes(4, "little") + (12).to_bytes(4, "little")
    with pytest.raises(LocaError, match="truncated entry table"):
        parse_loca(header)


def test_loca_bad_signature():
    from bg3forge.parsers import LocaError

    with pytest.raises(LocaError, match="signature"):
        parse_loca(b"XXXX" + b"\x00" * 20)


def test_localization_versioning_and_handles():
    loca = Localization()
    loca.load_bytes(write_loca([LocaEntry("h0key", 1, "old"), LocaEntry("h0key", 2, "new")]))
    assert loca.resolve("h0key") == "new"
    assert loca.resolve("h0key;5") == "new"      # version suffix stripped
    assert loca.resolve("h0missing", "fallback") == "fallback"
    assert loca.resolve(None) == ""
    assert "h0key;9" in loca


# -- lsx / root templates ----------------------------------------------------

def test_parse_lsx_regions_and_attributes():
    doc = parse_lsx(ROOTTEMPLATE_LSX)
    templates_region = doc.region("Templates")
    assert templates_region is not None
    objects = list(doc.find_all("GameObjects"))
    assert len(objects) == 3
    sword = objects[2]
    assert sword.get("Name") == "WPN_Longsword"
    # TranslatedString attributes expose their handle as text
    assert sword.get("DisplayName") == "h55555555-5555-5555-5555-555555555555"


def test_parse_lsx_rejects_garbage():
    from bg3forge.parsers import LsxError

    with pytest.raises(LsxError):
        parse_lsx("<not-lsx/>")
    with pytest.raises(LsxError):
        parse_lsx("definitely not xml <")


_CONTAINER_LSX = """\
<?xml version="1.0" encoding="utf-8"?>
<save>
  <version major="4" minor="0" revision="9" build="330" />
  <region id="Templates">
    <node id="Templates">
      <children>
        <node id="GameObjects">
          <attribute id="MapKey" type="FixedString" value="e57e3af6-ae79-4d5c-9d11-f695b359c740" />
          <attribute id="Name" type="LSString" value="S_Chest_Potions" />
          <attribute id="TemplateName" type="FixedString" value="813c005f-72ab-4806-ad7e-2e3135e41d27" />
          <children>
            <node id="InventoryList">
              <children>
                <node id="InventoryItem">
                  <attribute id="Object" type="LSString" value="TUT_Chest_Potions" />
                </node>
              </children>
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""


def test_root_template_parses_inventory_treasure_link():
    template = parse_root_templates(parse_lsx(_CONTAINER_LSX))[0]
    assert template.name == "S_Chest_Potions"
    assert template.inventory == ["TUT_Chest_Potions"]
    # a treasure-table name is not a UUID, so it surfaces as a treasure table
    assert template.treasure_tables == ["TUT_Chest_Potions"]


def test_by_treasure_table_finds_the_container():
    index = RootTemplateIndex()
    index.add_document(parse_lsx(_CONTAINER_LSX))
    matches = index.by_treasure_table("TUT_Chest_Potions")
    assert len(matches) == 1
    # the placed object's MapKey is the UUID you'd spawn
    assert matches[0].map_key == "e57e3af6-ae79-4d5c-9d11-f695b359c740"
    assert index.by_treasure_table("NOPE") == []


def test_direct_object_inventory_is_not_a_treasure_table():
    """An InventoryItem Object that is a UUID is a direct item, not a table."""
    lsx = _CONTAINER_LSX.replace(
        "TUT_Chest_Potions", "1111aaaa-0000-0000-0000-000000000001"
    )
    template = parse_root_templates(parse_lsx(lsx))[0]
    assert template.inventory == ["1111aaaa-0000-0000-0000-000000000001"]
    assert template.treasure_tables == []  # UUID filtered out


def test_root_template_inheritance():
    index = RootTemplateIndex()
    index.add_document(parse_lsx(ROOTTEMPLATE_LSX))
    assert len(index) == 3
    resolved = index.resolved("1111aaaa-0000-0000-0000-000000000001")
    assert resolved["Icon"] == "Item_Generic"    # inherited from parent
    assert resolved["Name"] == "WPN_Longsword"   # own value wins
    assert parse_root_templates(parse_lsx(ROOTTEMPLATE_LSX))[0].map_key.startswith("0000base")


# -- meta.lsx / Version64 ----------------------------------------------------

def test_version64_packs_and_unpacks():
    # The retail reference version round-trips through both directions.
    retail = (4, 8, 700, 7143220)
    packed = pack_version64(*retail)
    assert unpack_version64(packed) == retail
    # pack is the exact inverse of unpack for an arbitrary in-range integer.
    value = 0x0420_0000_1234_5678
    assert pack_version64(*unpack_version64(value)) == value


def test_version64_rejects_out_of_range_field():
    with pytest.raises(ValueError, match="minor"):
        pack_version64(1, 256, 0, 0)  # minor is 8 bits


def test_build_meta_document_roundtrips():
    module = ModuleInfo(
        name="SunforgedArmors",
        uuid="11112222-3333-4444-5555-666677778888",
        author="Author",
        description="A test mod.",
        version=(1, 2, 3, 4),
    )
    text = write_lsx(build_meta_document(module))
    assert parse_meta(parse_lsx(text)) == module


def test_build_meta_defaults_folder_to_name_and_emits_required_fields():
    module = ModuleInfo(name="MyMod", uuid="abc")
    assert module.folder == "MyMod"  # normalized in __post_init__
    info = next(build_meta_document(module).find_all("ModuleInfo"))
    for required in ("Folder", "Name", "UUID", "Version64", "Type"):
        assert required in info.attributes
    assert info.get("Type") == "Add-on"
    assert info.get("Folder") == "MyMod"


# -- root template builder ---------------------------------------------------

def test_build_root_template_roundtrips_through_parser():
    node = build_root_template_node(
        "abcd1234-0000-0000-0000-000000000001",
        "ARM_Sunforged_Plate",
        stats="ARM_Sunforged_Plate",
        icon="Item_ARM_Sunforged",
        display_name="h11110000-0000-0000-0000-000000000001",
        description="h22220000-0000-0000-0000-000000000002",
        parent_template_id="0000base-0000-0000-0000-00000000000f",
        tags=["bbbb2222-0000-0000-0000-000000000002"],
    )
    templates = parse_root_templates(build_templates_document([node]))
    assert len(templates) == 1
    template = templates[0]
    assert template.map_key == "abcd1234-0000-0000-0000-000000000001"
    assert template.name == "ARM_Sunforged_Plate"
    assert template.stats_name == "ARM_Sunforged_Plate"
    assert template.icon == "Item_ARM_Sunforged"
    assert template.parent_id == "0000base-0000-0000-0000-00000000000f"
    # DisplayName is serialized as a TranslatedString handle and read back as one
    assert template.display_name_handle == "h11110000-0000-0000-0000-000000000001"
    assert template.tags == ["bbbb2222-0000-0000-0000-000000000002"]
    assert template.fields["Type"] == "item"


def test_built_template_inherits_visuals_from_base():
    """A built item pointing at a base template resolves the base's fields
    (Icon here stands in for the reused visuals/mesh references)."""
    base = build_root_template_node(
        "0000base-0000-0000-0000-00000000000f",
        "BASE_Plate",
        icon="Item_Plate_Shared",
    )
    item = build_root_template_node(
        "abcd1234-0000-0000-0000-000000000001",
        "ARM_Sunforged_Plate",
        stats="ARM_Sunforged_Plate",
        parent_template_id="0000base-0000-0000-0000-00000000000f",
    )
    index = RootTemplateIndex()
    index.add_document(build_templates_document([base, item]))
    resolved = index.resolved("abcd1234-0000-0000-0000-000000000001")
    assert resolved["Icon"] == "Item_Plate_Shared"       # inherited from base
    assert resolved["Stats"] == "ARM_Sunforged_Plate"    # own value
    assert index.by_stats("ARM_Sunforged_Plate")[0].map_key.startswith("abcd1234")


def test_build_templates_document_uses_templates_region():
    node = build_root_template_node("uuid", "X")
    text = write_lsx(build_templates_document([node]))
    assert '<region id="Templates">' in text
    assert '<node id="GameObjects">' in text


# -- treasure ----------------------------------------------------------------

def test_write_treasure_tables_roundtrips():
    from bg3forge.parsers import write_treasure_tables

    tables = parse_treasure_tables(TREASURE_TXT)
    assert parse_treasure_tables(write_treasure_tables(tables)) == tables


def test_write_treasure_tables_injects_with_canmerge():
    from bg3forge.parsers import (
        TreasureObject,
        TreasureSubtable,
        TreasureTable,
        write_treasure_tables,
    )

    table = TreasureTable(
        name="TUT_Chest_Potions",
        can_merge=True,
        subtables=[TreasureSubtable("-1", [TreasureObject("I_ARM_Test", 1)])],
    )
    text = write_treasure_tables([table])
    assert 'new treasuretable "TUT_Chest_Potions"' in text
    assert "CanMerge 1" in text
    assert 'object category "I_ARM_Test",1,0,0,0,0,0,0,0' in text


def test_parse_treasure_tables():
    tables = parse_treasure_tables(TREASURE_TXT)
    assert len(tables) == 1
    table = tables[0]
    assert table.name == "TUT_Chest"
    assert table.can_merge
    assert len(table.subtables) == 1
    assert table.items() == ["WPN_Longsword"]
    frequencies = [o.frequency for o in table.subtables[0].objects]
    assert frequencies == [1, 3]


# -- progressions ------------------------------------------------------------

PROGRESSION_LSX = """\
<save>
  <region id="Progressions">
    <node id="root">
      <children>
        <node id="Progression">
          <attribute id="UUID" type="guid" value="aaaaaaaa-0000-0000-0000-000000000001" />
          <attribute id="Name" type="LSString" value="Barbarian" />
          <attribute id="TableUUID" type="guid" value="bbbbbbbb-0000-0000-0000-000000000001" />
          <attribute id="Level" type="uint8" value="1" />
          <attribute id="ProgressionType" type="uint8" value="0" />
          <attribute id="PassivesAdded" type="LSString" value="Rage;UnarmoredDefense" />
          <attribute id="PassivesRemoved" type="LSString" value="OldRage" />
          <attribute id="Boosts" type="LSString" value="ActionResource(Rage,2);Proficiency(MartialWeapons)" />
          <attribute id="Selectors" type="LSString" value="AddSpells(cccccccc-0000-0000-0000-000000000001);SelectSpells(cccccccc-0000-0000-0000-000000000002,1,0)" />
          <children>
            <node id="SubClasses">
              <children>
                <node id="SubClass">
                  <attribute id="Object" type="guid" value="dddddddd-0000-0000-0000-000000000001" />
                </node>
              </children>
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""


def test_parse_progressions():
    progressions = parse_progressions(parse_lsx(PROGRESSION_LSX))
    assert len(progressions) == 1
    p = progressions[0]
    assert p.name == "Barbarian"
    assert p.level == 1
    assert p.passives_added == ["Rage", "UnarmoredDefense"]
    assert p.passives_removed == ["OldRage"]
    assert p.boosts == ["ActionResource(Rage,2)", "Proficiency(MartialWeapons)"]
    assert p.added_spell_list_ids == [
        "cccccccc-0000-0000-0000-000000000001"
    ]
    assert p.selectable_spell_list_ids == [
        "cccccccc-0000-0000-0000-000000000002"
    ]
    assert p.subclass_ids == ["dddddddd-0000-0000-0000-000000000001"]


SPELL_LIST_LSX = """\
<save>
  <region id="SpellLists">
    <node id="root">
      <children>
        <node id="SpellList">
          <attribute id="UUID" type="guid" value="cccccccc-0000-0000-0000-000000000001" />
          <attribute id="Comment" type="LSString" value="Barbarian rituals" />
          <attribute id="Spells" type="LSString" value="Shout_Rage;Target_Jump" />
        </node>
      </children>
    </node>
  </region>
</save>
"""


def test_parse_spell_lists():
    spell_lists = parse_spell_lists(parse_lsx(SPELL_LIST_LSX), source="lists.lsx")
    assert len(spell_lists) == 1
    spell_list = spell_lists[0]
    assert spell_list.uuid == "cccccccc-0000-0000-0000-000000000001"
    assert spell_list.comment == "Barbarian rituals"
    assert spell_list.spell_names == ["Shout_Rage", "Target_Jump"]
    assert spell_list.source == "lists.lsx"


def test_spell_list_builder_round_trips():
    """The writer emits the retail shape (Name FixedString, Spells LSString,
    UUID guid in a SpellLists/root region) and re-parses to the same list."""
    from bg3forge.parsers import (
        build_spell_list_node,
        build_spell_lists_document,
        write_lsx,
    )

    node = build_spell_list_node(
        "cccccccc-0000-0000-0000-000000000002",
        ["Target_MistyStep", "Target_Forge_Step"],
        name="Wizard spells",
    )
    assert node.attributes["UUID"].type == "guid"
    assert node.attributes["Spells"].type == "LSString"
    assert node.attributes["Name"].type == "FixedString"
    parsed = parse_spell_lists(parse_lsx(write_lsx(build_spell_lists_document([node]))))
    assert len(parsed) == 1
    assert parsed[0].uuid == "cccccccc-0000-0000-0000-000000000002"
    assert parsed[0].spell_names == ["Target_MistyStep", "Target_Forge_Step"]
    assert parsed[0].display_name == "Wizard spells"
