"""Shared fixtures: a synthetic mini-BG3 data set packed into a real .pak."""

from __future__ import annotations

import struct

import pytest

from bg3forge.pak.writer import PakWriter
from bg3forge.parsers.localization import LocaEntry, write_loca

WEAPON_TXT = """\
new entry "_BaseWeapon"
type "Weapon"
data "ValueOverride" "10"
data "Weight" "1.0"
data "Rarity" "Common"

new entry "WPN_Longsword"
type "Weapon"
using "_BaseWeapon"
data "Damage" "1d8"
data "Damage Type" "Slashing"
data "RootTemplate" "1111aaaa-0000-0000-0000-000000000001"
data "Icon" "Item_WPN_Longsword"
data "Requirements" "Str 13"

new entry "WPN_Longsword_Magic"
type "Weapon"
using "WPN_Longsword"
data "Rarity" "Rare"
data "ValueOverride" "500"
data "PassivesOnEquip" "SavageAttacks"
data "StatusOnEquip" "BURNING"
data "Boosts" "UnlockSpell(Projectile_Fireball);WeaponEnchantment(1)"
"""

CHARACTER_TXT = """\
new entry "_BaseCharacter"
type "Character"
data "Strength" "10"
data "Dexterity" "10"
data "Constitution" "10"
data "Intelligence" "10"
data "Wisdom" "10"
data "Charisma" "10"
data "Vitality" "6"
data "Armor" "10"

new entry "GOB_Warrior"
type "Character"
using "_BaseCharacter"
data "Level" "3"
data "Vitality" "21"
data "Armor" "15"
data "Strength" "16"
data "Passives" "SavageAttacks"
"""

EQUIPMENT_TXT = """\
new equipment "EQP_Goblin_Warrior"
add initialweaponset "Melee"
add equipmentgroup
add equipment entry "WPN_Longsword"
add equipmentgroup
add equipment entry "ARM_Missing_Leather"
"""

SPELL_TXT = """\
// Fireball and friends
new entry "Projectile_Fireball"
type "SpellData"
data "SpellType" "Projectile"
data "Level" "3"
data "SpellSchool" "Evocation"
data "Damage" "8d6"
data "DisplayName" "h11111111-1111-1111-1111-111111111111;1"
data "Description" "h22222222-2222-2222-2222-222222222222;1"
data "Icon" "Spell_Evocation_Fireball"
data "UseCosts" "ActionPoint:1;SpellSlotsGroup:1:1:3"
"""

PASSIVE_TXT = """\
new entry "SavageAttacks"
type "PassiveData"
data "DisplayName" "h33333333-3333-3333-3333-333333333333;1"
data "Properties" "Highlighted"
data "Boosts" "RerollDamageDice()"
"""

STATUS_TXT = """\
new entry "BURNING"
type "StatusData"
data "StatusType" "BOOST"
data "DisplayName" "h44444444-4444-4444-4444-444444444444;1"
data "StackId" "BURNING"
data "Boosts" "DamageTakenBonus(1,Fire)"
"""

# Mirrors retail Data.txt / PhotoMode Data.txt: top-level key globals,
# comma-separated args, no entries.
DATA_TXT = """\
key "ProficiencyBonusBase","2"
key "CriticalHitMultiplier","2"
"""

TREASURE_TXT = """\
new treasuretable "TUT_Chest"
CanMerge 1
new subtable "1,1"
object category "I_WPN_Longsword",1,0,0,0,0,0,0,0
object category "T_EmptyChest",3,0,0,0,0,0,0,0
"""

PROGRESSION_LSX = """\
<save>
  <region id="Progressions">
    <node id="root">
      <children>
        <node id="Progression">
          <attribute id="UUID" type="guid" value="aaaaaaaa-0000-0000-0000-000000000001" />
          <attribute id="Name" type="LSString" value="Wizard" />
          <attribute id="TableUUID" type="guid" value="bbbbbbbb-0000-0000-0000-000000000001" />
          <attribute id="Level" type="uint8" value="1" />
          <attribute id="ProgressionType" type="uint8" value="0" />
          <attribute id="PassivesAdded" type="LSString" value="SavageAttacks" />
          <attribute id="Selectors" type="LSString" value="AddSpells(cccccccc-0000-0000-0000-000000000001,,,,AlwaysPrepared);SelectSpells(cccccccc-0000-0000-0000-000000000002,1,0)" />
          <children>
            <node id="SubClasses">
              <children>
                <node id="SubClass">
                  <attribute id="Object" type="guid" value="dddddddd-0000-0000-0000-000000000001" />
                </node>
              </children>
            </node>
          </children>
        </node>
        <node id="Progression">
          <attribute id="UUID" type="guid" value="aaaaaaaa-0000-0000-0000-000000000002" />
          <attribute id="Name" type="LSString" value="Wizard" />
          <attribute id="TableUUID" type="guid" value="bbbbbbbb-0000-0000-0000-000000000001" />
          <attribute id="Level" type="uint8" value="2" />
          <attribute id="ProgressionType" type="uint8" value="0" />
          <attribute id="PassivesRemoved" type="LSString" value="SavageAttacks" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

SPELL_LISTS_LSX = """\
<save>
  <region id="SpellLists">
    <node id="root">
      <children>
        <node id="SpellList">
          <attribute id="UUID" type="guid" value="cccccccc-0000-0000-0000-000000000001" />
          <attribute id="Comment" type="LSString" value="Automatic wizard spells" />
          <attribute id="Spells" type="LSString" value="Projectile_Fireball" />
        </node>
        <node id="SpellList">
          <attribute id="UUID" type="guid" value="cccccccc-0000-0000-0000-000000000002" />
          <attribute id="Comment" type="LSString" value="Wizard choices" />
          <attribute id="Spells" type="LSString" value="Projectile_Fireball" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

ROOTTEMPLATE_LSX = """\
<?xml version="1.0" encoding="utf-8"?>
<save>
  <version major="4" minor="0" revision="9" build="330" />
  <region id="Templates">
    <node id="Templates">
      <children>
        <node id="GameObjects">
          <attribute id="MapKey" type="FixedString" value="0000base-0000-0000-0000-00000000000f" />
          <attribute id="Name" type="LSString" value="BASE_Weapon" />
          <attribute id="Icon" type="FixedString" value="Item_Generic" />
          <children>
            <node id="Tags">
              <children>
                <node id="Tag">
                  <attribute id="Object" type="guid" value="aaaa1111-0000-0000-0000-000000000001" />
                </node>
              </children>
            </node>
          </children>
        </node>
        <node id="GameObjects">
          <attribute id="MapKey" type="FixedString" value="2222bbbb-0000-0000-0000-000000000002" />
          <attribute id="Name" type="LSString" value="GOB_Warrior" />
          <attribute id="Stats" type="FixedString" value="GOB_Warrior" />
          <attribute id="DisplayName" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000c1" version="1" />
          <attribute id="Equipment" type="FixedString" value="EQP_Goblin_Warrior" />
          <attribute id="Archetype" type="FixedString" value="melee" />
        </node>
        <node id="GameObjects">
          <attribute id="MapKey" type="FixedString" value="1111aaaa-0000-0000-0000-000000000001" />
          <attribute id="Name" type="LSString" value="WPN_Longsword" />
          <attribute id="ParentTemplateId" type="FixedString" value="0000base-0000-0000-0000-00000000000f" />
          <attribute id="DisplayName" type="TranslatedString" handle="h55555555-5555-5555-5555-555555555555" version="1" />
          <attribute id="Description" type="TranslatedString" handle="h66666666-6666-6666-6666-666666666666" version="1" />
          <attribute id="Stats" type="FixedString" value="WPN_Longsword" />
          <children>
            <node id="Tags">
              <children>
                <node id="Tag">
                  <attribute id="Object" type="guid" value="bbbb2222-0000-0000-0000-000000000002" />
                </node>
              </children>
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""

GLOBAL_ITEMS_LSX = """\
<?xml version="1.0" encoding="utf-8"?>
<save>
  <version major="4" minor="0" revision="9" build="330" />
  <region id="Templates">
    <node id="Templates">
      <children>
        <node id="GameObjects">
          <attribute id="MapKey" type="FixedString" value="3333cccc-0000-0000-0000-000000000003" />
          <attribute id="Name" type="LSString" value="S_WLD_PlacedLongsword" />
          <attribute id="TemplateName" type="FixedString" value="1111aaaa-0000-0000-0000-000000000001" />
          <attribute id="LevelName" type="FixedString" value="WLD_Main_A" />
          <attribute id="Type" type="FixedString" value="item" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

LEVEL_ITEMS_LSX = """\
<?xml version="1.0" encoding="utf-8"?>
<save>
  <version major="4" minor="0" revision="9" build="330" />
  <region id="Templates">
    <node id="Templates">
      <children>
        <node id="GameObjects">
          <attribute id="MapKey" type="FixedString" value="4444dddd-0000-0000-0000-000000000004" />
          <attribute id="Name" type="LSString" value="S_WLD_LevelLongsword" />
          <attribute id="TemplateName" type="FixedString" value="1111aaaa-0000-0000-0000-000000000001" />
          <attribute id="DisplayName" type="TranslatedString" handle="h11111111-1111-1111-1111-111111111111" version="1" />
          <attribute id="LevelName" type="FixedString" value="WLD_Main_A" />
          <attribute id="Type" type="FixedString" value="item" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

def _tag_lsx(uuid, name, display_handle=None, category=None):
    display = (
        f'<attribute id="DisplayName" type="TranslatedString" handle="{display_handle}" version="1" />'
        if display_handle
        else ""
    )
    categories = (
        f'<children><node id="Categories"><children><node id="Category">'
        f'<attribute id="Name" type="LSString" value="{category}" />'
        f"</node></children></node></children>"
        if category
        else ""
    )
    return f"""\
<save>
  <region id="Tags">
    <node id="Tags">
      <attribute id="UUID" type="guid" value="{uuid}" />
      <attribute id="Name" type="FixedString" value="{name}" />
      <attribute id="Description" type="LSString" value="{name} tag" />
      {display}
      {categories}
    </node>
  </region>
</save>
"""


WEAPON_TAG_LSX = _tag_lsx(
    "aaaa1111-0000-0000-0000-000000000001",
    "WEAPON",
    display_handle="h77777777-7777-7777-7777-777777777777",
    category="Item",
)
LONGSWORD_TAG_LSX = _tag_lsx(
    "bbbb2222-0000-0000-0000-000000000002",
    "LONGSWORD",
)

ATLAS_LSX = """\
<?xml version="1.0" encoding="utf-8"?>
<save>
  <version major="4" minor="0" revision="9" build="330" />
  <region id="TextureAtlasInfo">
    <node id="TextureAtlasInfo">
      <children>
        <node id="TextureAtlasIconSize">
          <attribute id="Height" type="int32" value="64" />
          <attribute id="Width" type="int32" value="64" />
        </node>
        <node id="TextureAtlasPath">
          <attribute id="Path" type="LSString" value="Assets/Textures/Icons/Icons_Items.dds" />
        </node>
        <node id="TextureAtlasTextureSize">
          <attribute id="Height" type="int32" value="128" />
          <attribute id="Width" type="int32" value="128" />
        </node>
      </children>
    </node>
  </region>
  <region id="IconUVList">
    <node id="root">
      <children>
        <node id="IconUV">
          <attribute id="MapKey" type="FixedString" value="Item_WPN_Longsword" />
          <attribute id="U1" type="float" value="0" />
          <attribute id="U2" type="float" value="0.5" />
          <attribute id="V1" type="float" value="0" />
          <attribute id="V2" type="float" value="0.5" />
        </node>
        <node id="IconUV">
          <attribute id="MapKey" type="FixedString" value="Spell_Evocation_Fireball" />
          <attribute id="U1" type="float" value="0.5" />
          <attribute id="U2" type="float" value="1" />
          <attribute id="V1" type="float" value="0" />
          <attribute id="V2" type="float" value="0.5" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

DIALOG_LSX = """\
<save>
  <region id="dialog">
    <node id="dialog">
      <attribute id="UUID" type="FixedString" value="dddd0000-0000-0000-0000-000000000001" />
      <attribute id="category" type="LSString" value="Camp" />
      <attribute id="TimelineId" type="FixedString" value="tttt0000-0000-0000-0000-000000000001" />
      <children>
        <node id="speakerlist">
          <children>
            <node id="speaker">
              <attribute id="index" type="FixedString" value="0" />
              <attribute id="SpeakerMappingId" type="guid" value="5e2222aa-0000-0000-0000-00000000aa01" />
            </node>
            <node id="speaker">
              <attribute id="index" type="FixedString" value="1" />
              <attribute id="SpeakerMappingId" type="guid" value="5e2222aa-0000-0000-0000-00000000aa02" />
            </node>
          </children>
        </node>
        <node id="nodes">
          <children>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="n0000001" />
              <attribute id="constructor" type="FixedString" value="TagGreeting" />
              <attribute id="speaker" type="int32" value="0" />
              <attribute id="Root" type="bool" value="True" />
              <children>
                <node id="TaggedTexts">
                  <children>
                    <node id="TaggedText">
                      <children>
                        <node id="TagTexts">
                          <children>
                            <node id="TagText">
                              <attribute id="TagText" type="TranslatedString" handle="h99990000-9999-9999-9999-999999999901" version="1" />
                            </node>
                          </children>
                        </node>
                      </children>
                    </node>
                  </children>
                </node>
                <node id="children">
                  <children>
                    <node id="child">
                      <attribute id="UUID" type="FixedString" value="n0000002" />
                    </node>
                  </children>
                </node>
              </children>
            </node>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="n0000002" />
              <attribute id="constructor" type="FixedString" value="TagAnswer" />
              <attribute id="speaker" type="int32" value="1" />
              <attribute id="endnode" type="bool" value="True" />
              <children>
                <node id="TaggedTexts">
                  <children>
                    <node id="TaggedText">
                      <children>
                        <node id="TagTexts">
                          <children>
                            <node id="TagText">
                              <attribute id="TagText" type="TranslatedString" handle="h99990000-9999-9999-9999-999999999902" version="1" />
                            </node>
                          </children>
                        </node>
                      </children>
                    </node>
                  </children>
                </node>
              </children>
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""

# The same greeting dialog in LSJ (JSON) form, as shipped under
# Story/Dialogs/ — hand-authored per LSLib's LSJ structure.
DIALOG_LSJ = """\
{
  "save": {
    "header": { "version": "4.0.9.330" },
    "regions": {
      "dialog": {
        "UUID": { "type": "FixedString", "value": "dddd0000-0000-0000-0000-000000000001" },
        "category": { "type": "LSString", "value": "Camp" },
        "TimelineId": { "type": "FixedString", "value": "tttt0000-0000-0000-0000-000000000001" },
        "speakerlist": [
          {
            "speaker": [
              { "index": { "type": "FixedString", "value": "0" },
                "SpeakerMappingId": { "type": "guid", "value": "5e2222aa-0000-0000-0000-00000000aa01" } },
              { "index": { "type": "FixedString", "value": "1" },
                "SpeakerMappingId": { "type": "guid", "value": "5e2222aa-0000-0000-0000-00000000aa02" } }
            ]
          }
        ],
        "nodes": [
          {
            "node": [
              {
                "UUID": { "type": "FixedString", "value": "n0000001" },
                "constructor": { "type": "FixedString", "value": "TagGreeting" },
                "speaker": { "type": "int32", "value": 0 },
                "Root": { "type": "bool", "value": true },
                "TaggedTexts": [
                  { "TaggedText": [
                      { "TagTexts": [
                          { "TagText": [
                              { "TagText": { "type": "TranslatedString",
                                             "handle": "h99990000-9999-9999-9999-999999999901",
                                             "version": 1 } }
                          ] }
                      ] }
                  ] }
                ],
                "children": [
                  { "child": [ { "UUID": { "type": "FixedString", "value": "n0000002" } } ] }
                ]
              },
              {
                "UUID": { "type": "FixedString", "value": "n0000002" },
                "constructor": { "type": "FixedString", "value": "TagAnswer" },
                "speaker": { "type": "int32", "value": 1 },
                "endnode": { "type": "bool", "value": true },
                "TaggedTexts": [
                  { "TaggedText": [
                      { "TagTexts": [
                          { "TagText": [
                              { "TagText": { "type": "TranslatedString",
                                             "handle": "h99990000-9999-9999-9999-999999999902",
                                             "version": 1 } }
                          ] }
                      ] }
                  ] }
                ]
              }
            ]
          }
        ]
      }
    }
  }
}
"""

# Minimal timeline (cinematic) resource; internals are unmodeled, only
# existence and dialog linkage matter.
TIMELINE_LSX = """\
<save>
  <region id="TimelineContent">
    <node id="TimelineContent">
      <attribute id="Duration" type="float" value="4.5" />
    </node>
  </region>
</save>
"""

# Trimmed from retail quest_prototypes.lsx (structure verbatim,
# including Larian's "QuestVisiblity" spelling and the unknown-handle
# sentinel).
QUEST_PROTOTYPES_LSX = """\
<?xml version="1.0" encoding="UTF-8"?>
<save>
  <version major="4" minor="7" revision="1" build="3"/>
  <region id="Quests">
    <node id="root">
      <children>
        <node id="Quest">
          <attribute id="CategoryID" type="FixedString" value="Crashside"/>
          <attribute id="ParentQuestID" type="FixedString" value=""/>
          <attribute id="QuestGuid" type="guid" value="56d7dfd6-affa-7fa3-e07e-9f8ee36ea03f"/>
          <attribute id="QuestID" type="FixedString" value="PLA_ZhentShipment"/>
          <attribute id="QuestTitle" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000q1" version="4"/>
          <attribute id="QuestVisiblity" type="bool" value="true"/>
          <attribute id="SortingPriority" type="int32" value="6"/>
          <children>
            <node id="QuestStep">
              <attribute id="Achievement" type="FixedString" value=""/>
              <attribute id="Description" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000q2" version="3"/>
              <attribute id="DevComment" type="FixedString" value="Agreed to help Hideout Zhent first"/>
              <attribute id="DialogFlagGUID" type="guid" value="719e7abb-dac9-41e7-912b-78eeeec43e68"/>
              <attribute id="ExperienceReward" type="guid" value="85e62526-1d6d-4efb-8897-c602e530e7bf"/>
              <attribute id="ID" type="FixedString" value="AgreedHelp"/>
              <attribute id="Objective" type="FixedString" value="PLA_ZhentShipment_AgreedHelp"/>
              <attribute id="QuestStepGuid" type="guid" value="01dbd8ae-fc4d-e2e4-ee92-b4da21215939"/>
              <attribute id="QuestTitleOverride" type="TranslatedString" handle="ls::TranslatedStringRepository::s_HandleUnknown" version="0"/>
              <attribute id="RewardAdditionalTreasureTable" type="FixedString" value=""/>
            </node>
            <node id="QuestStep">
              <attribute id="Description" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000q3" version="2"/>
              <attribute id="ExperienceReward" type="guid" value="00000000-0000-0000-0000-000000000000"/>
              <attribute id="ID" type="FixedString" value="NoticedStruggle_Hideout"/>
              <attribute id="Objective" type="FixedString" value="PLA_ZhentShipment_HelpSurvivors"/>
              <attribute id="QuestStepGuid" type="guid" value="351da90b-5850-a79f-bef9-302e3c346829"/>
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""

# Trimmed from a retail Markers/<uuid>.lsx.
MARKER_LSX = """\
<?xml version="1.0" encoding="UTF-8"?>
<save>
  <version major="4" minor="0" revision="9" build="302"/>
  <region id="Markers">
    <node id="root">
      <children>
        <node id="Marker">
          <attribute id="DisplayText" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000m1" version="1"/>
          <attribute id="Guid" type="guid" value="9d61b258-a858-7e39-39e6-a13a26c8cd8a"/>
          <attribute id="MarkerID" type="FixedString" value="SHA_ShadowfellPortal"/>
          <attribute id="MarkerIcon" type="FixedString" value="QuestMarker"/>
          <attribute id="MarkerLevel" type="FixedString" value="SCL_Main_A"/>
          <attribute id="MarkerTargetObjectType" type="FixedString" value="Trigger"/>
          <attribute id="MarkerTargetObjectUUID" type="FixedString" value="8f3c363b-b497-4318-ae1d-f5dd20d034bb"/>
          <attribute id="Radius" type="int32" value="0"/>
        </node>
      </children>
    </node>
  </region>
</save>
"""

# Trimmed from retail objective_prototypes.lsx.
OBJECTIVE_LSX = """\
<?xml version="1.0" encoding="UTF-8"?>
<save>
  <version major="4" minor="7" revision="1" build="3"/>
  <region id="Objectives">
    <node id="root">
      <children>
        <node id="Objective">
          <attribute id="Description" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000o1" version="2"/>
          <attribute id="ObjectiveID" type="FixedString" value="PLA_ZhentShipment_AgreedHelp"/>
          <attribute id="Priority" type="int32" value="1000"/>
          <attribute id="QuestID" type="FixedString" value="PLA_ZhentShipment"/>
          <attribute id="QuestObjectiveGuid" type="guid" value="8d0d28b1-4dfb-81e8-87d4-095827c891b2"/>
          <children>
            <node id="Markers">
              <attribute id="Markers" type="FixedString" value="SHA_ShadowfellPortal"/>
            </node>
          </children>
        </node>
        <node id="Objective">
          <attribute id="Description" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000o2" version="2"/>
          <attribute id="ObjectiveID" type="FixedString" value="PLA_ZhentShipment_HelpSurvivors"/>
          <attribute id="Priority" type="int32" value="1100"/>
          <attribute id="QuestID" type="FixedString" value="PLA_ZhentShipment"/>
          <attribute id="QuestObjectiveGuid" type="guid" value="a5d4bdab-d5f8-79d6-1e58-ea5493205d96"/>
        </node>
      </children>
    </node>
  </region>
</save>
"""

# Trimmed from retail questcategory_prototypes.lsx.
CATEGORY_LSX = """\
<?xml version="1.0" encoding="UTF-8"?>
<save>
  <version major="4" minor="7" revision="1" build="3"/>
  <region id="QuestCategories">
    <node id="root">
      <children>
        <node id="QuestCategory">
          <attribute id="CategoryID" type="FixedString" value="Crashside"/>
          <attribute id="Description" type="TranslatedString" handle="haaaa0000-0000-0000-0000-0000000000k1" version="1"/>
          <attribute id="QuestCategoryGuid" type="guid" value="019f2fb8-179d-e2e4-9735-46d336e37336"/>
          <attribute id="SortingPriority" type="int32" value="2"/>
        </node>
      </children>
    </node>
  </region>
</save>
"""

# Trimmed from a retail goal script (syntax verbatim).
GOAL_TXT = """\
Version 1
SubGoalCombiner SGC_AND
INITSECTION
DB_HasItemEvent(S_DEN_AdventurerNote_a07e15dd,(FLAG)Flag_370c7614);
DB_QuestDef_State(GOB_Event_e48a7760,"SHA_Nightsong","SolvedPuzzle");
KBSECTION
//REGION Nightsong Quest
IF
GameBookInterfaceClosed(S_GOB_SharTempleMap_f01b15a1,_Char)
AND
DB_Players(_Char)
AND
DB_QuestIsAccepted("SHA_Nightsong")
AND
QuestUpdateIsUnlocked(_Char, "SHA_Nightsong", "SawBook", 0)
THEN
QuestUpdate(_Char, "SHA_Nightsong", "RefinedLocation");

IF
DB_Players(_Char)
AND
DB_QuestIsAccepted("PLA_ZhentShipment")
THEN
QuestUpdate(_Char, "PLA_ZhentShipment", "AgreedHelp");
//END_REGION
EXITSECTION
ENDSECTION
ParentTargetEdge "Act1_DEN"
"""

# Registry file living under Story/Dialogs/ that is NOT a dialog
# (mirrors retail ScriptFlags.lsx / DialogVariables.lsx).
SCRIPTFLAGS_LSX = """\
<save>
  <region id="ScriptFlags">
    <node id="root">
      <children>
        <node id="Flag">
          <attribute id="UUID" type="guid" value="ffff0000-0000-0000-0000-000000000001" />
          <attribute id="Name" type="LSString" value="DEN_SomeFlag" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

LOCA_ENTRIES = [
    LocaEntry("h11111111-1111-1111-1111-111111111111", 1, "Fireball"),
    LocaEntry("h22222222-2222-2222-2222-222222222222", 1, "A bright streak flashes."),
    LocaEntry("h33333333-3333-3333-3333-333333333333", 1, "Savage Attacks"),
    LocaEntry("h44444444-4444-4444-4444-444444444444", 1, "Burning"),
    LocaEntry("h55555555-5555-5555-5555-555555555555", 1, "Longsword"),
    LocaEntry("h66666666-6666-6666-6666-666666666666", 1, "A trusty longsword."),
    LocaEntry("h77777777-7777-7777-7777-777777777777", 1, "Weapon"),
    LocaEntry("h99990000-9999-9999-9999-999999999901", 1, "Well met, traveler."),
    LocaEntry("h99990000-9999-9999-9999-999999999902", 1, "And to you."),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000q1", 4, "The Zhentarim Shipment"),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000q2", 3, "We agreed to recover the shipment."),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000q3", 2, "We noticed a struggle on the road."),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000m1", 1, "Shadowfell Portal"),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000c1", 1, "Goblin Warrior"),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000o1", 2, "Recover the shipment."),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000o2", 2, "Help the survivors."),
    LocaEntry("haaaa0000-0000-0000-0000-0000000000k1", 1, "Wilderness"),
]


def make_story_osi(minor: int = 15) -> bytes:
    """Hand-crafted Osiris story, pinned to LSLib's serializers.

    It contains one named database, one rule owned by one goal, one fact,
    compact string values, function signatures, and goal/global calls.
    """
    data = bytearray()
    scramble = 0

    def raw(fmt, *values):
        data.extend(struct.pack("<" + fmt, *values))

    def string(value):
        encoded = value.encode("utf-8")
        data.extend(byte ^ scramble for byte in encoded)
        data.append(scramble)

    def value(index, type_id, text, kind="variable"):
        if minor >= 14:
            raw("bB", index, 0x0B)  # Variable | IsValid
        raw("B", ord("0"))
        raw("H", type_id)
        raw("B", 1)
        string(text)
        if minor < 14 and kind in ("typed", "variable"):
            raw("BBB", 1, 0, 0)  # IsValid, OutParam, IsAType
            if kind == "variable":
                raw("bBB", index, 0, 0)  # Index, Unused, Adapted

    def entry(node=0, goal=0):
        raw("III", node, 0, goal)

    def call(name, parameters=(), goal=0):
        string(name)
        if name:
            raw("B", bool(parameters))
            if parameters:
                raw("B", len(parameters))
                for parameter in parameters:
                    if minor < 14:
                        raw("B", 1)  # Variable
                    value(*parameter)
            raw("B", 0)  # negate
        raw("i", goal)

    # SaveFileHeader is plain; strings after it are XOR-scrambled.
    raw("B", 0)
    string("Osiris save file")
    raw("BBBB", 1, minor, 0, 0)
    version = f"1.{minor}".encode()
    data.extend(version + bytes(0x80 - len(version)))
    raw("I", 0x1234)
    scramble = 0xAD

    # Types: CHARACTER aliases GUIDSTRING.
    raw("I", 1)
    string("CHARACTER")
    raw("BB", 6, 5)
    raw("I", 0)  # enums
    raw("I", 0)  # DIV objects

    # Two Function records: database and event.
    raw("I", 2)
    for name, kind, node in (("DB_Players", 4, 1), ("PlayerJoined", 1, 0)):
        raw("IIII", 12, 0, 0, node)
        raw("BIIII", kind, 0, 0, 0, 0)
        string(name)
        raw("I", 1)
        raw("B", 0)  # one-byte out mask
        raw("BH", 1, 6)  # one CHARACTER parameter

    # DatabaseNode #1 references RuleNode #2 in Goal #1.
    raw("I", 2)
    raw("BI", 1, 1)
    raw("I", 1)
    string("DB_Players")
    raw("B", 1)
    raw("I", 1)
    entry(2, 1)

    # RuleNode #2. Base -> Tree -> Rel -> rule payload.
    raw("BI", 7, 2)
    raw("I", 0)
    string("")
    entry()
    raw("III", 1, 0, 1)
    entry()
    raw("B", 0)
    raw("I", 0)  # calls
    raw("B", 0)  # variables
    raw("IB", 42, 0)

    if minor < 14:
        # Adapter #1 with one old-layout Tuple constant.
        raw("IIBB", 1, 1, 1, 0)  # count, index, tuple count, logical index
        value(0, 6, "S_Constant", kind="value")
        raw("BbBBB", 1, -1, 1, 0, 0)  # indices + logical map
    else:
        raw("I", 0)  # adapters

    # Database #1 with one CHARACTER fact.
    raw("I", 1)
    raw("I", 1)
    raw("BH", 1, 6)
    raw("I", 1)
    raw("B", 1)
    value(0, 6, "S_Player", kind="value")

    # Goal #1 with one init call.
    raw("I", 1)
    raw("I", 1)
    string("Act1_DEN_AdventurersQuest")
    raw("B", 0)
    raw("I", 0)
    raw("I", 0)
    raw("B", 0)
    raw("I", 1)
    call("DB_Players", ((0, 6, "S_Player"),))
    raw("I", 0)

    # A name-less global action that completes goal #1.
    raw("I", 1)
    call("", goal=1)
    return bytes(data)


def fixture_files() -> dict[str, bytes]:
    from bg3forge.parsers.lsf import write_lsf
    from bg3forge.parsers.lsx import parse_lsx

    # Shipped as binary v6, like retail dialogs and timelines.
    dialog_lsf = write_lsf(parse_lsx(DIALOG_LSX), version=6)
    timeline_lsf = write_lsf(parse_lsx(TIMELINE_LSX), version=6)
    return {
        "Public/Shared/Stats/Generated/Data/Weapon.txt": WEAPON_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Spell_Projectile.txt": SPELL_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Passive.txt": PASSIVE_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Status_BOOST.txt": STATUS_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Data.txt": DATA_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Character.txt": CHARACTER_TXT.encode(),
        "Public/Shared/Stats/Generated/Equipment.txt": EQUIPMENT_TXT.encode(),
        "Public/Shared/Stats/Generated/TreasureTable.txt": TREASURE_TXT.encode(),
        "Public/Shared/Progressions/Progressions.lsx": PROGRESSION_LSX.encode(),
        "Public/Shared/Lists/SpellLists.lsx": SPELL_LISTS_LSX.encode(),
        "Public/Shared/RootTemplates/Weapons.lsx": ROOTTEMPLATE_LSX.encode(),
        "Mods/Shared/Globals/WLD_Main_A/Items/_merged.lsx": GLOBAL_ITEMS_LSX.encode(),
        "Mods/Shared/Levels/WLD_Main_A/Items/_merged.lsx": LEVEL_ITEMS_LSX.encode(),
        "Public/Shared/Tags/aaaa1111-0000-0000-0000-000000000001.lsx": WEAPON_TAG_LSX.encode(),
        "Public/Shared/Tags/bbbb2222-0000-0000-0000-000000000002.lsx": LONGSWORD_TAG_LSX.encode(),
        "Public/Shared/GUI/Icons_Items.lsx": ATLAS_LSX.encode(),
        "Mods/Shared/Story/DialogsBinary/Camp/CAMP_Greeting.lsf": dialog_lsf,
        "Mods/Shared/Story/Dialogs/ScriptFlags/ScriptFlags.lsx": SCRIPTFLAGS_LSX.encode(),
        "Mods/Shared/Story/Dialogs/Camp/CAMP_Greeting.lsj": DIALOG_LSJ.encode(),
        "Public/Shared/Timeline/Generated/tttt0000-0000-0000-0000-000000000001.lsf": timeline_lsf,
        "Mods/Shared/Story/Journal/quest_prototypes.lsx": QUEST_PROTOTYPES_LSX.encode(),
        "Mods/Shared/Story/Journal/objective_prototypes.lsx": OBJECTIVE_LSX.encode(),
        "Mods/Shared/Story/Journal/questcategory_prototypes.lsx": CATEGORY_LSX.encode(),
        "Mods/Shared/Story/Journal/Markers/9d61b258-a858-7e39-39e6-a13a26c8cd8a.lsx": MARKER_LSX.encode(),
        "Mods/Shared/Story/RawFiles/Goals/Act1_DEN_AdventurersQuest.txt": GOAL_TXT.encode(),
        "Mods/Shared/Story/story.div.osi": make_story_osi(),
        "Localization/English/english.loca": write_loca(LOCA_ENTRIES),
    }


@pytest.fixture
def sample_pak(tmp_path):
    """A real LSPK v18 archive holding the synthetic data set."""
    writer = PakWriter()
    for name, data in fixture_files().items():
        writer.add(name, data)
    return writer.write(tmp_path / "Shared.pak")


@pytest.fixture
def data_dir(sample_pak):
    """Directory containing the sample pak, i.e. a fake game Data dir."""
    return sample_pak.parent
