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


def test_dialog_index_from_extracted(tmp_path, sample_pak):
    from bg3forge.pak import Extractor

    out = tmp_path / "extracted"
    Extractor(out).extract(sample_pak)
    game = Game(extracted_dir=out)
    assert len(game.dialogs) == 1
    assert game.dialogs.load(DIALOG_PATH).uuid.startswith("dddd0000")
