# Retail baseline — 2026-07

First clean validation sweep and benchmark against a full retail install.
This is the reference point the contributor policy (CONTRIBUTING.md,
design principle #5) measures optimization proposals against.

## Environment

| | |
| --- | --- |
| bg3forge | 0.1.0 (branch `claude/bg3-forge-toolkit-7xlkef`, post-`3b0d125`) |
| Python | 3.12.10 |
| OS | Windows 11 (10.0.26200) |
| Native LZ4 | yes |
| Data source | Steam install, 52 paks, 154.57 GB |
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
root templates              25,564
atlases                         11
files skipped              934,757
stats resolved              16,132

OK: every recognized file parsed cleanly.
```

Every recognized format parses cleanly on retail data: ~107k LSX/LSF
resources, ~233k localization handles, 16.6k stats definitions layering
down to 16,132 resolved entries (461 patch-layer redefinitions), zero
inheritance failures. `files skipped` counts assets we don't claim to
parse (textures, models, audio, …).

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

Per the roadmap, no optimization is planned until a real consumer needs
one; any proposal should beat these numbers on comparable hardware and
include its own before/after reports.
