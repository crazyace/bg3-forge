# Plan: current milestones

Working plan as of 2026-07. 0.1.0 is published; 0.2.0 development is
accumulating on `main`. Two consumer-driven tracks are now active: the
typed **progression graph** (read side — for build-planning and
data-export consumers) and **mod authoring** (write side — generating
loadable mods, retail-verified for items). Neither opens a speculative
binary-format project; the backlog formats wait for a concrete consumer.

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
- [x] Move the first downstream consumer from its temporary git pin to
      `bg3forge[icons]>=0.1.0,<0.2.0` from PyPI; no vendored copies
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

## 4. Release 0.1.0 — complete

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
- [x] Configure the PyPI pending trusted publisher and GitHub `pypi`
      environment for `.github/workflows/publish.yml`
- [x] Date the changelog, tag `v0.1.0`, publish the GitHub release, and
      verify the trusted workflow's PyPI upload

Released 2026-07-21. The trusted workflow uploaded both distributions,
and a clean `pip install bg3forge==0.1.0` installed the wheel with zero
dependencies and passed CLI/import smoke tests.

## 5. Post-release consumer milestone — typed progressions — first slice complete

Model the existing progression parser as a relationship graph rather than
starting a speculative format project. The target API is classes/races →
level records → granted spells/passives, with reverse lookups driven by
concrete build-planning and data-export queries. Retail counts and joins
must be added to `validate` and `benchmark` before downstream migration.

First vertical slice retail-validated 2026-07-21: 1,004 effective progression
records across 144 tables, 315 effective spell lists, and zero missing passive,
spell-list, or spell joins. Automatic grants remain distinct from player
choices, load-order overrides are applied, and the stage costs 0.29 s.

Class description join landed 2026-07-22, driven by the teachable-spells
authoring work: `game.classes` ties each class/subclass to its learnable
spell list (`SpellList`/`CanLearnSpells` — the wizard transcription pool),
its progression table, and parent/subclass links, with
`game.spell_lists_containing(spell)` as the class-spell authoring query.
Race descriptions remain open for when a consumer needs them.

## 6. Mod authoring — item pipeline complete, retail-verified — current

The inverse of the read stack: generate a loadable mod. Built on the
format writers (stats, RootTemplate `_merged.lsf`, `meta.lsx`, Version64,
`.loca`, `PakWriter`), with the `Mod` capstone (`bg3forge.authoring`)
composing them and minting stable UUID5 identifiers/handles.

- [x] Write primitives: stats writer, RootTemplate builder, `meta.lsx`
      builder + Version64 pack/unpack
- [x] `Mod` capstone: `new_item`/`new_armor` assemble a `.pak`, rebuilds
      byte-identical
- [x] Retail-verified in a Patch 8 game — item spawns, stats and localized
      name/description resolve, icon inherits, equip boosts apply. Found and
      fixed the `_merged.lsf` requirement by diffing a known-good retail mod
- [x] Equip abilities: `boosts` / `grants_spells` / `passives` / `statuses`
- [x] Obtainability: `place_in_treasure` / `treasure=` injects into an
      existing table with `CanMerge`, so items drop from a base-game
      container instead of console-spawn only. Retail-verified: the item
      appeared in the tutorial chest on a fresh playthrough
- [x] Weapons (`new_weapon`): damage/type/properties, with on-wield boosts
      and granted actions routed to `BoostsOnEquipMainHand`. Retail-verified
      in the tutorial chest (correct damage, inherited traits, weapon action)
- [x] Custom passives (`new_passive`): `type "PassiveData"` with its own
      boosts and localized name, granted through an item's `passives=[...]`
- [x] Custom statuses (`new_status`): `StatusData` BOOST with boosts,
      instant `OnApplyFunctors`, and localized name — enables fully-original
      consumables
- [x] Custom spells (`new_spell`): `SpellData` clone-and-tweak — `using` a
      retail base inherits targeting/animation/VFX; overrides carry identity
      and effect (`SpellSuccess`, `SpellProperties`, tooltip fields).
      Delivered via `new_scroll(spell=…)` or an item's `grants_spells`.
      Retail-verified: a scroll of a cloned Fire Bolt cast in game with
      overridden 3d10 damage and an auto-derived damage tooltip
- [x] Consumables: `new_potion`/`new_elixir` (Consume action applying a
      status) and `new_scroll` (cast-from-scroll action) — with custom
      statuses and spells, fully-original consumables end to end
- [x] Teachable spells: `replace_spell_list` re-ships a class's learnable
      list with a custom spell appended, and `new_scroll` emits the
      ActionType 33 learn action. Retail-verified: Forge Step transcribed
      from its scroll into the wizard spellbook and cast
- [x] Class spells: `add_class_spell(game, mod, class, spell, level=…)`
      extends a class's selection/prepare lists (cantrip-safe).
      Retail-verified: Forge Step offered in a Sorcerer's level-up picker,
      selected, and cast

**Milestone complete and retail-verified end to end** — items, weapons,
obtainability, and custom passives, statuses, and spells: a mod can ship
fully-original content with every piece invented by the library. Further
authoring work is consumer-driven — build what a real mod needs and verify
each in game.

## 7. Format backlog

In priority order unless a consumer changes it:

1. Virtual texture (GTS/GTP) atlas support
2. GR2 model metadata
3. Full Osiris rule decompilation

Compiled Osiris already exposes header, type, function, database, goal,
and rule metadata. Executable rule reconstruction remains last because it
is the largest project and has no current consumer requirement.

## Sequencing

Milestones 1–4 and 6 are complete. **Mod authoring is retail-verified end
to end** (fully-original items, weapons, consumables, passives, statuses,
and spells); further authoring features are consumer-driven. The remaining
active track is the **typed progression graph** (first slice done; the
class/race description join resumes when the data consumer needs it). Do
not start a backlog format without a concrete consumer or a separately
agreed research goal.
