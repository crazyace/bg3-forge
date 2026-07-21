"""Tests for the dialog parser and the lazy DialogIndex."""

import pytest

from bg3forge import Game
from bg3forge.parsers import DialogError, parse_dialog, parse_lsx
from conftest import DIALOG_LSX

DIALOG_PATH = "Mods/Shared/Story/DialogsBinary/Camp/CAMP_Greeting.lsf"


# -- parser ------------------------------------------------------------------

def test_parse_dialog_structure():
    dialog = parse_dialog(parse_lsx(DIALOG_LSX), source="CAMP_Greeting.lsx")
    assert dialog.uuid == "dddd0000-0000-0000-0000-000000000001"
    assert dialog.category == "Camp"
    assert dialog.timeline_id == "tttt0000-0000-0000-0000-000000000001"
    assert [s.index for s in dialog.speakers] == [0, 1]
    assert dialog.speakers[0].mapping_id == "5e2222aa-0000-0000-0000-00000000aa01"

    assert len(dialog.nodes) == 2
    greeting = dialog.node("n0000001")
    assert greeting.constructor == "TagGreeting"
    assert greeting.is_root and not greeting.is_end
    assert greeting.speaker == 0
    assert greeting.text_handles == [("h99990000-9999-9999-9999-999999999901", 1)]
    assert greeting.child_uuids == ["n0000002"]

    answer = dialog.node("n0000002")
    assert answer.is_end and not answer.is_root

    assert [n.uuid for n in dialog.roots] == ["n0000001"]
    assert [n.uuid for n in dialog.walk()] == ["n0000001", "n0000002"]
    assert len(dialog.text_handles()) == 2


def test_parse_dialog_rejects_non_dialog():
    with pytest.raises(DialogError, match="dialog"):
        parse_dialog(parse_lsx('<save><region id="Other"><node id="Other"/></region></save>'))


def test_walk_cuts_cycles():
    looped = parse_lsx(DIALOG_LSX)
    dialog = parse_dialog(looped)
    dialog.node("n0000002").child_uuids.append("n0000001")  # create a loop
    assert [n.uuid for n in dialog.walk()] == ["n0000001", "n0000002"]


# -- DialogIndex --------------------------------------------------------------

def test_registry_files_excluded_from_index(data_dir):
    """ScriptFlags/DialogVariables live under Story/Dialogs/ but are not
    dialogs (retail regression: 7 such files failed the sweep)."""
    game = Game(data_dir=data_dir)
    assert len(game.dialogs) == 1
    assert not game.dialogs.find("scriptflags")


def test_dialog_index_is_lazy(data_dir):
    game = Game(data_dir=data_dir)
    index = game.dialogs
    assert len(index) == 1
    assert DIALOG_PATH in index
    assert index.paths == [DIALOG_PATH]
    assert index._cache == {}          # nothing parsed yet

    dialog = index.load(DIALOG_PATH)
    assert dialog.category == "Camp"
    assert index.load(DIALOG_PATH) is dialog  # cached

    assert index.find("camp_greeting") == [DIALOG_PATH]
    assert index.find("nonexistent") == []
    assert index.get("nope.lsf") is None
    with pytest.raises(KeyError):
        index.load("nope.lsf")


def test_dialog_lines_resolve_localization(data_dir):
    game = Game(data_dir=data_dir)
    assert game.dialogs.lines(DIALOG_PATH) == [
        (0, "Well met, traveler."),
        (1, "And to you."),
    ]


TIMELINE_PATH = "Public/Shared/Timeline/Generated/tttt0000-0000-0000-0000-000000000001.lsf"


def test_timeline_index_and_dialog_linkage(data_dir):
    game = Game(data_dir=data_dir)
    assert len(game.timelines) == 1
    assert TIMELINE_PATH in game.timelines
    assert game.timelines._cache == {}          # listing didn't parse anything

    dialog = game.dialogs.load(DIALOG_PATH)
    assert game.timelines.for_dialog(dialog) == [TIMELINE_PATH]

    document = game.timelines.load(TIMELINE_PATH)
    assert document.region("TimelineContent") is not None

    # a dialog with no timeline id links to nothing
    dialog.timeline_id = None
    assert game.timelines.for_dialog(dialog) == []


def test_search_cli(data_dir, capsys):
    from bg3forge.cli.main import main

    assert main(["--data-dir", str(data_dir), "search", "dialogsbinary"]) == 0
    out = capsys.readouterr().out
    assert "CAMP_Greeting.lsf" in out
    assert "1 match(es)" in out

    assert main(["--data-dir", str(data_dir), "search", "nothing-matches-this"]) == 0
    assert "0 match(es)" in capsys.readouterr().out

    assert main(["--data-dir", str(data_dir), "search", "Shared", "--limit", "2"]) == 0
    assert "first 2 shown" in capsys.readouterr().out


def test_search_cli_glob_and_dirs(data_dir, capsys):
    from bg3forge.cli.main import main

    # glob: anchored pattern instead of substring
    assert main(["--data-dir", str(data_dir), "search", "*/stats/generated/data/*.txt"]) == 0
    out = capsys.readouterr().out
    assert "Weapon.txt" in out and "6 match(es)" in out

    # --dirs: aggregate by directory with counts
    assert main(["--data-dir", str(data_dir), "search", ".txt", "--dirs"]) == 0
    out = capsys.readouterr().out
    assert "      6  Public/Shared/Stats/Generated/Data" in out
    assert "9 match(es) in 3 directorie(s)" in out


def test_dialog_index_from_extracted(tmp_path, sample_pak):
    from bg3forge.pak import Extractor

    out = tmp_path / "extracted"
    Extractor(out).extract(sample_pak)
    game = Game(extracted_dir=out)
    assert len(game.dialogs) == 1
    assert game.dialogs.load(DIALOG_PATH).uuid.startswith("dddd0000")
