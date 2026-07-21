"""Compiled Osiris story metadata tests."""

import pytest

from bg3forge import Game
from bg3forge.parsers.osiris import FunctionType, OsirisError, parse_osiris
from conftest import make_story_osi


def test_parse_compiled_story_metadata():
    story = parse_osiris(make_story_osi(), source="story.div.osi")

    assert story.header.version == "1.15"
    assert story.header.version_string == "Osiris save file"
    assert story.header.debug_flags == 0x1234
    assert story.node_count == 2
    assert story.rule_count == 1
    assert story.enum_count == 0
    assert story.adapter_count == 0
    assert story.global_action_count == 1

    assert story.type_name(6) == "CHARACTER"
    assert [(function.name, function.kind) for function in story.functions] == [
        ("DB_Players", FunctionType.DATABASE),
        ("PlayerJoined", FunctionType.EVENT),
    ]
    assert story.signature(story.functions[0].parameter_types) == ("CHARACTER",)

    database = story.databases[0]
    assert database.name == "DB_Players"
    assert database.parameter_types == (6,)
    assert database.fact_count == 1

    goal = story.goals[0]
    assert goal.name == "Act1_DEN_AdventurersQuest"
    assert goal.init_call_count == 1
    assert goal.exit_call_count == 0
    assert goal.rule_count == 1
    assert story.goal_names == {"Act1_DEN_AdventurersQuest"}


@pytest.mark.parametrize("cut", [0, 1, 140, -1])
def test_truncated_story_is_rejected(cut):
    data = make_story_osi()
    truncated = data[:cut] if cut >= 0 else data[:cut]
    with pytest.raises(OsirisError, match="truncated"):
        parse_osiris(truncated, source="broken.osi")


def test_unsupported_story_version_is_rejected():
    data = bytearray(make_story_osi())
    # Header: marker + zero-terminated "Osiris save file", then major/minor.
    minor_offset = 1 + len("Osiris save file") + 1 + 1
    data[minor_offset] = 13
    with pytest.raises(OsirisError, match="unsupported Osiris version 1.13"):
        parse_osiris(bytes(data))


def test_trailing_bytes_are_rejected():
    with pytest.raises(OsirisError, match="trailing bytes"):
        parse_osiris(make_story_osi() + b"extra")


def test_game_story_index_is_lazy_and_cross_checks_goals(data_dir):
    game = Game(data_dir=data_dir)
    assert len(game.story) == 1
    assert game.story._cache == {}

    path = game.story.paths[0]
    story = game.story.load(path)
    assert story.goals[0].name == "Act1_DEN_AdventurersQuest"
    assert game.story.load(path) is story
    assert game.uncompiled_goals() == []
