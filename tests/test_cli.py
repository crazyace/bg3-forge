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


def test_unpack_reports_corrupt_pak(tmp_path, sample_pak, capsys):
    """A damaged archive (LSPK signature, unreadable file list) must be
    reported with a non-zero exit — it used to be silently skipped as if
    it were a foreign file.  Real secondary parts still skip quietly."""
    from bg3forge.pak.format import HEADER_STRUCT, SIGNATURE

    data_dir = sample_pak.parent
    corrupt = HEADER_STRUCT.pack(SIGNATURE, 18, 10**6, 0, 0, 0, b"\x00" * 16, 0)
    (data_dir / "Corrupt.pak").write_bytes(corrupt)
    (data_dir / "Textures_1.pak").write_bytes(b"raw part data")

    out_dir = tmp_path / "extracted"
    code = main(["--data-dir", str(data_dir), "unpack", "-o", str(out_dir)])
    captured = capsys.readouterr()
    assert code == 1
    assert "Corrupt.pak" in captured.err
    assert "Textures_1.pak" not in captured.err
    # the good pak still extracted
    assert (out_dir / "Public/Shared/Stats/Generated/Data/Weapon.txt").exists()


def test_unpack_single_corrupt_pak_fails(tmp_path, capsys):
    """Naming a corrupt pak explicitly must fail, not print 'done'."""
    from bg3forge.pak.format import HEADER_STRUCT, SIGNATURE

    bad = tmp_path / "Corrupt.pak"
    bad.write_bytes(HEADER_STRUCT.pack(SIGNATURE, 18, 10**6, 0, 0, 0, b"\x00" * 16, 0))
    code = main(["unpack", str(bad), "-o", str(tmp_path / "out")])
    assert code == 1
    assert "Corrupt.pak" in capsys.readouterr().err


def test_patches_with_extracted_dir_errors_cleanly(tmp_path, sample_pak, capsys):
    """`patches --extracted-dir` has no pak directory to fingerprint; it
    must exit with a clear error, not a Path(None) TypeError traceback."""
    from bg3forge.pak.extractor import Extractor

    out = tmp_path / "extracted"
    Extractor(out).extract(sample_pak)
    code = main([
        "--extracted-dir", str(out),
        "patches", "--snapshot", str(tmp_path / "snap.json"),
    ])
    assert code == 1
    assert "needs a game install" in capsys.readouterr().err


def test_patch_scan_skips_unreadable_pak(tmp_path, sample_pak):
    """An unreadable .pak (here: a directory with the extension) must be
    skipped by the fingerprint scan, not raise OSError."""
    from bg3forge.pak.patches import PatchDetector

    (sample_pak.parent / "Weird.pak").mkdir()
    fingerprints = PatchDetector(tmp_path / "snap.json").scan(sample_pak.parent)
    assert "Shared.pak" in fingerprints
    assert "Weird.pak" not in fingerprints


def test_spells_json(tmp_path, data_dir, capsys):
    output = tmp_path / "spells.json"
    assert main(["--data-dir", str(data_dir), "spells", "-o", str(output)]) == 0
    records = json.loads(output.read_text("utf-8"))
    assert records[0]["display_name"] == "Fireball"


def test_items_csv(tmp_path, data_dir):
    output = tmp_path / "items.csv"
    assert main(["--data-dir", str(data_dir), "items", "-o", str(output), "-f", "csv"]) == 0
    assert "WPN_Longsword" in output.read_text("utf-8")


def test_progressions_json(tmp_path, data_dir):
    output = tmp_path / "progressions.json"
    assert main([
        "--data-dir", str(data_dir), "progressions", "-o", str(output)
    ]) == 0
    records = json.loads(output.read_text("utf-8"))
    assert [record["level"] for record in records] == [1, 2]

    spell_lists = tmp_path / "spell-lists.json"
    assert main([
        "--data-dir", str(data_dir), "spell-lists", "-o", str(spell_lists)
    ]) == 0
    assert len(json.loads(spell_lists.read_text("utf-8"))) == 3


def test_export_all_sqlite(tmp_path, data_dir, capsys):
    out_dir = tmp_path / "export"
    assert main(["--data-dir", str(data_dir), "export", "sqlite", "-o", str(out_dir)]) == 0
    with sqlite3.connect(out_dir / "bg3.db") as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "items", "spells", "passives", "statuses", "progressions",
        "spell_lists",
    } <= tables


def test_export_all_json(tmp_path, data_dir):
    out_dir = tmp_path / "export"
    assert main(["--data-dir", str(data_dir), "export", "json", "-o", str(out_dir)]) == 0
    for dataset in (
        "items", "spells", "passives", "statuses", "progressions",
        "spell_lists",
    ):
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
    assert objects[2].get("Name") == "WPN_Longsword"
    assert objects[2].get("DisplayName") == "h55555555-5555-5555-5555-555555555555"


def test_convert_rejects_unknown_extension(tmp_path, capsys):
    source = tmp_path / "Weapons.lsx"
    source.write_text('<save><region id="R"><node id="R"/></region></save>', "utf-8")
    assert main(["convert", str(source), str(tmp_path / "out.bin")]) == 1
    assert "unsupported output format" in capsys.readouterr().err


def test_error_reporting(tmp_path, capsys):
    assert main(["list", str(tmp_path / "missing.pak")]) == 1
    assert "error:" in capsys.readouterr().err
