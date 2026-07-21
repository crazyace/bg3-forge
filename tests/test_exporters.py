import csv
import json
import sqlite3

import pytest

from bg3forge.exporters import export_csv, export_json, export_markdown, export_sqlite, export_yaml
from bg3forge.models import Spell


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
