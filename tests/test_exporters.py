import csv
import json
import sqlite3

import pytest

from bg3forge.exporters import export_csv, export_json, export_markdown, export_sqlite, export_yaml
from bg3forge.models import Spell
from bg3forge.parsers.progressions import Progression
from bg3forge.parsers.spelllists import SpellList


@pytest.fixture
def spells():
    return [
        Spell.from_stats(
            "Projectile_Fireball",
            {"SpellType": "Projectile", "Level": "3", "Damage": "8d6", "Icon": "Spell_Fireball"},
            display_name="Fireball",
        ),
        Spell.from_stats(
            "Target_MainHandAttack",
            {"SpellType": "Target", "Level": "0"},
            display_name="Main Hand Attack",
        ),
    ]


def test_export_json(tmp_path, spells):
    path = export_json(spells, tmp_path / "spells.json")
    records = json.loads(path.read_text("utf-8"))
    assert len(records) == 2
    assert records[0]["name"] == "Projectile_Fireball"
    assert records[0]["data"]["Damage"] == "8d6"


def test_export_json_deterministic(tmp_path, spells):
    a = export_json(spells, tmp_path / "a.json").read_text()
    b = export_json(spells, tmp_path / "b.json").read_text()
    assert a == b


def test_export_json_flatten(tmp_path, spells):
    path = export_json(spells, tmp_path / "flat.json", flatten=True)
    records = json.loads(path.read_text("utf-8"))
    assert records[0]["data.Damage"] == "8d6"
    assert "data" not in records[0]


def test_export_csv(tmp_path, spells):
    path = export_csv(spells, tmp_path / "spells.csv")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["name"] == "Projectile_Fireball"
    assert rows[0]["data.Damage"] == "8d6"
    assert rows[1]["data.Damage"] == ""


def test_export_sqlite(tmp_path, spells):
    path = export_sqlite(spells, tmp_path / "bg3.db", table="spells")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT * FROM "spells" ORDER BY name').fetchall()
    assert len(rows) == 2
    assert rows[0]["name"] == "Projectile_Fireball"
    assert rows[0]["level"] == 3
    # re-export is idempotent
    export_sqlite(spells, path, table="spells")
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM "spells"').fetchone()[0] == 2


def test_export_sqlite_empty(tmp_path):
    path = export_sqlite([], tmp_path / "empty.db", table="nothing")
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM "nothing"').fetchone()[0] == 0


def test_export_markdown(tmp_path, spells):
    path = export_markdown(spells, tmp_path / "spells.md", title="Spells",
                           columns=["name", "display_name", "level"])
    text = path.read_text("utf-8")
    assert text.startswith("# Spells")
    assert "| Projectile_Fireball | Fireball | 3 |" in text


def test_export_markdown_escapes_pipes(tmp_path):
    path = export_markdown([{"a": "x|y", "b": "line1\nline2"}], tmp_path / "t.md")
    text = path.read_text("utf-8")
    assert "x\\|y" in text
    assert "line1<br>line2" in text


def test_export_yaml(tmp_path, spells):
    yaml = pytest.importorskip("yaml")
    path = export_yaml(spells, tmp_path / "spells.yaml")
    records = yaml.safe_load(path.read_text("utf-8"))
    assert records[0]["name"] == "Projectile_Fireball"


def test_export_csv_flattens_progression_fields_and_lists(tmp_path):
    progression = Progression(
        uuid="11111111-1111-1111-1111-111111111111",
        name="Wizard",
        table_uuid="22222222-2222-2222-2222-222222222222",
        level=2,
        progression_type=0,
        fields={
            "Boosts": "ActionResource(SpellSlot,1,2)",
            "PassivesAdded": "SculptSpells;ArcaneRecovery",
        },
        subclass_ids=[
            "33333333-3333-3333-3333-333333333333",
            "44444444-4444-4444-4444-444444444444",
        ],
    )

    path = export_csv([progression], tmp_path / "progressions.csv")
    with path.open(newline="", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))

    assert "fields" not in row
    assert row["fields.Boosts"] == "ActionResource(SpellSlot,1,2)"
    assert row["fields.PassivesAdded"] == "SculptSpells;ArcaneRecovery"
    assert row["subclass_ids"] == (
        "33333333-3333-3333-3333-333333333333;"
        "44444444-4444-4444-4444-444444444444"
    )


def test_export_sqlite_flattens_spell_list_fields_and_lists(tmp_path):
    spell_list = SpellList(
        uuid="55555555-5555-5555-5555-555555555555",
        spell_names=["Projectile_Fireball", "Target_MistyStep"],
        comment="Wizard level 2",
        fields={
            "Name": "Wizard spells",
            "Spells": "Projectile_Fireball;Target_MistyStep",
        },
    )

    path = export_sqlite([spell_list], tmp_path / "bg3.db", table="spell_lists")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM "spell_lists"').fetchone()

    assert row is not None
    assert "fields" not in row.keys()
    assert row["fields_Name"] == "Wizard spells"
    assert row["fields_Spells"] == "Projectile_Fireball;Target_MistyStep"
    assert row["spell_names"] == "Projectile_Fireball;Target_MistyStep"


def test_export_json_keeps_spell_list_structure_nested(tmp_path):
    spell_list = SpellList(
        uuid="55555555-5555-5555-5555-555555555555",
        spell_names=["Projectile_Fireball", "Target_MistyStep"],
        fields={"Name": "Wizard spells"},
    )

    path = export_json([spell_list], tmp_path / "spell-lists.json")
    record = json.loads(path.read_text("utf-8"))[0]

    assert record["fields"] == {"Name": "Wizard spells"}
    assert record["spell_names"] == ["Projectile_Fireball", "Target_MistyStep"]
