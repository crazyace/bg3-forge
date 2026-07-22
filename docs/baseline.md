# Retail baseline — 2026-07

First clean validation sweep and benchmark against a full retail install.
This is the reference point the contributor policy (CONTRIBUTING.md,
design principle #5) measures optimization proposals against.

## Environment

| | |
| --- | --- |
| bg3forge | 0.1.0 (branch `main`, post-`044c97b`) |
| Python | 3.12.10 |
| OS | Windows 11 (10.0.26200) |
| Native LZ4 | yes |
| Data source | Steam install, 52 paks, 154.57 GB |
| Game data | 4.8.700.7143220 (module GustavDev) |
| Language | English |

## Validation (`bg3forge validate`)

```
Coverage
--------
paks                            30
pak parts skipped               22
stats files                    136
stats entries               16,593
stats globals                  345
treasure files                   5
treasure tables              1,565
loca files                       9
loca handles               232,876
lsx resources               23,061
lsf resources               83,909
lsj resources               10,015
root templates              25,564
atlases                         11
dialogs                     18,757
dialog nodes               374,082
timelines                   32,427
quests                         167
quest steps                  3,543
quest markers                  542
objectives                   1,335
quest categories                14
goals                          975
goal quest refs                367
progression files               10
progressions                 1,073
progression tables             144
progression passive grants       397
progression passive removals        19
progression passives missing         0
progression spell list grants       240
progression spell list choices       294
progression spell lists missing         0
spell list files                 3
spell lists                    358
spell list spells            3,293
spell list spells missing         0
compiled stories                11
story functions            182,780
story databases            140,190
story goals                  8,164
story rules                435,803
source goals compiled          943
source goals missing             0
equipment files                  5
equipment sets                 738
files skipped              923,751
stats resolved              16,132

OK: every recognized file parsed cleanly.
```

Every recognized format parses cleanly on retail data: ~117k LSX/LSF/LSJ
resources, ~233k localization handles, 16.6k stats definitions layering
down to 16,132 resolved entries (461 patch-layer redefinitions), zero
inheritance failures. `files skipped` counts assets we don't claim to
parse (textures, models, audio, …).

The completed journal layer was retail-verified on 2026-07-21. The two
previously sample-gated parsers produced 1,335 objectives and 14 quest
categories with zero issues. A relationship spot check resolved the full
localized chain:

    PLA_ZhentShipment — Find the Missing Shipment
      category: Crashside — Nautiloid Crash Region
      objective: PLA_ZhentShipment_AgreedHelp — Find the missing wagon.
      marker: PLA_ZhentShipment_Caravan — Wagon

The compiled Osiris metadata reader was retail-verified the same day
against all 11 shipped `story.div.osi` files (versions 1.13–1.15). It
traversed 182,780 function records, 140,190 databases, 8,164 goal records,
and 435,803 rules with zero parse failures. All 943 unique source-goal
names appeared in at least one compiled story variant; the difference
from 975 source files is duplicate goal names across modules.

The first typed-progression slice was retail-verified on 2026-07-21.
All ten progression resources and all three spell-list resources parsed
cleanly. The validation sweep saw 1,073 physical progression definitions
and 358 physical spell-list definitions; load-order deduplication produces
1,004 effective progression records in 144 tables and 315 effective spell
lists through `Game`. All 397 passive grants, 19 passive removals, 534
progression spell-list references, and 3,293 spell-list spell references
resolved with zero missing joins.

Other spot checks along the way: `game.dialogs.lines(...)` returned real
localized lines ("Mmm. Delicious gruel."), `game.quests` real journal
text ("Find the Nightsong"), and `game.characters` a fully joined NPC
("Duke Ulder Ravengard" with his longsword, shield, and plate).

Getting here took three retail-only fixes worth remembering:
`key`-style global stats files, the LSF v6 metadata offset
(36,560 files), and self-`using` patch layering — all invisible to
synthetic fixtures. See the git history around `9b2b5d7`..`3b0d125`.

## Benchmark (`bg3forge benchmark`, warm cache)

```
Read pak indexes ........   1.89 s
Parse stats .............   2.31 s
Parse localization ......   2.60 s
Parse root templates ....   4.80 s
Parse atlases ...........   2.64 s
Build models ............   0.05 s
Resolve relationships ...   0.02 s
Export JSON .............   0.31 s

pak entries ............. 1,041,877
stats entries ...........   16,132
loca handles ............  232,876
root templates ..........   25,560
items ...................    3,139
spells ..................    4,687
passives ................    1,827
statuses ................    4,631

Peak RSS ................    826 MB
```

Reading: the full pipeline — locate, parse everything, build and link
every model, export JSON — is **~14.6 s warm** end to end. Parsing
dominates (RootTemplates at 4.8 s is the largest single stage); model
building and relationship resolution are effectively free (70 ms
combined), which validates the lazy-graph design. Peak RSS 826 MB is
comfortable for a developer tool.

**Release-gate run (all datasets):** with tags, dialogs, timelines,
quests, goals, characters, and equipment added, the same install
benchmarked at ~28.6 s / 828 MB — and the stage table itself exposed a
defect: ten stages each cost a near-identical ~2.3 s, the fixed price
of re-parsing every pak file list per stage. Cached shared readers
remove that redundancy. This is design principle #5 working as
intended — the optimization exists because the benchmark measured the
need.

**Post-fix run (same install, before compiled-story parsing):** total
**~8.8 s** / 827 MB — the
per-stage toll collapsed to real work::

    Read pak indexes ........   1.83 s
    Parse stats .............   2.21 s
    Parse localization ......   0.47 s   (was 2.63)
    Parse root templates ....   2.46 s   (was 4.78)
    Parse tags ..............   0.19 s   (was 2.24)
    Parse atlases ...........   0.48 s
    Index dialogs ...........   0.11 s   (was 2.33)
    Index timelines .........   0.10 s
    Parse quests ............   0.37 s
    Index goals .............   0.10 s
    Build models ............   0.17 s
    Resolve relationships ...   0.01 s
    Export JSON .............   0.28 s

**Final 0.1.0 release gate (same install):** total **~25.1 s** / 827 MB.
The completed compiled-story stage accounts for 16.05 s; all other stages
remain at the post-fix baseline::

    Read pak indexes .........   1.82 s
    Parse stats ..............   2.23 s
    Parse localization .......   0.47 s
    Parse root templates .....   2.48 s
    Parse tags ...............   0.19 s
    Parse atlases ............   0.48 s
    Index dialogs ............   0.10 s
    Index timelines ..........   0.09 s
    Parse quests .............   0.57 s
    Index goals ..............   0.10 s
    Parse compiled stories ...  16.05 s
    Build models .............   0.17 s
    Resolve relationships ....   0.02 s
    Export JSON ..............   0.28 s

    pak entries .............. 1,041,877
    stats entries ............   16,132
    loca handles .............  232,876
    root templates ...........   25,560
    tags .....................    1,103
    atlases ..................       11
    dialogs indexed ..........    9,386
    timelines indexed ........   32,427
    quests ...................      167
    objectives ...............    1,335
    quest categories .........       14
    goals indexed ............      946
    compiled stories .........        6
    story goals ..............    4,273
    story databases ..........   73,340
    story rules ..............  226,858
    items ....................    3,139
    spells ...................    4,687
    passives .................    1,827
    statuses .................    4,631
    characters ...............    1,550
    equipment sets ...........      738

`validate` intentionally reports 11 physical compiled-story files across
all pak variants. The consumer-facing `Game.story` index applies game
load-order overrides by archived path, so the benchmark parses the six
effective logical stories. Both numbers are correct for their respective
purposes.

**0.2.0.dev0 typed-progression gate (same install):** the new progression
stage adds 0.29 s and keeps peak RSS at 826 MB::

    Read pak indexes .........   1.82 s
    Parse stats ..............   2.19 s
    Parse localization .......   0.47 s
    Parse root templates .....   2.48 s
    Parse tags ...............   0.19 s
    Parse atlases ............   0.49 s
    Index dialogs ............   0.10 s
    Index timelines ..........   0.09 s
    Parse quests .............   0.58 s
    Index goals ..............   0.10 s
    Parse compiled stories ...  15.98 s
    Parse progressions .......   0.29 s
    Build models .............   0.17 s
    Resolve relationships ....   0.02 s
    Export JSON ..............   0.29 s

    progressions .............    1,004
    progression tables .......      144
    spell lists ..............      315
    progression passive grants       397
    progression spell grants .      558
    progression spell choices    11,587

The benchmark's 558 automatic grants and 11,587 choices count resolved
spell entries after expanding referenced lists; the validation counters
count the 240 `AddSpells` and 294 `SelectSpells` list references themselves.
This typed-progression gate is the current reference for optimization PRs.

Per the roadmap, no further optimization is planned until a real
consumer needs one; any proposal should beat these numbers on
comparable hardware and include its own before/after reports.

## Mod authoring — retail-verified (2026-07-22)

The write side reached the same bar as the read side: a mod generated
entirely by `bg3forge.authoring.Mod` was installed into a retail Patch 8
game and loaded successfully. The generated item (an armor cloning a base
template via `ParentTemplateId`) resolved every layer in game:

- item spawned by its template UUID (`RootTemplates/_merged.lsf` loaded)
- stats bound — Armour Class 21 applied
- localized name and description rendered (not raw handles)
- icon inherited from the base template
- an equip boost applied to the character — `Ability(Strength,2)` showed
  as `+2 from <item>` on the character's Strength sheet

Getting here surfaced one write-only defect, invisible to round-tripping
against our own parsers: BG3 loads RootTemplates only from a binary LSF
named exactly `_merged.lsf`, not an arbitrary `.lsx`. A known-good retail
item mod confirmed the rest of the output (meta.lsx, stats layout, `.loca`
keys, and `h…g…` handle format) already matched byte-for-byte. See the git
history around the `_merged.lsf` fix.

### Obtainability — verified in a fresh playthrough

The item was then made obtainable with `treasure="TUT_Chest_Potions"`
(injecting into an existing table with `CanMerge`). On a new game, the
generated armor appeared **in the tutorial chest** during normal play —
no console, the strongest possible confirmation.

The container→treasure lookup added to close this loop was also confirmed
against the same install:

    >>> game.item_templates.by_treasure_table("TUT_Chest_Potions")
    S_Chest_Potions  e57e3af6-ae79-4d5c-9d11-f695b359c740

That is the level-placed chest object (its `InventoryList` references the
table), and its `map_key` is the object UUID — matching, from data alone,
the chest the item was found in. The full write path — author → pack →
load → equip → **find in the world** — is retail-verified.

### Weapons and custom passives — verified 2026-07-22

- `new_weapon`: a generated 2d6 slashing blade (cloning a base via
  `ParentTemplateId`) appeared in the tutorial chest with correct damage,
  inherited traits and finesse properties, the magical shimmer from
  `DefaultBoosts`, and its granted weapon action — confirming the
  `BoostsOnEquipMainHand` routing.
- `new_passive`: a custom `PassiveData` ("Forge Warding",
  `DamageReduction(All, Flat, 3)`) granted through an armor's
  `PassivesOnEquip` appeared under Notable Features on the character
  sheet with its localized name — a passive that does not exist in the
  base game, defined entirely by the library.
- Operational note learned along the way: container loot is rolled at
  new-game generation and stored in the save, so treasure-table tests
  need a fresh game (or spawn the item by its deterministic UUID).

### Consumables — verified 2026-07-22

- `new_potion`: a generated potion (cloning the healing potion's visuals,
  applying `POTION_OF_HEALING`) healed on drink and was consumed.
- `new_scroll`: a generated scroll cast `Shout_FeatherFall` on use (with
  its normal party-wide shout radius) and was consumed — confirming the
  `OnUsePeaceActions` cast-from-scroll action and typed LSF attributes.
- `new_elixir` differs from the potion only by `StatusDuration = -1`, the
  exact field observed on the retail elixir template.

### Custom statuses and retail-parity tooltips — verified 2026-07-22

The fully-original consumable: an elixir applying a status invented by the
library ("Forgefire", `Ability(Strength,2)` + fire resistance) was drunk in
game — the condition appeared with its localized name and description,
`+2 from Forgefire` on the Strength sheet, halved fire damage in the
resistances panel, and an until-long-rest duration.

Dissecting retail's Elixir of Bloodlust then mapped BG3's four item text
slots (`DisplayName` = name, `Description` = italic flavor,
`TechnicalDescription` = the golden effect blurb, `OnUseDescription` = the
use-verb "Drink") and the `<LSTag>` hyperlink markup carried inside
localized strings. The rebuilt brew rendered at full retail parity: its
blurb in the right slot, "Forgefire" as a working hyperlink popping the
custom status card, and elixir-base visuals with no inherited text.

Operational rules learned: template text changes need *fresh item
instances* (existing items in a save render stale tooltips), and the
line under the blurb is [status icon] + duration — the status identity
there is its `Icon`.
