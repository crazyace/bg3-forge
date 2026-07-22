# Changelog

## 0.2.0 — unreleased

### API

* Added `game.progressions`, a load-order-aware collection indexed by
  progression UUID and grouped by `TableUUID`/level.
* Progression passive additions/removals resolve to typed models. Referenced
  spell lists resolve `AddSpells` automatic grants separately from
  `SelectSpells` choices, with reverse links on `Passive` and `Spell`.
* Added progression and spell-list coverage, unresolved-reference counts,
  and a progression stage to `validate`/`benchmark`.
* Retail verification found 1,004 effective progression records across 144
  tables and 315 effective spell lists, with zero unresolved joins; the new
  benchmark stage takes 0.29 seconds on the reference install.
* RootTemplates now capture their `InventoryList` object references
  (`RootTemplate.inventory` / `.treasure_tables`), and
  `RootTemplateIndex.by_treasure_table(name)` returns the containers that
  fill from a treasure table. On `game.item_templates` (which includes
  placed level objects) this answers "which container drops from
  `TUT_Chest_Potions`, and what's its spawn UUID" — closing the loop with
  the authoring `treasure=` feature.

### Mod authoring (experimental)

The first write primitives aimed at programmatic mod creation:

* Added a stats writer (`write_stats`, `write_stats_document`), the inverse
  of the stats parser. Re-parsing its output reproduces the same document,
  and the canonical fixture round-trips byte-for-byte.
* Added a `meta.lsx` module-manifest builder: `build_meta_document` turns a
  `ModuleInfo` (name, folder, UUID, packed version) into a game-readable
  manifest via `write_lsx`, with `parse_meta` to read one back.
* Added `pack_version64`/`unpack_version64` (the public inverse pair for
  Larian's 64-bit module version).
* Added a RootTemplate node builder: `build_root_template_node` constructs a
  `GameObjects` item template (MapKey, Stats, Icon, TranslatedString
  DisplayName/Description handles, `ParentTemplateId` for reused visuals, and
  tags), and `build_templates_document` wraps them in the `Templates` region
  a RootTemplate file uses. Built templates round-trip through
  `parse_root_templates` and resolve inheritance via `RootTemplateIndex`.
* Added the `Mod` capstone (`bg3forge.authoring`): `mod.new_armor(...)` /
  `mod.new_item(...)` assemble stats, RootTemplate, `meta.lsx`, and
  localization, and `mod.build(path)` packs a `.pak`. UUIDs and handles are
  minted with UUID5, so rebuilds are byte-identical. It writes only to the
  chosen output path, never the game install. Verified end to end by
  building a pak and reading every cross-reference back through the parsers.
* Fixed the capstone to emit RootTemplates as `RootTemplates/_merged.lsf`
  (binary LSF v7), not an arbitrary `.lsx` — BG3 only loads templates from
  that exact file. Confirmed by diffing a known-good retail item mod, whose
  `meta.lsx`, stats layout, `.loca` keys, and `h…g…` handle format all
  matched what the capstone already produced; the RootTemplate file was the
  one difference.
* Added equip-ability parameters to `new_item`/`new_armor`: `boosts`,
  `grants_spells` (added as `UnlockSpell(...)` boosts), `passives`
  (`PassivesOnEquip`), and `statuses` (`StatusOnEquip`), each merging with
  any explicit `data`. Saves hand-writing the semicolon-joined stats fields.
* **Retail-verified in game (Patch 8):** a capstone-built mod loaded and its
  item resolved end to end — spawned by UUID, AC applied, localized
  name/description rendered, icon inherited, and an `Ability(Strength,2)`
  boost applied to the character. See `docs/baseline.md`.
* Added item obtainability: `mod.place_in_treasure(table, item)` (and a
  `treasure=` shortcut on `new_item`/`new_armor`) injects an item into an
  existing treasure table with `CanMerge`, so it drops from a base-game
  container (e.g. `"TUT_Chest_Potions"` for the tutorial chest) instead of
  being console-spawn-only. Backed by a new treasure-table writer
  (`write_treasure_tables`). Retail-verified: the generated item appeared in
  the tutorial chest on a fresh playthrough.
* Added `mod.new_weapon(...)`: `damage`, `damage_type`, and
  `weapon_properties` set the weapon stats fields, and on-wield effects
  (`boosts`, `grants_spells`) route to `BoostsOnEquipMainHand` — not
  `Boosts` — with always-on effects in `DefaultBoosts`, matching retail
  weapon layout. Retail-verified: a generated weapon dropped in the tutorial
  chest with correct damage, inherited traits, and its weapon action.
* Added `mod.new_passive(...)`: define a *custom* passive (`type
  "PassiveData"`) with its own `boosts` and a localized name/description,
  returning the name for use in an item's `passives=[...]`. Handles carry the
  `;version` suffix BG3 uses for PassiveData, and `Properties` defaults to
  `Highlighted` so the passive shows on the character sheet.
* Added `mod.new_status(...)`: define a *custom* status (`type "StatusData"`,
  `BOOST` by default) with `boosts` active while it lasts, instant
  `on_apply` functors, a localized name/description, and `StackId`
  defaulting to the name — enabling fully-original consumables
  (`new_elixir(status=<your status>)`).
* Added visibility knobs to `new_status`: `apply_effect=` (a VFX GUID played
  on application, e.g. the healing potion's swirl) and `property_flags=`
  (`StatusPropertyFlags`). By default no flags are emitted, so custom
  statuses announce themselves via overhead text, combat log, and portrait
  indicator — the channels retail's `POTION_OF_HEALING` explicitly disables.
* Mapped BG3's four item text slots by dissecting retail's Elixir of
  Bloodlust: `display_name` (item name), `description` (italic flavor),
  `effect_description` (the golden effect blurb — `TechnicalDescription`,
  which supports `<LSTag ...>` hyperlink markup passed through verbatim),
  and `on_use_description` (just the use-verb label, "Drink"). Unset slots
  inherit the `parent_template`'s text. Also added `description_params=` to
  `new_status` (`DescriptionParams` — values substituted into `[1]`, `[2]`
  placeholders).
* Corpus-verified the authoring wiring with `scripts/wiring_survey.py`
  (all 25,564 retail templates): the text-slot map and typed action
  attributes hold everywhere; the scroll `ClassId` proved optional (now
  `class_id=None` omits it) and `StatusDuration` documented as turns, not
  just 0/-1. The survey is a rerunnable patch-drift check.
* Added `mod.new_spell(...)`: define a *custom* spell (`type "SpellData"`)
  by cloning a retail base — `using="Projectile_FireBolt"` inherits the
  targeting/animation/sound/VFX plumbing while overrides carry the identity
  (localized name/description/icon) and effect (`spell_roll`,
  `spell_success`, `spell_properties`, `tooltip_damage`, `damage_type`).
  From-scratch definitions take `spell_type=` plus explicit `data`. The
  returned name wires into `new_scroll(spell=…)` and `grants_spells=[…]`,
  completing the fully-original consumable chain (custom spell + custom
  status + the items that deliver them, all in one mod).
* Added consumables: `mod.new_potion(status=…)` and `mod.new_elixir(status=…)`
  (a Consume template action applying a status — duration 0, or -1 until long
  rest) and `mod.new_scroll(spell=…)` (the retail cast-from-scroll action,
  `CanUseSpellScroll`-gated). The template builder gained `on_use=` action
  children (`build_consume_action` / `build_use_spell_action`) with attribute
  types pinned from retail templates (`int32`/`bool`/`guid`/…).

## 0.1.0 — 2026-07-21

First release. Everything below is validated against a full retail
install (Patch 8, 154 GB, 52 paks) — see `docs/baseline.md` for the
numbers and `docs/retail-testing.md` for how to reproduce them.

### Formats

* LSPK `.pak` archives v15–v18: reader, writer, multi-part archives,
  LZ4/zlib/zstd entries, incremental extraction, patch detection
* Stats `.txt` with `using` inheritance, patch layering (self-`using`
  overrides), and `key` global constants
* Localization `.loca` (read/write) with handle-version precedence
* Node trees in all three serializations — LSX (XML), LSF (binary,
  versions 1–7), LSJ (JSON) — parsing into one document model with
  format sniffing; `bg3forge convert` translates `.lsf` ↔ `.lsx`
* Texture atlases + DDS icon extraction to PNG/WebP (optional Pillow)
* Quest journal (`quest_prototypes.lsx`, markers) and metadata-level
  Osiris goal scripts
* Compiled Osiris stories (`story.div.osi`, versions 1.13–1.15):
  metadata traversal for headers, types, functions, databases, goals,
  and rules, plus source-goal cross-checking
* Character equipment sets from `Stats/Generated/Equipment.txt`
* Core library has **zero required dependencies** (pure-Python LZ4
  block + frame codecs included); native speedups via extras

### API

* `Game` facade: reads straight from installed paks in engine load
  order (pak priority), or from an extracted tree; everything lazy
* Typed models with a relationship graph: forward edges
  (`item.passives/.statuses/.spells/.tags/.owner_templates`,
  `quest.goals`) and reverse edges (`passive.items`, `spell.items`,
  `status.items`, `tag.items`, `game.goals_for_quest`)
* Name-addressed collections with display-name search
  (`game.items["WPN_Longsword"]`, `game.quests.find("nightsong")`)
* Indexed datasets for large families: `game.dialogs` (graph model,
  localized lines), `game.timelines` (dialog↔cinematic linkage),
  `game.goals`, and `game.story` — listing from pak indexes only, parse
  large resources per file on demand
* Runtime-facing item templates (`game.item_templates`) combine canonical
  RootTemplates with stable objects placed under module Globals/Levels and
  resolve `TemplateName` references through the RootTemplate chain
* Selected icon export (`game.export_icons`) reads DDS atlases directly
  from game paks and writes lossless PNG/WebP without an extraction step
* Exporters: deterministic JSON, SQLite, CSV, Markdown, YAML

### Tooling

* `bg3forge doctor` — install/environment diagnostics with game-data
  version detection
* `bg3forge validate` — full-coverage parse sweep with per-file
  failures and a live progress line that survives output redirection
* `bg3forge benchmark` — repeatable stage timings, counts, peak RSS
* `bg3forge search` — archived-path search (globs, directory
  aggregation) across all paks
* `unpack`, `list`, `convert`, `patches`, `icons`, and per-dataset
  export commands

### Added after the initial changelog draft

* Characters (`game.characters`): NPC/creature stat blocks with ability
  scores, joined to root templates for localized names, archetype, and
  equipment; `character.passives`, `character.tags`,
  `character.equipment_items` (loadout resolved into Item models), and
  the reverse `passive.characters` edge
* Equipment sets (`game.equipment`) parsed from
  `Stats/Generated/Equipment.txt`
* `bg3forge characters` export command; `export` covers characters
* Objectives (`game.objectives`) and quest categories
  (`game.quest_categories`) complete the journal layer, with
  `quest.objectives`, `quest.category`, `objective.markers`, and
  `category.quests` joins
* Shared cached pak readers: the full pipeline dropped from ~28.6 s to
  ~8.8 s on the retail baseline (ten stages had each re-parsed every
  pak file list)
* A real downstream consumer now sources 7,081 named items plus passives,
  statuses, placed templates, and icons through BG3 Forge; all 146 curated
  items enrich successfully and all 994 referenced gear icon keys are
  covered
