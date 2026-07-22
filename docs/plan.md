# Plan: current milestones

Agreed working plan as of 2026-07. The first real consumer integration
has now exercised the item/template/icon API against retail data, so the
next gate is the 0.1.0 release. Work after that remains consumer-driven:
finish the typed progression graph for build-planning and data-export
consumers before opening another large binary-format project.

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

## 3. First downstream consumer integration — item-data slice complete

*The point of the whole library. Also the best API review we can get.*

- [x] Inventory the first integration slice: items, passives, statuses,
      placed templates, and icons
- [x] Depend on bg3forge via git ref (pinned commit) until the release
      is cut; no vendored copies
- [x] Replace the Script Extender/Lua item dump and Multitool icon path
      with `Game`-API calls; the consumer contains no pak/format code for
      this pipeline
- [x] Feed consumer friction back into Forge: global and level-placed
      templates, `TemplateName` inheritance, and selected in-pak icon
      export were all added from this integration
- [x] Validate the generated consumer database against its existing data:
      7,081 named items, 146/146 curated records enriched, and 994/994 gear
      icon keys covered after two documented fallbacks
- [ ] Add typed progression joins (classes/races → level progressions →
      granted spells/passives), with reverse lookups for build-planning
      and data-export consumers
- [ ] Migrate the remaining game-derived leveling inputs once the typed
      progression API is available

The item-data exit criterion is met. The broader consumer milestone closes
when the remaining leveling-data inputs can be served through BG3 Forge.

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
- [x] Record the final retail benchmark: ~25.1 s total, 827 MB peak RSS;
      compiled-story parsing is 16.05 s and the remaining stages match
      the post-reader-cache baseline
- [ ] Configure the PyPI pending trusted publisher and GitHub `pypi`
      environment for `.github/workflows/publish.yml`
- [ ] Date the changelog, tag `v0.1.0`, publish the GitHub release, and
      verify the trusted workflow's PyPI upload

## 5. Post-release consumer milestone — typed progressions

Model the existing progression parser as a relationship graph rather than
starting a speculative format project. The target API is classes/races →
level records → granted spells/passives, with reverse lookups driven by
concrete build-planning and data-export queries. Retail counts and joins
must be added to `validate` and `benchmark` before downstream migration.

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
slice. Finish the 0.1.0 release next, then let concrete consumer progression
needs shape milestone 5. Do not start a backlog format without a concrete
consumer or a separately agreed research goal.
