"""Shared fixtures: a synthetic mini-BG3 data set packed into a real .pak."""

from __future__ import annotations

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
]


def fixture_files() -> dict[str, bytes]:
    from bg3forge.parsers.lsf import write_lsf
    from bg3forge.parsers.lsx import parse_lsx

    # Shipped as binary v6, like retail dialogs.
    dialog_lsf = write_lsf(parse_lsx(DIALOG_LSX), version=6)
    return {
        "Public/Shared/Stats/Generated/Data/Weapon.txt": WEAPON_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Spell_Projectile.txt": SPELL_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Passive.txt": PASSIVE_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Status_BOOST.txt": STATUS_TXT.encode(),
        "Public/Shared/Stats/Generated/Data/Data.txt": DATA_TXT.encode(),
        "Public/Shared/Stats/Generated/TreasureTable.txt": TREASURE_TXT.encode(),
        "Public/Shared/RootTemplates/Weapons.lsx": ROOTTEMPLATE_LSX.encode(),
        "Public/Shared/Tags/aaaa1111-0000-0000-0000-000000000001.lsx": WEAPON_TAG_LSX.encode(),
        "Public/Shared/Tags/bbbb2222-0000-0000-0000-000000000002.lsx": LONGSWORD_TAG_LSX.encode(),
        "Public/Shared/GUI/Icons_Items.lsx": ATLAS_LSX.encode(),
        "Mods/Shared/Story/DialogsBinary/Camp/CAMP_Greeting.lsf": dialog_lsf,
        "Mods/Shared/Story/Dialogs/ScriptFlags/ScriptFlags.lsx": SCRIPTFLAGS_LSX.encode(),
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
