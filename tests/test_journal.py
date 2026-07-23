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


def test_parse_goal_ignores_block_and_trailing_comments():
    """Retail goal sources use /* */ block comments and trailing //
    comments; counting them or harvesting quest refs from them corrupts
    the metadata."""
    goal = parse_goal(
        "Version 1\n"
        "KBSECTION\n"
        "IF\n"
        'DB_QuestIsAccepted("REAL_Quest") // active rule\n'
        "THEN\n"
        'QuestUpdate(_Char, "REAL_Quest", "Step1");\n'
        "/*\n"
        "IF\n"
        'DB_QuestIsAccepted("COMMENTED_Quest")\n'
        "THEN\n"
        'QuestUpdate(_Char, "COMMENTED_Quest", "Ghost");\n'
        "*/\n"
        'DB_Fact("kept"); // DB_QuestIsAccepted("AlsoCommented")\n'
    )
    assert goal.rules == 1                       # not 2 — the block IF is gone
    assert set(goal.quest_ids) == {"REAL_Quest"}  # commented quests excluded
    assert "COMMENTED_Quest" not in goal.quest_refs
    assert "AlsoCommented" not in goal.quest_refs


def test_parse_objectives():
    from bg3forge.parsers import parse_objectives
    from conftest import OBJECTIVE_LSX

    objectives = parse_objectives(parse_lsx(OBJECTIVE_LSX), source="objective_prototypes.lsx")
    assert [o.objective_id for o in objectives] == [
        "PLA_ZhentShipment_AgreedHelp",
        "PLA_ZhentShipment_HelpSurvivors",
    ]
    first = objectives[0]
    assert first.quest_id == "PLA_ZhentShipment"
    assert first.priority == 1000
    assert first.marker_ids == ["SHA_ShadowfellPortal"]
    assert objectives[1].marker_ids == []


def test_parse_quest_categories():
    from bg3forge.parsers import parse_quest_categories
    from conftest import CATEGORY_LSX

    categories = parse_quest_categories(parse_lsx(CATEGORY_LSX))
    assert len(categories) == 1
    assert categories[0].category_id == "Crashside"
    assert categories[0].sorting_priority == 2


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


def test_objectives_localized_and_linked(game):
    objective = game.objectives["PLA_ZhentShipment_AgreedHelp"]
    assert objective.description == "Recover the shipment."
    assert objective.quest is game.quests["PLA_ZhentShipment"]
    # objective → marker join by MarkerID
    assert [m.display_text for m in objective.markers] == ["Shadowfell Portal"]
    assert game.objectives["PLA_ZhentShipment_HelpSurvivors"].markers == []


def test_quest_category_and_objectives(game):
    quest = game.quests["PLA_ZhentShipment"]
    assert quest.category is game.quest_categories["Crashside"]
    assert quest.category.display_name == "Wilderness"
    assert [o.objective_id for o in quest.objectives] == [
        "PLA_ZhentShipment_AgreedHelp",
        "PLA_ZhentShipment_HelpSurvivors",
    ]
    # reverse: category → quests
    assert game.quest_categories["Crashside"].quests == [quest]
    assert game.quests_in_category("Nope") == []


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
