"""Tests for `bg3forge lint` — mod-pak consistency checking."""

import pytest

from bg3forge import Game, Mod
from bg3forge.lint import ERROR, WARNING, lint_mod
from bg3forge.pak import PakWriter

VALID_UUID = "11111111-2222-3333-4444-555555555555"


def _categories(report, severity):
    return {f.category for f in report.findings if f.severity == severity}


def test_lint_clean_mod_with_base(tmp_path, data_dir):
    """A well-formed mod whose references all exist in the base game
    passes with no errors."""
    mod = Mod("CleanMod")
    mod.new_armor(
        "ARM_Clean",
        armor_class=18,
        stats_using="_BaseWeapon",          # exists in the fixture base
        parent_template=VALID_UUID,
        display_name="Clean Plate",         # handle is minted into the mod's .loca
        description="Shiny.",
        passives=["SavageAttacks"],         # exists in the fixture base
        statuses=["BURNING"],               # exists in the fixture base
    )
    pak = mod.build(tmp_path / "CleanMod.pak")

    report = lint_mod(pak, base=Game(data_dir=data_dir))
    assert report.ok, [f.message for f in report.errors]
    assert not report.warnings


def test_lint_flags_broken_references(tmp_path, data_dir):
    """using / status / passive references absent from base + mod are
    reported once the base game is available to resolve against."""
    mod = Mod("BrokenRefs")
    mod.new_armor(
        "ARM_Broken",
        armor_class=18,
        stats_using="_NoSuchBase",
        parent_template=VALID_UUID,
        display_name="Broken",
        passives=["NoSuchPassive"],
        statuses=["NoSuchStatus"],
    )
    pak = mod.build(tmp_path / "BrokenRefs.pak")

    report = lint_mod(pak, base=Game(data_dir=data_dir))
    assert not report.ok
    assert "using" in _categories(report, ERROR)          # missing using -> error
    assert "reference" in _categories(report, WARNING)    # missing passive/status -> warning
    messages = " ".join(f.message for f in report.findings)
    assert "_NoSuchBase" in messages
    assert "NoSuchPassive" in messages and "NoSuchStatus" in messages


def test_lint_flags_placeholder_uuid(tmp_path):
    """A left-in placeholder parent-template UUID is caught even without a
    base install (it is a format error, not a reference)."""
    mod = Mod("PlaceholderUUID")
    mod.new_armor(
        "ARM_Ph",
        armor_class=18,
        parent_template="<base-template-uuid>",   # the README placeholder, shipped by mistake
        display_name="Oops",
    )
    pak = mod.build(tmp_path / "PlaceholderUUID.pak")

    report = lint_mod(pak)  # no base needed
    assert not report.ok
    assert "uuid" in _categories(report, ERROR)


def test_lint_flags_dangling_handle(tmp_path):
    """A DisplayName pointing at a handle with no .loca entry is a warning
    (it renders as a raw handle in game). Checkable without a base."""
    writer = PakWriter()
    writer.add(
        "Public/Mod/Stats/Generated/Data/Weapon.txt",
        b'new entry "WPN_NoLoca"\ntype "Weapon"\n'
        b'data "DisplayName" "hdeadbeef-0000-0000-0000-000000000000;1"\n',
    )
    pak = writer.write(tmp_path / "Dangling.pak")

    report = lint_mod(pak)
    assert any(f.category == "handle" and f.severity == WARNING for f in report.findings)
    assert report.ok  # a dangling handle is a warning, not an error


def test_lint_reports_parse_failure(tmp_path):
    writer = PakWriter()
    writer.add(
        "Public/Mod/Stats/Generated/Data/Bad.txt",
        b'data "Orphan" "1"\n',  # structural line outside any block
    )
    pak = writer.write(tmp_path / "BadParse.pak")

    report = lint_mod(pak)
    assert not report.ok
    assert "parse" in _categories(report, ERROR)


def test_lint_cli_exit_codes(tmp_path, data_dir, capsys):
    from bg3forge.cli.main import main

    good = Mod("CliGood")
    good.new_armor("ARM_Ok", armor_class=18, stats_using="_BaseWeapon",
                   parent_template=VALID_UUID, display_name="Ok")
    good_pak = good.build(tmp_path / "CliGood.pak")
    assert main(["--data-dir", str(data_dir), "lint", str(good_pak)]) == 0
    assert "no issues" in capsys.readouterr().out

    bad = Mod("CliBad")
    bad.new_armor("ARM_Bad", armor_class=18, parent_template="<base-template-uuid>")
    bad_pak = bad.build(tmp_path / "CliBad.pak")
    assert main(["lint", str(bad_pak)]) == 1
    assert "error" in capsys.readouterr().out.lower()
