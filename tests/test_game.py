import pytest

from bg3forge import Game, GameNotFoundError
from bg3forge.pak.extractor import Extractor


@pytest.fixture
def game(data_dir):
    return Game(data_dir=data_dir)


def test_game_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("BG3_PATH", raising=False)
    with pytest.raises(GameNotFoundError):
        Game(path=tmp_path)  # empty dir: no Data/*.pak


def test_stats_loaded_from_pak(game):
    assert "WPN_Longsword" in game.stats
    assert "Projectile_Fireball" in game.stats
    assert game.stats["BURNING"].type == "StatusData"
    assert game.stats.globals["ProficiencyBonusBase"] == "2"  # from Data.txt
    assert game.load_issues == []


def test_bad_file_is_recorded_not_fatal(tmp_path):
    """A malformed stats file must never abort the whole load (regression
    for the retail PhotoMode/Data.txt crash)."""
    from bg3forge.pak import PakWriter
    from conftest import fixture_files

    writer = PakWriter()
    for name, data in fixture_files().items():
        writer.add(name, data)
    writer.add(
        "Public/Broken/Stats/Generated/Data/Broken.txt",
        b'data "Orphan" "1"\n',  # structural line outside any block
    )
    writer.write(tmp_path / "Shared.pak")

    game = Game(data_dir=tmp_path)
    assert len(game.items) == 3            # everything else still loads
    assert len(game.load_issues) == 1
    issue = game.load_issues[0]
    assert issue.file == "Public/Broken/Stats/Generated/Data/Broken.txt"
    assert "outside any" in issue.error


def test_localization_loaded(game):
    assert game.localization.resolve("h11111111-1111-1111-1111-111111111111;1") == "Fireball"


def test_items_join_templates_and_localization(game):
    items = {item.name: item for item in game.items}
    assert set(items) == {"_BaseWeapon", "WPN_Longsword", "WPN_Longsword_Magic"}
    sword = items["WPN_Longsword"]
    assert sword.display_name == "Longsword"          # via root template + loca
    assert sword.description == "A trusty longsword."
    assert sword.icon == "Item_WPN_Longsword"
    assert sword.weight == 1.0
    magic = items["WPN_Longsword_Magic"]
    assert magic.rarity == "Rare"
    assert magic.value == 500
    assert magic.display_name == "Longsword"          # inherited RootTemplate


def test_item_templates_include_global_items_and_resolve_template_name(game):
    placed_id = "3333cccc-0000-0000-0000-000000000003"
    assert placed_id not in game.templates
    assert placed_id in game.item_templates
    placed = game.item_templates.get(placed_id)
    assert placed is not None
    assert placed.template_name == "1111aaaa-0000-0000-0000-000000000001"
    assert game.item_templates.resolved(placed_id) == {
        "Name": "S_WLD_PlacedLongsword",
        "Icon": "Item_Generic",
        "DisplayName": "h55555555-5555-5555-5555-555555555555",
        "Description": "h66666666-6666-6666-6666-666666666666",
        "Stats": "WPN_Longsword",
        "ParentTemplateId": "0000base-0000-0000-0000-00000000000f",
        "TemplateName": "1111aaaa-0000-0000-0000-000000000001",
        "LevelName": "WLD_Main_A",
        "Type": "item",
    }

    level_id = "4444dddd-0000-0000-0000-000000000004"
    assert level_id not in game.templates
    assert level_id in game.item_templates
    assert game.item_templates.resolved(level_id)["Stats"] == "WPN_Longsword"
    assert game.item_templates.resolved(level_id)["DisplayName"] == (
        "h11111111-1111-1111-1111-111111111111"
    )


def test_spells(game):
    spells = game.spells
    assert len(spells) == 2
    fireball = spells[0]
    assert fireball.display_name == "Fireball"
    assert fireball.level == 3
    assert fireball.school == "Evocation"
    assert fireball.damage == "8d6"
    assert fireball.spell_type == "Projectile"


def test_passives_and_statuses(game):
    assert game.passives[0].display_name == "Savage Attacks"
    assert game.passives[0].boosts == "RerollDamageDice()"
    assert game.statuses[0].name == "BURNING"
    assert game.statuses[0].status_type == "BOOST"


def test_named_lookup(game):
    sword = game.items["WPN_Longsword"]
    assert sword.display_name == "Longsword"
    assert "WPN_Longsword" in game.items
    assert "WPN_Missing" not in game.items
    assert game.items.get("WPN_Missing") is None
    with pytest.raises(KeyError, match="WPN_Missing"):
        game.items["WPN_Missing"]
    # integer indexing and iteration still behave like a list
    assert game.items[0] in list(game.items)


def test_find_by_display_name(game):
    hits = game.items.find("longsword")
    assert {item.name for item in hits} >= {"WPN_Longsword", "WPN_Longsword_Magic"}
    assert game.spells.find("fireball")[0].name == "Projectile_Fireball"


def test_cross_source_resolution(game):
    """weapon.passives / .statuses / .spells resolve across data sources."""
    magic = game.items["WPN_Longsword_Magic"]
    assert magic.passive_names == ["SavageAttacks"]
    assert [p.display_name for p in magic.passives] == ["Savage Attacks"]
    assert [s.name for s in magic.statuses] == ["BURNING"]
    assert magic.spell_names == ["Projectile_Fireball"]
    assert [s.display_name for s in magic.spells] == ["Fireball"]
    assert "WeaponEnchantment(1)" in magic.boosts
    # the plain longsword grants nothing
    assert game.items["WPN_Longsword"].passives == []


def test_reverse_links(game):
    """passive.items / status.items / spell.items walk the graph backwards."""
    assert [i.name for i in game.passives["SavageAttacks"].items] == ["WPN_Longsword_Magic"]
    assert [i.name for i in game.statuses["BURNING"].items] == ["WPN_Longsword_Magic"]
    assert [i.name for i in game.spells["Projectile_Fireball"].items] == ["WPN_Longsword_Magic"]
    # forward and reverse edges agree on identity
    magic = game.items["WPN_Longsword_Magic"]
    assert magic.passives[0].items[0] is magic


def test_progression_graph(game):
    table_uuid = "bbbbbbbb-0000-0000-0000-000000000001"
    records = game.progressions.by_table(table_uuid)
    assert [record.level for record in records] == [1, 2]
    assert game.progressions.at_level(1, table_uuid) == [records[0]]
    assert game.progressions[records[0].uuid] is records[0]
    assert records[0].subclass_ids == [
        "dddddddd-0000-0000-0000-000000000001"
    ]

    level_one = records[0]
    assert [passive.name for passive in level_one.passives] == ["SavageAttacks"]
    assert [spell.name for spell in level_one.spells] == ["Projectile_Fireball"]
    assert [spell.name for spell in level_one.selectable_spells] == [
        "Projectile_Fireball",
        "Projectile_FireBolt",
    ]
    assert [passive.name for passive in records[1].removed_passives] == [
        "SavageAttacks"
    ]

    passive = game.passives["SavageAttacks"]
    fireball = game.spells["Projectile_Fireball"]
    assert passive.progressions == [level_one]
    assert fireball.progressions == [level_one]
    assert fireball.progression_choices == [level_one]


def test_class_descriptions_join_the_spell_machinery(game):
    """game.classes ties a class to its learnable spell list, progression
    table, and subclasses — the joins behind wizard transcription and
    class-spell authoring."""
    wizard = game.classes["Wizard"]
    assert wizard.display_name == "Wizard"
    assert wizard.can_learn_spells is True
    assert wizard.must_prepare_spells is True
    assert wizard.base_hp == 6 and wizard.hp_per_level == 4
    assert wizard.spell_list.uuid == "cccccccc-0000-0000-0000-000000000001"
    assert [s.name for s in wizard.spell_list.spells] == ["Projectile_Fireball"]
    assert [p.level for p in wizard.progressions] == [1, 2]

    evocation = game.classes["EvocationSchool"]
    assert evocation.parent is wizard
    assert wizard.subclasses == [evocation]
    assert evocation.spell_list is None

    # The class-spell authoring query: every list carrying a sibling spell.
    lists = game.spell_lists_containing("Projectile_Fireball")
    assert {l.uuid for l in lists} == {
        "cccccccc-0000-0000-0000-000000000001",
        "cccccccc-0000-0000-0000-000000000002",
    }
    assert game.spell_lists_containing("Target_Nonexistent") == []


def test_add_class_spell_extends_matching_lists(game):
    """add_class_spell bridges read and write: it extends the class's
    selectable lists and ClassDescription pool that already hold spells of
    the given level, and skips wrong-level lists."""
    from bg3forge import Mod, add_class_spell
    from bg3forge.parsers import parse_lsx, parse_spell_lists

    mod = Mod("ClassSpellMod")
    # Fixture Fireball is level 3: both wizard lists carry it.
    extended = add_class_spell(game, mod, "Wizard", "Projectile_MyBolt", level=3)
    assert set(extended) == {
        "cccccccc-0000-0000-0000-000000000002",  # SelectSpells list
        "cccccccc-0000-0000-0000-000000000001",  # ClassDescription pool
    }
    text = mod.files()["Public/ClassSpellMod/Lists/SpellLists.lsx"].decode("utf-8")
    lists = {l.uuid: l for l in parse_spell_lists(parse_lsx(text))}
    for uuid in extended:
        assert lists[uuid].spell_names == ["Projectile_Fireball", "Projectile_MyBolt"]

    # No level-2 spells anywhere in the fixture: nothing to extend.
    mod2 = Mod("ClassSpellMod2")
    assert add_class_spell(game, mod2, "Wizard", "Target_MyStep", level=2) == []
    assert not any("Lists/" in name for name in mod2.files())

    # Idempotent: a spell already on the lists is not re-added.
    mod3 = Mod("ClassSpellMod3")
    assert add_class_spell(game, mod3, "Wizard", "Projectile_Fireball", level=3) == []


def test_add_class_spell_level_zero_targets_cantrip_lists(game):
    """The level guard is symmetric: level=0 extends exactly the cantrip
    lists and leaves leveled lists alone."""
    from bg3forge import Mod, add_class_spell
    from bg3forge.parsers import parse_lsx, parse_spell_lists

    mod = Mod("CantripMod")
    extended = add_class_spell(game, mod, "Wizard", "Projectile_MyZap", level=0)
    assert extended == ["cccccccc-0000-0000-0000-000000000003"]  # cantrips only
    text = mod.files()["Public/CantripMod/Lists/SpellLists.lsx"].decode("utf-8")
    (cantrips,) = parse_spell_lists(parse_lsx(text))
    assert cantrips.spell_names == ["Projectile_FireBolt", "Projectile_MyZap"]
    assert cantrips.display_name == "Wizard cantrips"


def test_progression_uuid_follows_pak_load_order(data_dir):
    from conftest import PROGRESSION_LSX
    from bg3forge.pak import PakWriter

    patched = PROGRESSION_LSX.replace(
        'value="Wizard"', 'value="PatchedWizard"', 1
    )
    writer = PakWriter(priority=10)
    writer.add("Public/Patch/Progressions/Progressions.lsx", patched.encode())
    writer.write(data_dir / "Patch.pak")

    game = Game(data_dir=data_dir)
    record = game.progressions["aaaaaaaa-0000-0000-0000-000000000001"]
    assert record.name == "PatchedWizard"


def test_owner_templates_and_requirements(game):
    sword = game.items["WPN_Longsword"]
    assert sword.requirements == ["Str 13"]
    assert [t.map_key for t in sword.owner_templates] == [
        "1111aaaa-0000-0000-0000-000000000001"
    ]
    # the magic variant inherits Requirements via `using`, but no template
    # names its stats entry directly
    magic = game.items["WPN_Longsword_Magic"]
    assert magic.requirements == ["Str 13"]
    assert magic.owner_templates == []


def test_tag_ids_merge_template_chain(game):
    sword = game.items["WPN_Longsword"]
    assert sword.tag_ids == [
        "aaaa1111-0000-0000-0000-000000000001",  # from BASE_Weapon parent
        "bbbb2222-0000-0000-0000-000000000002",  # own tag
    ]
    # magic variant shares the RootTemplate, hence the tags
    assert game.items["WPN_Longsword_Magic"].tag_ids == sword.tag_ids
    # no template → no tags
    assert game.items["_BaseWeapon"].tag_ids == []


def test_tag_registry(game):
    assert len(game.tags) == 2
    weapon = game.tags["WEAPON"]                     # by engine name
    assert weapon is game.tags["aaaa1111-0000-0000-0000-000000000001"]  # by UUID
    assert weapon.display_name == "Weapon"           # localized via .loca
    assert weapon.categories == ["Item"]
    assert game.tags["LONGSWORD"].display_name == ""  # no handle, no crash
    with pytest.raises(KeyError):
        game.tags["NOPE"]


def test_item_tags_resolve_to_tag_objects(game):
    sword = game.items["WPN_Longsword"]
    assert [tag.name for tag in sword.tags] == ["WEAPON", "LONGSWORD"]
    assert sword.tags[0].display_name == "Weapon"


def test_tag_items_reverse_edge(game):
    tagged = game.tags["LONGSWORD"].items
    assert {item.name for item in tagged} == {"WPN_Longsword", "WPN_Longsword_Magic"}
    # lookup by name and by UUID agree
    assert game.items_with_tag("LONGSWORD") == game.items_with_tag(
        "bbbb2222-0000-0000-0000-000000000002"
    )
    assert game.items_with_tag("unknown-uuid") == []


def test_relationships_are_lazy_and_cached(data_dir):
    game = Game(data_dir=data_dir)
    # constructing a Game reads nothing: no collection is materialized yet
    assert "stats" not in vars(game)
    assert "items" not in vars(game)
    magic = game.items["WPN_Longsword_Magic"]
    assert "stats" in vars(game)          # first access loaded lazily
    assert "passives" not in vars(magic)  # relationship untouched so far
    first = magic.passives
    assert magic.passives is first        # resolved once, cached on instance


def test_resolution_cycle_is_recorded_not_fatal(tmp_path):
    """A genuine inheritance cycle skips that entry and records an issue
    instead of aborting the items build (regression: retail export died
    on 'inheritance cycle at MAG_Frost_GenerateFrostOnDamage_Gloves')."""
    from bg3forge.pak import PakWriter
    from conftest import fixture_files

    writer = PakWriter()
    for name, data in fixture_files().items():
        writer.add(name, data)
    writer.add(
        "Public/Cycle/Stats/Generated/Data/Cycle.txt",
        b'new entry "ARM_A"\ntype "Armor"\nusing "ARM_B"\n'
        b'new entry "ARM_B"\ntype "Armor"\nusing "ARM_A"\n',
    )
    writer.write(tmp_path / "Shared.pak")

    game = Game(data_dir=tmp_path)
    assert {i.name for i in game.items} >= {"WPN_Longsword"}  # build survives
    assert "ARM_A" not in game.items
    cycle_issues = [i for i in game.load_issues if "cycle" in i.error]
    assert len(cycle_issues) == 2  # both cycle members skipped and recorded


def test_self_using_override_resolves(tmp_path):
    """The retail patch-layering pattern resolves instead of cycling."""
    from bg3forge.pak import PakWriter
    from conftest import fixture_files

    writer = PakWriter()
    for name, data in fixture_files().items():
        writer.add(name, data)
    # a higher-priority pak layers a rarity change over the base longsword
    # (priority beats the unhelpful alphabetical order of the filenames)
    writer.write(tmp_path / "Shared.pak")
    patch = PakWriter(priority=10)
    patch.add(
        "Public/Patch/Stats/Generated/Data/Weapon.txt",
        b'new entry "WPN_Longsword"\ntype "Weapon"\nusing "WPN_Longsword"\n'
        b'data "Rarity" "Legendary"\n',
    )
    patch.write(tmp_path / "Patch1.pak")

    game = Game(data_dir=tmp_path)
    sword = game.items["WPN_Longsword"]
    assert sword.rarity == "Legendary"          # patched layer wins
    assert sword.data["Damage"] == "1d8"        # base layer preserved
    assert sword.display_name == "Longsword"    # template join intact
    assert game.load_issues == []


def test_linked_models_still_export_cleanly(game, tmp_path):
    """The game back-reference must never leak into exports."""
    import json

    from bg3forge.exporters import export_json
    from bg3forge.models import to_record

    magic = game.items["WPN_Longsword_Magic"]
    record = to_record(magic)
    assert "_game" not in record
    path = export_json([magic], tmp_path / "item.json")
    dumped = json.loads(path.read_text("utf-8"))
    assert dumped[0]["name"] == "WPN_Longsword_Magic"
    assert "_game" not in dumped[0]


def test_treasure_tables(game):
    assert game.treasure_tables[0].items() == ["WPN_Longsword"]


def test_atlases(game):
    assert len(game.atlases) == 1
    atlas = game.atlases[0]
    assert atlas.width == 128
    assert "Item_WPN_Longsword" in atlas


def test_lsf_roottemplates(tmp_path):
    """Templates shipped as binary .lsf resolve exactly like .lsx ones."""
    from bg3forge.pak import PakWriter
    from bg3forge.parsers import parse_lsx, write_lsf
    from conftest import ROOTTEMPLATE_LSX, fixture_files

    writer = PakWriter()
    for name, data in fixture_files().items():
        if name.endswith("Weapons.lsx"):
            name = name[: -len(".lsx")] + ".lsf"
            data = write_lsf(parse_lsx(ROOTTEMPLATE_LSX), version=7)
        writer.add(name, data)
    writer.write(tmp_path / "Shared.pak")

    game = Game(data_dir=tmp_path)
    items = {item.name: item for item in game.items}
    assert items["WPN_Longsword"].display_name == "Longsword"
    assert items["WPN_Longsword"].description == "A trusty longsword."


def test_game_from_extracted_dir(tmp_path, sample_pak):
    out = tmp_path / "extracted"
    Extractor(out).extract(sample_pak)
    game = Game(extracted_dir=out)
    assert {item.name for item in game.items} >= {"WPN_Longsword"}
    assert game.spells[0].display_name == "Fireball"
