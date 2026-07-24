"""Smoke test for scripts/build_data_release.py (the data-export release).

The script generates the community data bundle from an installed game; it
can't be exercised against retail here, but running it against the
synthetic fixture install proves it stays wired to the exporters and
produces a well-formed, reproducible bundle.
"""

import importlib.util
import io
import json
import sqlite3
import zipfile
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_data_release.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_data_release", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_data_release_bundle(tmp_path, data_dir, capsys):
    mod = _load_script()
    out = tmp_path / "dist"
    code = mod.main(["--data-dir", str(data_dir), "--output", str(out), "--label", "testfix"])
    assert code == 0

    captured = capsys.readouterr()
    assert "Building BG3 Forge data release" in captured.err
    assert "[ 1/10] Exporting items..." in captured.err
    assert "[ 9/10] Validating source archives..." in captured.err
    assert "[10/10] Writing release bundle..." in captured.err
    assert "done — 3 rows" in captured.err
    assert "wrote" in captured.out

    bundle = out / "bg3forge-data-testfix.zip"
    assert bundle.exists()

    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        assert "MANIFEST.json" in names
        assert "bg3forge-data.sqlite" in names
        for dataset in mod.DATASETS:
            assert f"json/{dataset}.json" in names
            assert f"csv/{dataset}.csv" in names

        manifest = json.loads(zf.read("MANIFEST.json"))
        # every dataset is counted, and the coverage sweep ran clean
        assert set(manifest["datasets"]) == set(mod.DATASETS)
        assert manifest["datasets"]["items"] == 3
        assert manifest["coverage"]["ok"] is True
        assert manifest["game_version"] == "unknown"  # fixture has no meta.lsx

        # the sqlite dataset is a real, queryable table
        (tmp_path / "bg3.sqlite").write_bytes(zf.read("bg3forge-data.sqlite"))

    con = sqlite3.connect(tmp_path / "bg3.sqlite")
    names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"items", "spells", "characters"} <= names
    con.close()


def test_build_data_release_is_reproducible(tmp_path, data_dir):
    mod = _load_script()
    hashes = []
    for run in ("a", "b"):
        out = tmp_path / run
        mod.main(["--data-dir", str(data_dir), "--output", str(out), "--label", "x"])
        hashes.append((out / "bg3forge-data-x.zip").read_bytes())
    assert hashes[0] == hashes[1]  # same install -> byte-identical bundle


def test_build_data_release_refuses_failed_validation(
    tmp_path, data_dir, monkeypatch, capsys
):
    mod = _load_script()
    from bg3forge.validate import ValidationIssue, ValidationReport

    report = ValidationReport(
        issues=[
            ValidationIssue(
                file="<progressions>",
                stage="progression-passives",
                error="1 unresolved passive reference",
            )
        ]
    )
    monkeypatch.setattr(mod, "validate_data", lambda *_args, **_kwargs: report)

    out = tmp_path / "dist"
    code = mod.main(
        ["--data-dir", str(data_dir), "--output", str(out), "--label", "bad"]
    )

    assert code == 1
    captured = capsys.readouterr()
    assert "release bundle was not written" in captured.err
    assert "attach it to a release" not in captured.out
    assert not (out / "bg3forge-data-bad.zip").exists()


class _TTYBuffer(io.StringIO):
    def isatty(self):
        return True


def test_build_data_release_live_progress_detail():
    mod = _load_script()
    stream = _TTYBuffer()
    progress = mod._Progress(1, stream=stream)

    progress.start("Validating source archives")
    progress.update("[1/2] Shared.pak")
    progress.finish("2 paks, 0 issues")

    output = stream.getvalue()
    assert "[1/1] Validating source archives..." in output
    assert "\r  [1/2] Shared.pak" in output
    assert "done — 2 paks, 0 issues" in output
