import pytest

from bg3forge.parsers import (
    Localization,
    LocaEntry,
    StatsCollection,
    StatsParseError,
    parse_loca,
    parse_lsx,
    parse_root_templates,
    parse_stats,
    parse_treasure_tables,
    write_loca,
    RootTemplateIndex,
)
from bg3forge.parsers.progressions import parse_progressions

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


def test_stats_data_outside_block_raises():
    with pytest.raises(StatsParseError, match="outside any"):
        parse_stats('data "Damage" "1d4"')


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
    assert len(objects) == 2
    sword = objects[1]
    assert sword.get("Name") == "WPN_Longsword"
    # TranslatedString attributes expose their handle as text
    assert sword.get("DisplayName") == "h55555555-5555-5555-5555-555555555555"


def test_parse_lsx_rejects_garbage():
    from bg3forge.parsers import LsxError

    with pytest.raises(LsxError):
        parse_lsx("<not-lsx/>")
    with pytest.raises(LsxError):
        parse_lsx("definitely not xml <")


def test_root_template_inheritance():
    index = RootTemplateIndex()
    index.add_document(parse_lsx(ROOTTEMPLATE_LSX))
    assert len(index) == 2
    resolved = index.resolved("1111aaaa-0000-0000-0000-000000000001")
    assert resolved["Icon"] == "Item_Generic"    # inherited from parent
    assert resolved["Name"] == "WPN_Longsword"   # own value wins
    assert parse_root_templates(parse_lsx(ROOTTEMPLATE_LSX))[0].map_key.startswith("0000base")


# -- treasure ----------------------------------------------------------------

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
          <attribute id="UUID" type="guid" value="aaaa-bbbb" />
          <attribute id="Name" type="LSString" value="Barbarian" />
          <attribute id="TableUUID" type="guid" value="cccc-dddd" />
          <attribute id="Level" type="uint8" value="1" />
          <attribute id="ProgressionType" type="uint8" value="0" />
          <attribute id="PassivesAdded" type="LSString" value="Rage;UnarmoredDefense" />
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
