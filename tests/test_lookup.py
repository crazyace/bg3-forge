"""Tests for `bg3forge lookup` — name / UUID / handle resolution."""

import pytest

from bg3forge import Game
from bg3forge.lookup import lookup


@pytest.fixture
def game(data_dir):
    return Game(data_dir=data_dir)


def _section(result, title_prefix):
    return next((s for s in result.sections if s.title.startswith(title_prefix)), None)


def _rows(section):
    return dict(section.rows)


def test_lookup_item_with_cross_references(game):
    result = lookup(game, "WPN_Longsword_Magic")
    section = _section(result, "item:")
    assert section is not None
    rows = _rows(section)
    assert rows["display name"] == "Longsword"
    assert rows["type"] == "Weapon"
    # the magic longsword grants a passive, a status, and a spell
    assert "SavageAttacks" in rows["grants passives"]
    assert "BURNING" in rows["applies statuses"]
    assert "Projectile_Fireball" in rows["unlocks spells"]


def test_lookup_spell_reverse_edges(game):
    result = lookup(game, "Projectile_Fireball")
    rows = _rows(_section(result, "spell:"))
    assert rows["display name"] == "Fireball"
    assert "WPN_Longsword_Magic" in rows["unlocked by items"]     # reverse: item unlock
    assert "Wizard" in rows["granted by progressions"]            # reverse: progression


def test_lookup_status_and_applied_by(game):
    rows = _rows(_section(lookup(game, "BURNING"), "status:"))
    assert rows["display name"] == "Burning"
    assert "WPN_Longsword_Magic" in rows["applied by items"]


def test_lookup_tag_by_name_and_uuid(game):
    by_name = _section(lookup(game, "LONGSWORD"), "tag:")
    assert _rows(by_name)["UUID"] == "bbbb2222-0000-0000-0000-000000000002"
    by_uuid = _section(lookup(game, "bbbb2222-0000-0000-0000-000000000002"), "tag:")
    assert _rows(by_uuid)["name"] == "LONGSWORD"


def test_lookup_handle_resolves_text(game):
    result = lookup(game, "h11111111-1111-1111-1111-111111111111;1")
    rows = _rows(_section(result, "Localization handle"))
    assert rows["text"] == "Fireball"


def test_lookup_partial_name_suggests(game):
    result = lookup(game, "longsword")   # lowercase, not an exact stats name
    assert not result.found
    assert any("WPN_Longsword" in s for s in result.suggestions)


def test_lookup_no_match(game):
    result = lookup(game, "does_not_exist_xyz")
    assert not result.found
    assert not result.suggestions


def test_lookup_cli_exit_codes(data_dir, capsys):
    from bg3forge.cli.main import main

    assert main(["--data-dir", str(data_dir), "lookup", "WPN_Longsword"]) == 0
    assert "item: WPN_Longsword" in capsys.readouterr().out

    assert main(["--data-dir", str(data_dir), "lookup", "no_such_thing"]) == 1
    assert "No match" in capsys.readouterr().out
