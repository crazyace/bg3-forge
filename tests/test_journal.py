"""Tests for the quest journal layer and Osiris goal metadata."""

import pytest

from bg3forge import Game
from bg3forge.parsers import parse_goal, parse_lsx, parse_markers, parse_quests
from conftest import GOAL_TXT, MARKER_LSX, QUEST_PROTOTYPES_LSX


# -- parsers -----------------------------------------------------------------

def test_parse_quests():
    quests = parse_quests(parse_lsx(QUEST_PROTOTYPES_LSX), source="quest_prototypes.lsx")
    assert len(quests) == 1
    quest = quests[0]
    assert quest.quest_id == "PLA_ZhentShipment"
    assert quest.guid == "56d7dfd6-affa-7fa3-e07e-9f8ee36ea03f"
    assert quest.category_id == "Crashside"
    assert quest.parent_quest_id is None          # empty string normalized
    assert quest.title_handle == "haaaa0000-0000-0000-0000-0000000000q1"
    assert quest.visible is True
    assert quest.sorting_priority == 6

    assert [s.id for s in quest.steps] == ["AgreedHelp", "NoticedStruggle_Hideout"]
    first, second = quest.steps
    assert first.objective == "PLA_ZhentShipment_AgreedHelp"
    assert first.dev_comment == "Agreed to help Hideout Zhent first"
    assert first.dialog_flag_guid == "719e7abb-dac9-41e7-912b-78eeeec43e68"
    assert first.experience_reward == "85e62526-1d6d-4efb-8897-c602e530e7bf"
    assert first.treasure_table is None            # empty string normalized
    assert second.experience_reward is None        # zero guid normalized


def test_parse_markers():
    markers = parse_markers(parse_lsx(MARKER_LSX))
    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_id == "SHA_ShadowfellPortal"
    assert marker.icon == "QuestMarker"
    assert marker.level == "SCL_Main_A"
    assert marker.target_type == "Trigger"
    assert marker.target_uuid == "8f3c363b-b497-4318-ae1d-f5dd20d034bb"


def test_parse_goal():
    goal = parse_goal(GOAL_TXT, source="Mods/.../Act1_DEN_AdventurersQuest.txt")
    assert goal.name == "Act1_DEN_AdventurersQuest"
    assert goal.version == "1"
    assert goal.combiner == "SGC_AND"
    assert goal.sections == ["INITSECTION", "KBSECTION", "EXITSECTION", "ENDSECTION"]
    assert goal.init_facts == 2
    assert goal.rules == 2
    assert set(goal.quest_ids) == {"SHA_Nightsong", "PLA_ZhentShipment"}
    # step references collected per quest
    assert "SolvedPuzzle" in goal.quest_refs["SHA_Nightsong"]
    assert "RefinedLocation" in goal.quest_refs["SHA_Nightsong"]
    assert goal.quest_refs["PLA_ZhentShipment"] == ["AgreedHelp"]


# -- Game integration --------------------------------------------------------

@pytest.fixture
def game(data_dir):
    return Game(data_dir=data_dir)


def test_quests_localized(game):
    quest = game.quests["PLA_ZhentShipment"]
    assert quest.title == "The Zhentarim Shipment"
    assert quest.steps[0].description == "We agreed to recover the shipment."
    assert game.quests.find("zhentarim")[0] is quest   # display-name search


def test_quest_markers_localized(game):
    assert len(game.quest_markers) == 1
    assert game.quest_markers[0].display_text == "Shadowfell Portal"


def test_goals_index_lazy(game):
    assert len(game.goals) == 1
    path = game.goals.paths[0]
    assert game.goals._cache == {}
    goal = game.goals.load(path)
    assert goal.name == "Act1_DEN_AdventurersQuest"


def test_read_entry_reuses_pak_readers(data_dir, monkeypatch):
    """Loading many indexed resources must not reopen the pak each time
    (regression: quest.goals reopened Gustav.pak per goal script)."""
    import bg3forge.game as game_module

    opens = []
    real_reader = game_module.PakReader

    class CountingReader(real_reader):
        def __init__(self, path):
            opens.append(str(path))
            super().__init__(path)

    monkeypatch.setattr(game_module, "PakReader", CountingReader)
    with Game(data_dir=data_dir) as game:
        game.dialogs.load(game.dialogs.paths[0])
        game.goals.load(game.goals.paths[0])
        game.timelines.load(game.timelines.paths[0])
        game.items, game.quests  # collection loads share the same readers
        read_opens = len(opens)
    game.close()  # idempotent
    # ONE reader for the fixture's single pak, shared by every index
    # build, collection load, and entry read (retail benchmark showed
    # ~2.3 s of file-list parsing repeated per stage before this).
    assert read_opens == 1


def test_quest_to_goal_cross_link(game):
    quest = game.quests["PLA_ZhentShipment"]
    assert quest.goals == [
        "Mods/Shared/Story/RawFiles/Goals/Act1_DEN_AdventurersQuest.txt"
    ]
    assert game.goals_for_quest("SHA_Nightsong") == quest.goals  # same file
    assert game.goals_for_quest("UNKNOWN_QUEST") == []
