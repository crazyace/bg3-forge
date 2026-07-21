"""Parser for quest journal prototypes and markers.

``Mods/<Mod>/Story/Journal/quest_prototypes.lsx`` holds the quest
catalog (region ``Quests``)::

    <node id="Quest">
      <attribute id="QuestID" type="FixedString" value="PLA_ZhentShipment"/>
      <attribute id="QuestGuid" type="guid" value="..."/>
      <attribute id="CategoryID" type="FixedString" value="Crashside"/>
      <attribute id="QuestTitle" type="TranslatedString" handle="h..."/>
      <children>
        <node id="QuestStep">
          <attribute id="ID" type="FixedString" value="AgreedHelp"/>
          <attribute id="Description" type="TranslatedString" handle="h..."/>
          <attribute id="Objective" type="FixedString" value="..."/>
          ...

``Story/Journal/Markers/<uuid>.lsx`` files each hold one map marker
(region ``Markers``) tying a quest moment to a level and target object.

Handles equal to Larian's ``ls::TranslatedStringRepository::s_HandleUnknown``
sentinel are normalized to ``None``.  Localization joins are the
caller's job (:class:`bg3forge.game.Game` does it).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lsx import LsxDocument, LsxNode

_UNKNOWN_HANDLE = "ls::TranslatedStringRepository::s_HandleUnknown"


def _handle(node: LsxNode, attribute_id: str) -> str | None:
    value = node.get(attribute_id)
    if not value or value == _UNKNOWN_HANDLE:
        return None
    return value


@dataclass
class QuestStep:
    id: str
    guid: str | None = None
    description_handle: str | None = None
    description: str = ""              # localized, filled by Game
    dev_comment: str | None = None
    objective: str | None = None       # objective_prototypes reference
    achievement: str | None = None
    treasure_table: str | None = None  # RewardAdditionalTreasureTable
    experience_reward: str | None = None
    dialog_flag_guid: str | None = None


@dataclass
class Quest:
    quest_id: str                      # e.g. "PLA_ZhentShipment"
    guid: str | None = None
    category_id: str | None = None
    parent_quest_id: str | None = None
    title_handle: str | None = None
    title: str = ""                    # localized, filled by Game
    visible: bool = True
    sorting_priority: int = 0
    steps: list[QuestStep] = field(default_factory=list)
    source: str | None = None

    # NamedCollection compatibility
    @property
    def name(self) -> str:
        return self.quest_id

    @property
    def display_name(self) -> str:
        return self.title

    def _link(self, game) -> None:
        self._game = game

    @property
    def goals(self) -> list[str]:
        """Osiris goal script paths whose logic references this quest."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.goals_for_quest(self.quest_id)

    @property
    def category(self) -> "QuestCategory | None":
        game = getattr(self, "_game", None)
        if game is None or not self.category_id:
            return None
        return game.quest_categories.get(self.category_id)

    @property
    def objectives(self) -> list["Objective"]:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.objectives_for_quest(self.quest_id)


@dataclass
class Marker:
    guid: str
    marker_id: str = ""
    icon: str | None = None
    level: str | None = None           # e.g. "SCL_Main_A"
    target_type: str | None = None     # e.g. "Trigger"
    target_uuid: str | None = None
    radius: int = 0
    display_text_handle: str | None = None
    display_text: str = ""             # localized, filled by Game


@dataclass
class Objective:
    """One entry from ``objective_prototypes.lsx`` (region ``Objectives``)."""

    objective_id: str                  # e.g. "FOR_UnfortunateGnome_Approach"
    quest_id: str | None = None
    guid: str | None = None
    priority: int = 0
    description_handle: str | None = None
    description: str = ""              # localized, filled by Game
    marker_ids: list[str] = field(default_factory=list)
    source: str | None = None

    # NamedCollection compatibility
    @property
    def name(self) -> str:
        return self.objective_id

    @property
    def display_name(self) -> str:
        return self.description

    def _link(self, game) -> None:
        self._game = game

    @property
    def quest(self):
        game = getattr(self, "_game", None)
        if game is None or not self.quest_id:
            return None
        return game.quests.get(self.quest_id)

    @property
    def markers(self) -> list[Marker]:
        """The map markers this objective points at (matched by MarkerID)."""
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return [
            marker
            for marker_id in self.marker_ids
            for marker in game.markers_by_id(marker_id)
        ]


@dataclass
class QuestCategory:
    """One entry from ``questcategory_prototypes.lsx``.

    The ``Description`` handle holds the category's display name (the
    journal section header, e.g. "Companions").
    """

    category_id: str
    guid: str | None = None
    sorting_priority: int = 0
    description_handle: str | None = None
    description: str = ""              # localized, filled by Game
    source: str | None = None

    # NamedCollection compatibility
    @property
    def name(self) -> str:
        return self.category_id

    @property
    def display_name(self) -> str:
        return self.description

    def _link(self, game) -> None:
        self._game = game

    @property
    def quests(self) -> list[Quest]:
        game = getattr(self, "_game", None)
        if game is None:
            return []
        return game.quests_in_category(self.category_id)


def parse_objectives(document: LsxDocument, source: str | None = None) -> list[Objective]:
    objectives = []
    for node in document.find_all("Objective"):
        objective_id = node.get("ObjectiveID")
        if not objective_id:
            continue
        marker_ids = [
            value
            for markers_node in node.find_all("Markers")
            if (value := markers_node.get("Markers"))
        ]
        objectives.append(
            Objective(
                objective_id=objective_id,
                quest_id=node.get("QuestID") or None,
                guid=node.get("QuestObjectiveGuid"),
                priority=int(node.get("Priority", "0") or 0),
                description_handle=_handle(node, "Description"),
                marker_ids=marker_ids,
                source=source,
            )
        )
    return objectives


def parse_quest_categories(
    document: LsxDocument, source: str | None = None
) -> list[QuestCategory]:
    categories = []
    for node in document.find_all("QuestCategory"):
        category_id = node.get("CategoryID")
        if not category_id:
            continue
        categories.append(
            QuestCategory(
                category_id=category_id,
                guid=node.get("QuestCategoryGuid"),
                sorting_priority=int(node.get("SortingPriority", "0") or 0),
                description_handle=_handle(node, "Description"),
                source=source,
            )
        )
    return categories


def parse_quests(document: LsxDocument, source: str | None = None) -> list[Quest]:
    quests = []
    for node in document.find_all("Quest"):
        quest_id = node.get("QuestID")
        if not quest_id:
            continue
        steps = [
            QuestStep(
                id=step.get("ID", "") or "",
                guid=step.get("QuestStepGuid"),
                description_handle=_handle(step, "Description"),
                dev_comment=step.get("DevComment") or None,
                objective=step.get("Objective") or None,
                achievement=step.get("Achievement") or None,
                treasure_table=step.get("RewardAdditionalTreasureTable") or None,
                experience_reward=_nonzero_guid(step.get("ExperienceReward")),
                dialog_flag_guid=_nonzero_guid(step.get("DialogFlagGUID")),
            )
            for step in node.find_all("QuestStep")
        ]
        quests.append(
            Quest(
                quest_id=quest_id,
                guid=node.get("QuestGuid"),
                category_id=node.get("CategoryID") or None,
                parent_quest_id=node.get("ParentQuestID") or None,
                title_handle=_handle(node, "QuestTitle"),
                # sic: the game data spells it "QuestVisiblity"
                visible=(node.get("QuestVisiblity", "True") or "True").lower()
                in ("true", "1"),
                sorting_priority=int(node.get("SortingPriority", "0") or 0),
                steps=steps,
                source=source,
            )
        )
    return quests


def parse_markers(document: LsxDocument, source: str | None = None) -> list[Marker]:
    markers = []
    for node in document.find_all("Marker"):
        guid = node.get("Guid")
        if not guid:
            continue
        markers.append(
            Marker(
                guid=guid,
                marker_id=node.get("MarkerID", "") or "",
                icon=node.get("MarkerIcon") or None,
                level=node.get("MarkerLevel") or None,
                target_type=node.get("MarkerTargetObjectType") or None,
                target_uuid=node.get("MarkerTargetObjectUUID") or None,
                radius=int(node.get("Radius", "0") or 0),
                display_text_handle=_handle(node, "DisplayText"),
            )
        )
    return markers


def _nonzero_guid(value: str | None) -> str | None:
    if not value or value == "00000000-0000-0000-0000-000000000000":
        return None
    return value
