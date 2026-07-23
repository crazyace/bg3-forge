"""Tests for `bg3forge lint` — mod-pak consistency checking."""

import pytest

from bg3forge import Game, Mod
from bg3forge.lint import ERROR, WARNING, lint_mod
from bg3forge.pak import PakWriter
from bg3forge.parsers.lsx import write_lsx
from bg3forge.parsers.meta import ModuleInfo, build_meta_document

VALID_UUID = "11111111-2222-3333-4444-555555555555"


def _categories(report, severity):
    return {f.category for f in report.findings if f.severity == severity}


def _meta_bytes(name="ModName", uuid=VALID_UUID, folder=None, version=(1, 0, 0, 0)):
    """A serialized meta.lsx for hand-built test paks."""
    module = ModuleInfo(name=name, uuid=uuid, folder=folder or name, version=version)
    return write_lsx(build_meta_document(module)).encode("utf-8")


def _add_valid_meta(writer, folder="ModName"):
    writer.add(f"Mods/{folder}/meta.lsx", _meta_bytes(folder=folder))


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
    _add_valid_meta(writer)
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
    _add_valid_meta(writer)
    writer.add(
        "Public/Mod/Stats/Generated/Data/Bad.txt",
        b'data "Orphan" "1"\n',  # structural line outside any block
    )
    pak = writer.write(tmp_path / "BadParse.pak")

    report = lint_mod(pak)
    assert not report.ok
    assert "parse" in _categories(report, ERROR)


def test_lint_flags_missing_meta(tmp_path):
    """A pak with content but no meta.lsx is the #1 'mod doesn't show up'
    bug; it's an error even with nothing else to check."""
    writer = PakWriter()
    writer.add("Public/Mod/Stats/Generated/Data/Weapon.txt", b'new entry "WPN_X"\ntype "Weapon"\n')
    pak = writer.write(tmp_path / "NoMeta.pak")

    report = lint_mod(pak)
    assert not report.ok
    assert "meta" in _categories(report, ERROR)
    assert any("no Mods" in f.message for f in report.errors)


def test_lint_flags_meta_folder_mismatch(tmp_path):
    """meta.lsx at Mods/RealDir/ but ModuleInfo.Folder says something else —
    the game locates content by Folder, so this loads nothing."""
    writer = PakWriter()
    writer.add(
        "Mods/RealDir/meta.lsx",
        _meta_bytes(name="MyMod", folder="WrongName"),
    )
    writer.add("Public/WrongName/Stats/Generated/Data/W.txt", b'new entry "WPN_X"\ntype "Weapon"\n')
    pak = writer.write(tmp_path / "FolderMismatch.pak")

    report = lint_mod(pak)
    assert not report.ok
    assert any(f.category == "meta" and "Folder" in f.message for f in report.errors)


def test_lint_flags_malformed_meta_uuid(tmp_path):
    writer = PakWriter()
    writer.add("Mods/BadUuid/meta.lsx", _meta_bytes(folder="BadUuid", uuid="not-a-uuid"))
    pak = writer.write(tmp_path / "BadUuid.pak")

    report = lint_mod(pak)
    assert not report.ok
    assert any(f.category == "meta" and "UUID" in f.message for f in report.errors)


def test_lint_authored_mod_has_valid_meta(tmp_path):
    """The authoring path produces a meta.lsx that lint accepts — the
    manifest checks don't false-positive on Forge's own output."""
    mod = Mod("MetaOk")
    mod.new_armor("ARM_X", armor_class=18, parent_template=VALID_UUID, display_name="X")
    pak = mod.build(tmp_path / "MetaOk.pak")

    report = lint_mod(pak)
    assert "meta" not in _categories(report, ERROR)


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
