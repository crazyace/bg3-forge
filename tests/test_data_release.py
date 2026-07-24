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
    assert not list(out.glob(".bg3forge-data-*"))

    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        expected = {"MANIFEST.json", "bg3forge-data.sqlite"}
        expected.update(f"json/{dataset}.json" for dataset in mod.DATASETS)
        expected.update(f"csv/{dataset}.csv" for dataset in mod.DATASETS)
        assert names == expected

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
    out = tmp_path / "dist"
    # Simulate the persistent staging directory used by older releases.
    # A clean per-run staging tree must never copy this into the ZIP.
    stale = out / "bundle" / "obsolete.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("must not ship", "utf-8")

    hashes = []
    for _run in range(2):
        code = mod.main(
            ["--data-dir", str(data_dir), "--output", str(out), "--label", "x"]
        )
        assert code == 0
        bundle = out / "bg3forge-data-x.zip"
        hashes.append(bundle.read_bytes())
        with zipfile.ZipFile(bundle) as zf:
            assert "obsolete.txt" not in zf.namelist()
        assert not list(out.glob(".bg3forge-data-*"))

    # Same install + same output directory -> byte-identical atomic replacement.
    assert hashes[0] == hashes[1]


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
    assert "no new release bundle was published" in captured.err
    assert "attach it to a release" not in captured.out
    assert not (out / "bg3forge-data-bad.zip").exists()
    assert not list(out.glob(".bg3forge-data-*"))


def test_failed_validation_preserves_existing_bundle(
    tmp_path, data_dir, monkeypatch, capsys
):
    mod = _load_script()
    from bg3forge.validate import ValidationIssue, ValidationReport

    out = tmp_path / "dist"
    args = ["--data-dir", str(data_dir), "--output", str(out), "--label", "same"]
    assert mod.main(args) == 0
    bundle = out / "bg3forge-data-same.zip"
    known_good = bundle.read_bytes()
    capsys.readouterr()

    report = ValidationReport(
        issues=[ValidationIssue(file="<audit>", stage="audit", error="forced")]
    )
    monkeypatch.setattr(mod, "validate_data", lambda *_args, **_kwargs: report)

    assert mod.main(args) == 1
    captured = capsys.readouterr()
    assert "existing" in captured.err
    assert "was left unchanged" in captured.err
    assert "attach it to a release" not in captured.out
    assert bundle.read_bytes() == known_good
    assert not list(out.glob(".bg3forge-data-*"))


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
