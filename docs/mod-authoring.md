# Mod authoring — retail verification

The authoring primitives and the `Mod` capstone are verified both by
round-tripping every generated file through Forge's parsers and by loading
the resulting mods in a retail Patch 8 game. Generated armor, weapons,
consumables, passives, statuses, and spells have loaded successfully; items
have appeared in base-game treasure, scrolls have cast and taught custom
spells, and custom spells have appeared in class level-up selection.

The detailed results and the operational lessons discovered during those
checks are recorded in [the retail baseline](baseline.md#mod-authoring--retail-verified-2026-07-22).
This checklist documents the repeatable smoke test for future releases and
game patches.

## Reproduce the verification

### Build a test mod

```python
from bg3forge import Mod

mod = Mod("ForgeSmokeTest", author="you", description="Forge authoring smoke test.")
template_uuid = mod.new_armor(
    "ARM_Forge_TestPlate",
    armor_class=21,
    stats_using="_Armor",                 # a real base stats entry
    parent_template="<base-template-uuid>",  # a real base item's RootTemplate UUID
    display_name="Forge Test Plate",
    description="If you can read this in game, authoring works.",
    icon="Item_Plate_Body",               # an existing atlas icon
)
print("template UUID:", template_uuid)    # spawn code for the in-game test
print("built:", mod.build("ForgeSmokeTest.pak"))  # build returns the pak path
```

To find a real `parent_template` UUID and a base stats entry to inherit
from, read them straight out of the install with the same library:

```python
from bg3forge import Game
game = Game()
plate = game.items["ARM_Body_Plate"]         # or any armor you want to clone
print(plate.owner_templates[0].map_key)      # -> use as parent_template
```

### Install and load

1. Copy `ForgeSmokeTest.pak` into the BG3 `Mods` folder
   (`%LOCALAPPDATA%\Larian Studios\Baldur's Gate 3\Mods` on Windows).
2. Enable the mod in your mod manager (or add it to `modsettings.lsx`).
3. Launch the game and load or start a save.

### Verify (in order — each rules out a layer)

- [ ] **The game boots with the mod enabled.** A malformed `meta.lsx`
      usually shows up here (mod missing from the list, or a load error).
- [ ] **The item exists.** Spawn it by its template UUID from the dev
      console / Script Extender:
      `spawn <template-uuid>` or add it to your inventory. If it appears,
      `meta.lsx` + RootTemplate + stats binding are all good.
- [ ] **Stats are right.** Inspect the item — Armour Class 21, and any
      inherited fields from the base stats entry are present.
- [ ] **The name and description render.** You should see "Forge Test
      Plate" and the description — *not* a raw `h...` handle. A raw handle
      means the localization didn't resolve (handle/`.loca` mismatch).
- [ ] **The icon shows.** The referenced atlas icon should display.
- [ ] **The visuals render.** The item should use the `parent_template`'s
      appearance rather than a placeholder.

### If something fails

Note which checkbox failed and what you saw — that isolates the layer:

| Fails at | Likely culprit |
| --- | --- |
| Boot / mod list | `meta.lsx` shape or Version64 |
| Item won't spawn | RootTemplate ↔ stats `RootTemplate` UUID mismatch, or bad `Type` |
| Name shows as `h...` | localization: `.loca` key vs template handle, or folder/language path |
| No icon | `Icon` name not in any atlas |
| No/placeholder mesh | `parent_template` UUID wrong or not a real base |

Report the failing checkbox and the observed value; each maps to a
specific primitive, so a fix (and a regression fixture) is targeted —
the same loop that closed the read-side retail gaps.
