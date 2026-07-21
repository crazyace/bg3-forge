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

**Post-fix run (same install):** total **~8.8 s** / 827 MB — the
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

This is the current reference for optimization PRs.

Per the roadmap, no further optimization is planned until a real
consumer needs one; any proposal should beat these numbers on
comparable hardware and include its own before/after reports.
