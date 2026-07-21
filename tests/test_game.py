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


def test_spells(game):
    spells = game.spells
    assert len(spells) == 1
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
