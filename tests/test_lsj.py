"""Tests for the LSJ (JSON) resource parser."""

import pytest

from bg3forge.parsers import is_lsj, parse_dialog, parse_lsj, parse_lsx, parse_resource
from bg3forge.parsers.lsj import LsjError
from conftest import DIALOG_LSJ, DIALOG_LSX

from test_lsf import _assert_documents_equal


def test_lsj_matches_lsx_form():
    """The LSJ and LSX serializations of the same dialog parse into
    structurally identical documents."""
    _assert_documents_equal(parse_lsx(DIALOG_LSX), parse_lsj(DIALOG_LSJ.encode()))


def test_lsj_dialog_end_to_end():
    dialog = parse_dialog(parse_lsj(DIALOG_LSJ.encode()), source="CAMP_Greeting.lsj")
    assert dialog.uuid == "dddd0000-0000-0000-0000-000000000001"
    assert dialog.timeline_id == "tttt0000-0000-0000-0000-000000000001"
    assert [s.index for s in dialog.speakers] == [0, 1]
    assert [n.uuid for n in dialog.walk()] == ["n0000001", "n0000002"]
    greeting = dialog.node("n0000001")
    assert greeting.is_root
    assert greeting.text_handles == [("h99990000-9999-9999-9999-999999999901", 1)]


def test_lsj_value_rendering():
    document = parse_lsj(
        b'{"save": {"regions": {"R": {'
        b'"Flag": {"type": "bool", "value": true},'
        b'"Count": {"type": "int32", "value": 42},'
        b'"Ratio": {"type": "float", "value": 0.5},'
        b'"Pos": {"type": "fvec3", "value": [1.5, -2.5, 0.25]},'
        b'"NumericType": {"type": "22", "value": "FixedStr"},'
        b'"IntType": {"type": 23, "value": "LSStr"}'
        b"}}}}"
    )
    node = document.regions["R"]
    assert node.attributes["Flag"].value == "True"
    assert node.attributes["Count"].value == "42"
    assert node.attributes["Ratio"].value == "0.5"
    assert node.attributes["Pos"].value == "1.5 -2.5 0.25"
    assert node.attributes["NumericType"].type == "FixedString"  # numeric string id
    assert node.attributes["IntType"].type == "LSString"          # numeric id


def test_lsj_sniffing():
    assert is_lsj(b'  {"save": {}}')
    assert not is_lsj(b"LSOF....")
    assert not is_lsj(b"<save/>")
    document = parse_resource(DIALOG_LSJ.encode())
    assert "dialog" in document.regions


def test_lsj_rejects_garbage():
    with pytest.raises(LsjError, match="malformed"):
        parse_lsj(b"{not json")
    with pytest.raises(LsjError, match="save"):
        parse_lsj(b'{"other": 1}')
