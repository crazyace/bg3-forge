"""Tests for character stat blocks and equipment sets."""

import pytest

from bg3forge import Game
from bg3forge.parsers import parse_equipment_sets
from conftest import EQUIPMENT_TXT


# -- equipment parser --------------------------------------------------------

def test_parse_equipment_sets():
    sets = parse_equipment_sets(EQUIPMENT_TXT, source="Equipment.txt")
    assert len(sets) == 1
    eqp = sets[0]
    assert eqp.name == "EQP_Goblin_Warrior"
    assert eqp.initial_weapon_set == "Melee"
    assert eqp.groups == [["WPN_Longsword"], ["ARM_Missing_Leather"]]
    assert eqp.entries() == ["WPN_Longsword", "ARM_Missing_Leather"]


def test_parse_equipment_tolerates_noise():
    sets = parse_equipment_sets(
        '// comment\nadd equipment entry "orphan"\n'
        'new equipment "X"\nadd equipment entry "A"\n'  # entry before any group
    )
    assert len(sets) == 1
    assert sets[0].groups == [["A"]]


# -- Game integration --------------------------------------------------------

@pytest.fixture
def game(data_dir):
    return Game(data_dir=data_dir)


def test_characters_join_templates(game):
    warrior = game.characters["GOB_Warrior"]
    assert warrior.display_name == "Goblin Warrior"     # template + loca
    assert warrior.map_key == "2222bbbb-0000-0000-0000-000000000002"
    assert warrior.archetype == "melee"
    assert warrior.level == 3
    assert warrior.vitality == 21
    assert warrior.armor == 15
    assert warrior.strength == 16
    assert warrior.dexterity == 10                      # via `using` inheritance
    # base entry exists but has no template
    base = game.characters["_BaseCharacter"]
    assert base.display_name == "" and base.map_key is None


def test_character_passives_link(game):
    warrior = game.characters["GOB_Warrior"]
    assert warrior.passive_names == ["SavageAttacks"]
    assert [p.display_name for p in warrior.passives] == ["Savage Attacks"]
    # reverse edge
    assert game.passives["SavageAttacks"].characters == [warrior]
    assert game.characters_with_passive("Unknown") == []


def test_character_equipment_resolves_to_items(game):
    warrior = game.characters["GOB_Warrior"]
    assert warrior.equipment_name == "EQP_Goblin_Warrior"
    assert warrior.equipment is game.equipment["EQP_Goblin_Warrior"]
    assert warrior.equipment.initial_weapon_set == "Melee"
    # entries resolve to Item models; undefined stats names are omitted
    assert [item.name for item in warrior.equipment_items] == ["WPN_Longsword"]
    assert warrior.equipment_items[0].display_name == "Longsword"


def test_equipment_collection(game):
    assert len(game.equipment) == 1
    assert "EQP_Goblin_Warrior" in game.equipment
    assert game.equipment.get("EQP_Nope") is None


def test_characters_search(game):
    assert game.characters.find("goblin")[0].name == "GOB_Warrior"


def test_characters_export_cleanly(game, tmp_path):
    import json

    from bg3forge.exporters import export_json

    path = export_json(game.characters, tmp_path / "characters.json")
    records = json.loads(path.read_text("utf-8"))
    warrior = next(r for r in records if r["name"] == "GOB_Warrior")
    assert warrior["strength"] == 16
    assert "_game" not in warrior
