import json
import sqlite3

from bg3forge.cli.main import main


def test_list(sample_pak, capsys):
    assert main(["list", str(sample_pak)]) == 0
    out = capsys.readouterr().out
    assert "Public/Shared/Stats/Generated/Data/Weapon.txt" in out


def test_unpack_single_pak(tmp_path, sample_pak, capsys):
    out_dir = tmp_path / "extracted"
    assert main(["unpack", str(sample_pak), "-o", str(out_dir)]) == 0
    assert (out_dir / "Public/Shared/Stats/Generated/Data/Weapon.txt").exists()
    # second run skips everything
    assert main(["unpack", str(sample_pak), "-o", str(out_dir)]) == 0
    assert "0 extracted" in capsys.readouterr().out


def test_unpack_pattern(tmp_path, sample_pak):
    out_dir = tmp_path / "loca-only"
    assert main(["unpack", str(sample_pak), "-o", str(out_dir), "-p", "*.loca"]) == 0
    assert (out_dir / "Localization/English/english.loca").exists()
    assert not (out_dir / "Public/Shared/Stats/Generated/Data/Weapon.txt").exists()


def test_spells_json(tmp_path, data_dir, capsys):
    output = tmp_path / "spells.json"
    assert main(["--data-dir", str(data_dir), "spells", "-o", str(output)]) == 0
    records = json.loads(output.read_text("utf-8"))
    assert records[0]["display_name"] == "Fireball"


def test_items_csv(tmp_path, data_dir):
    output = tmp_path / "items.csv"
    assert main(["--data-dir", str(data_dir), "items", "-o", str(output), "-f", "csv"]) == 0
    assert "WPN_Longsword" in output.read_text("utf-8")


def test_export_all_sqlite(tmp_path, data_dir, capsys):
    out_dir = tmp_path / "export"
    assert main(["--data-dir", str(data_dir), "export", "sqlite", "-o", str(out_dir)]) == 0
    with sqlite3.connect(out_dir / "bg3.db") as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"items", "spells", "passives", "statuses"} <= tables


def test_export_all_json(tmp_path, data_dir):
    out_dir = tmp_path / "export"
    assert main(["--data-dir", str(data_dir), "export", "json", "-o", str(out_dir)]) == 0
    for dataset in ("items", "spells", "passives", "statuses"):
        assert (out_dir / f"{dataset}.json").exists()


def test_patches_snapshot(tmp_path, data_dir, capsys):
    snapshot = tmp_path / "snap.json"
    args = ["--data-dir", str(data_dir), "patches", "--snapshot", str(snapshot)]
    assert main(args + ["--update"]) == 0
    assert snapshot.exists()
    assert main(args) == 0
    assert "no changes detected" in capsys.readouterr().out


def test_convert_lsx_to_lsf_and_back(tmp_path, capsys):
    from bg3forge.parsers import load_resource
    from conftest import ROOTTEMPLATE_LSX

    lsx_in = tmp_path / "Weapons.lsx"
    lsx_in.write_text(ROOTTEMPLATE_LSX, "utf-8")
    lsf = tmp_path / "Weapons.lsf"
    lsx_out = tmp_path / "Weapons.out.lsx"

    assert main(["convert", str(lsx_in), str(lsf), "--lsf-version", "7"]) == 0
    assert lsf.read_bytes()[:4] == b"LSOF"
    assert main(["convert", str(lsf), str(lsx_out)]) == 0

    document = load_resource(lsx_out)
    objects = list(document.find_all("GameObjects"))
    assert objects[1].get("Name") == "WPN_Longsword"
    assert objects[1].get("DisplayName") == "h55555555-5555-5555-5555-555555555555"


def test_convert_rejects_unknown_extension(tmp_path, capsys):
    source = tmp_path / "Weapons.lsx"
    source.write_text('<save><region id="R"><node id="R"/></region></save>', "utf-8")
    assert main(["convert", str(source), str(tmp_path / "out.bin")]) == 1
    assert "unsupported output format" in capsys.readouterr().err


def test_error_reporting(tmp_path, capsys):
    assert main(["list", str(tmp_path / "missing.pak")]) == 1
    assert "error:" in capsys.readouterr().err
