# Plan: current milestones

Agreed working plan as of 2026-07. The first real consumer integration
has now exercised the item/template/icon API against retail data, so the
next gate is the 0.1.0 release. Work after that remains consumer-driven:
finish Pathway's leveling-data migration before opening another large
binary-format project.

## 1. Retail verification of the completed journal layer — complete

*Small — one loop of the usual cycle.*

The objectives/categories parsers were the final code not yet proven
against retail at scale (they were built from 40-line samples).

- [x] `git pull`, then `bg3forge validate --max-issues 999` on the
      game machine
- [x] Result: 1,335 `objectives`, 14 `quest_categories`, zero issues
- [x] Spot check: `PLA_ZhentShipment` resolved its localized category,
      first linked objective, and `PLA_ZhentShipment_Caravan` marker
- [x] Fold the new counts into `docs/baseline.md`

Completed 2026-07-21 against game data 4.8.700.7143220: clean sweep,
counts recorded, and the relationship chain verified.

## 2. Compiled Osiris reader (`story.div.osi`) — complete

*The next format project, LSF-sized. Deepens the quest graph the most.*

The shipped goal *source* already gives quest↔logic edges, but the
compiled story database is the authoritative, complete form (and the
Honour/HonourX variants ship only compiled). Same discipline as LSF:

- [x] Study the reference implementation (LSLib `Story/StoryReader`)
      before writing any struct — fetch the actual source, no
      from-memory format guessing (the LSF v6 lesson)
- [x] Scope v1 to *metadata*: header/version, goal list, database
      names/signatures, rule counts — enough to cross-check the goal
      scripts and diff Gustav vs Honour. Full rule decompilation is
      explicitly out of scope for v1
- [x] Parser in `parsers/osiris.py`, read-only; `game.story`
      lazy (current retail ships 11 files, and they are large)
- [x] Wire into `validate` (counts + per-file failures) so the retail
      run judges it; add a benchmark stage
- [x] Fixtures: hand-crafted minimal .osi per the reference structs
      (like the LSF byte-layout pinning tests)

Exit criterion: all 11 retail `story.div.osi` files parse; goal list
cross-checks against `game.goals` (every source goal appears in the
compiled story).

Completed 2026-07-21 against all 11 retail stories. The first pass parsed
ten files and identified Gustav's older Osiris 1.13 expanded-value
layout; the pinned follow-up fix produced a clean sweep. All 943 unique
source-goal names were present in compiled data.

## 3. BG3 Pathway integration — item-data slice complete

*The point of the whole library. Also the best API review we can get.*

- [x] Inventory the first integration slice: items, passives, statuses,
      placed templates, and icons
- [x] Depend on bg3forge via git ref (pinned commit) until the release
      is cut; no vendored copies
- [x] Replace the Script Extender/Lua item dump and Multitool icon path
      with `Game`-API calls; Pathway contains no pak/format code for this
      pipeline
- [x] Feed consumer friction back into Forge: global and level-placed
      templates, `TemplateName` inheritance, and selected in-pak icon
      export were all added from this integration
- [x] Validate the generated Pathway database against the existing
      consumer data: 7,081 named items, 146/146 curated records enriched,
      and 994/994 gear icon keys covered after two documented fallbacks
- [ ] Add typed progression joins (classes/races → levels →
      spells/passives) for Pathway's leveling/build data
- [ ] Migrate any remaining game-derived Pathway inputs once the typed
      progression API is available

The item-data exit criterion is met. The broader consumer milestone closes
when Pathway's remaining leveling data also comes through BG3 Forge.

## 4. Release 0.1.0 — current

*The library is retail-proven and now has a real downstream consumer.*

- [x] Reconcile README and changelog with everything added since the
      initial release draft
- [x] Confirm current `main` CI passes across Linux, Windows, and macOS
      on Python 3.10–3.12 plus the zero-dependency job
- [x] Retail `doctor` and full `validate` gate pass on game data
      4.8.700.7143220
- [x] Run the current test, package-build, wheel-content, and fresh-venv
      smoke gates from `docs/release-checklist.md`
- [ ] Date the changelog, tag `v0.1.0`, publish to PyPI, and create the
      GitHub release

## 5. Post-release consumer milestone — typed progressions

Model the existing progression parser as a relationship graph rather than
starting a speculative format project. The target API is classes/races →
level records → granted spells/passives, with reverse lookups where a real
Pathway query needs them. Retail counts and joins must be added to
`validate` and `benchmark` before the consumer migrates.

## 6. Format backlog

In priority order unless a consumer changes it:

1. Virtual texture (GTS/GTP) atlas support
2. GR2 model metadata
3. Full Osiris rule decompilation

Compiled Osiris already exposes header, type, function, database, goal,
and rule metadata. Executable rule reconstruction remains last because it
is the largest project and has no current consumer requirement.

## Sequencing

Milestones 1 and 2 are complete, and milestone 3 proved the first consumer
slice. Finish the 0.1.0 release next, then let Pathway's progression needs
shape milestone 5. Do not start a backlog format without a concrete
consumer or a separately agreed research goal.
