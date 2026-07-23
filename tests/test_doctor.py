"""Tests for bg3forge doctor."""

import pytest

from bg3forge.cli.main import main
from bg3forge.doctor import FAIL, OK, WARN, format_report, run_doctor
from bg3forge.pak import PakWriter, lz4compat

META_LSX = """\
<save>
  <region id="Config">
    <node id="root">
      <children>
        <node id="ModuleInfo">
          <attribute id="Name" type="LSString" value="Gustav" />
          <attribute id="Version64" type="int64" value="{version64}" />
        </node>
      </children>
    </node>
  </region>
</save>
"""


def _check(report, label):
    matches = [c for c in report.checks if c.label == label]
    assert matches, f"no check labeled {label!r} in {[c.label for c in report.checks]}"
    return matches[0]


@pytest.fixture
def full_install(data_dir):
    """Fixture data dir upgraded to look like a real install: Gustav.pak
    with a module meta.lsx carrying a packed Version64."""
    version64 = (4 << 55) | (1 << 47) | (1 << 31) | 100  # 4.1.1.100
    writer = PakWriter()
    writer.add("Mods/Gustav/meta.lsx", META_LSX.format(version64=version64).encode())
    writer.write(data_dir / "Gustav.pak")
    return data_dir


def test_doctor_healthy_install(full_install):
    report = run_doctor(data_dir=full_install)
    assert report.ok
    assert _check(report, "Shared.pak").status == OK
    assert _check(report, "Gustav pak").status == OK
    assert _check(report, "English localization").status == OK
    version = _check(report, "Game data version")
    assert version.status == OK
    assert "4.1.1.100" in version.detail
    assert "Gustav" in version.detail
    assert _check(report, "Pak archives").status == OK
    assert "2 readable" in _check(report, "Pak archives").detail


def test_doctor_reports_corrupt_pak(data_dir):
    """A pak whose header parses but whose file list is damaged used to
    be silently skipped by the content scan; it must FAIL the report."""
    from bg3forge.pak.format import HEADER_STRUCT, SIGNATURE

    corrupt = HEADER_STRUCT.pack(SIGNATURE, 18, 10**6, 0, 0, 0, b"\x00" * 16, 0)
    (data_dir / "Corrupt.pak").write_bytes(corrupt)

    report = run_doctor(data_dir=data_dir)
    assert not report.ok
    check = _check(report, "Corrupt pak")
    assert check.status == FAIL
    assert "Corrupt.pak" in check.detail


def test_doctor_warns_without_gustav_or_meta(data_dir):
    report = run_doctor(data_dir=data_dir)
    assert report.ok  # warnings, not failures
    warned = {c.label for c in report.warnings}
    assert "Gustav pak" in warned
    assert "Game data version" in warned


def test_doctor_warns_on_missing_language(full_install):
    report = run_doctor(data_dir=full_install, language="German")
    assert _check(report, "German localization").status == WARN


def test_doctor_fails_without_install(tmp_path, monkeypatch):
    monkeypatch.delenv("BG3_PATH", raising=False)
    report = run_doctor(path=tmp_path)
    assert not report.ok
    assert _check(report, "BG3 installation").status == FAIL


def test_doctor_fails_on_unsupported_pak_version(full_install):
    bogus = b"LSPK" + (99).to_bytes(4, "little") + b"\x00" * 56
    (full_install / "Future.pak").write_bytes(bogus)
    report = run_doctor(data_dir=full_install)
    assert not report.ok
    failure = _check(report, "Unsupported pak version")
    assert "Future.pak" in failure.detail


def test_doctor_warns_without_native_lz4(full_install, monkeypatch):
    monkeypatch.setattr(lz4compat, "HAVE_NATIVE_LZ4", False)
    report = run_doctor(data_dir=full_install)
    assert _check(report, "Native LZ4").status == WARN
    pretty = format_report(report, unicode_symbols=True)
    assert "Warnings" in pretty
    assert "Native LZ4: not installed" in pretty


def test_format_report_symbols(full_install, monkeypatch):
    # Keep this formatting test deterministic in both the regular and
    # deliberately dependency-free CI jobs.
    monkeypatch.setattr(lz4compat, "HAVE_NATIVE_LZ4", True)
    report = run_doctor(data_dir=full_install)
    pretty = format_report(report, unicode_symbols=True)
    assert "✓ Shared.pak" in pretty
    assert "Warnings" in pretty and "None" in pretty
    plain = format_report(report, unicode_symbols=False)
    assert "[ OK ] Shared.pak" in plain
    assert "✓" not in plain


def test_doctor_cli(full_install, capsys):
    assert main(["--data-dir", str(full_install), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "BG3 data directory" in out
    assert "Game data version" in out


def test_doctor_cli_failure_exit(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("BG3_PATH", raising=False)
    monkeypatch.setattr("bg3forge.locate._candidate_paths", lambda: [])
    assert main(["--game-path", str(tmp_path), "doctor"]) == 1
