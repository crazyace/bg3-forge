# Changelog

## 0.2.0 — unreleased

### Tooling

* Added `scripts/build_data_release.py` — builds a downloadable dataset
  bundle (SQLite + JSON + CSV for items/spells/passives/statuses/
  characters/progressions/spell-lists, plus a `MANIFEST.json` recording
  the game version, `bg3forge` version, row counts, and validation
  coverage) from an installed copy of the game. Output is byte-reproducible
  for a given install. This is the *data-export release* step: the
  resolved data is published to the community — who mostly don't run
  Python — as a release asset. See [docs/data-release.md](docs/data-release.md).

### API

* Added `game.find_files(pattern)` — archived paths matching a glob or
  substring, mapped to their source pak (or extracted file), reading no
  content. `bg3forge search` is now glue around it, so other tools no
  longer need the private `_locate_entries`.
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
* Added `game.races`: race and subrace records as a `ParentGuid` tree
  (root `Humanoid` → playable races → subraces) joined to their
  progression tables, localized names/descriptions, and the tag registry.
  The retail census (156 nodes, nine attributes) pinned the schema;
  character-creation cosmetic banks are deliberately not modeled. Counted
  by `validate` — this completes the classes/races origin join,
  retail-verified: the full taxonomy renders with progression levels on
  exactly the playable branches and identity tags resolved end to end.
* Added `game.classes` (class descriptions): each class/subclass joined to
  its learnable spell list (`SpellList` + `CanLearnSpells` — the wizard
  transcription pool), its progression table, and `parent`/`subclasses`
  links, with localized display names. `game.spell_lists_containing(spell)`
  answers the class-spell authoring question "which cumulative per-level
  lists should also carry my custom spell". Class descriptions are counted
  by `validate`.
* RootTemplates now capture their `InventoryList` object references
  (`RootTemplate.inventory` / `.treasure_tables`), and
  `RootTemplateIndex.by_treasure_table(name)` returns the containers that
  fill from a treasure table. On `game.item_templates` (which includes
  placed level objects) this answers "which container drops from
  `TUT_Chest_Potions`, and what's its spawn UUID" — closing the loop with
  the authoring `treasure=` feature.

### Security

* Archive extraction now rejects two Windows-specific hazards that
  survived the traversal checks: a path component containing a colon (an
  NTFS alternate data stream, e.g. `file.txt:evil`) and a reserved
  device name (`CON`, `NUL`, `COM1`…`LPT9`, with or without an
  extension). Legitimate BG3 paths — including ones that merely start
  with a device name, like `CONtent/` — are unaffected.
* Decompression of third-party paks and mod files is now bounded so a
  crafted archive can't drive an unbounded allocation. A per-entry /
  per-section uncompressed size that is implausible for its compressed
  input (beyond DEFLATE's ~1032:1, LZ4's ~255:1, or zstd's headroom) is
  rejected as a `DecompressionBombError` before any native decompressor
  pre-allocates that many bytes; zlib inflation is self-bounded; and the
  LZ4 *frame* path (native and pure-Python) decodes against an output
  cap instead of trusting the frame's own content-size hint. Applies to
  pak entries (`PakReader.read`) and LSF sections. All errors remain
  `ValueError` subclasses, so `Game`'s per-file `load_issues` containment
  still applies.

### Docs & CI

* The README execution guard is now strict about `NameError`: blocks
  share one namespace (the README is a progressive narrative), a
  `NameError` is tolerated only for documented placeholders or names
  whose defining statement was skipped for data reasons, and total
  skips are capped. Previously a blanket `NameError` tolerance silently
  skipped 24 of 75 statements — including the entire high-level API
  block; coverage is now 59/75 with every skip accounted for.
* README notes that the released 0.1.0 predates the authoring layer and
  the progressions/classes/races graph (this README documents `main`).
* docs/mod-authoring.md no longer labels `Mod.build()`'s return value
  as the template UUID — `build` returns the pak path; the UUID is
  returned by `new_armor`/`new_item` (the doc's spawn step depends on
  it).
* Publishing now verifies the built version matches the release tag —
  a release cut today would have shipped `0.2.0.dev0` to PyPI.
* CI tests Python 3.13 (suite verified); classifiers updated.

### Fixed (game graph)

* Tag UUID joins are now case-insensitive, like every other UUID join in
  the graph: `TagRegistry` lookups, `items_with_tag`, and the tag
  reverse index all normalize to lowercase, so template attributes and
  tag files that disagree on casing still join. Tag *names* remain
  case-sensitive (canonical engine identifiers).
* Items whose stats chain carries no `Icon` now inherit the root
  template's icon, exactly like `DisplayName`/`Description` already did.
* Non-English games fall back to English for untranslated handles
  instead of resolving to empty strings. Translations always win; only
  handles the chosen language lacks entirely are filled from English
  (`Localization.merge_missing`).

### Performance

* Compiled Osiris stories parse ~30x faster. `story.div.osi` — the
  largest single file in a retail install — is dominated by scrambled
  null-terminated strings, which the reader consumed one byte at a time
  through `struct` (five Python-level calls per byte). Strings are now
  located with a single C-level scan and descrambled with one
  `bytes.translate` pass, and the fixed-width helpers use precompiled
  `Struct` objects.
* `item_templates` no longer re-parses every RootTemplate file. It now
  builds on a copy of the already-parsed `templates` index (RootTemplates
  are the largest files in the game), layering only the placed-item
  files — cutting the graph's most expensive parse in half.
* In extracted-directory mode the tree is walked and sorted once and
  cached, instead of `rglob('*')` plus a per-file `stat` on every one of
  the ~18 lazily-built collections.
* `game.timelines.for_dialog` resolves via a prebuilt stem→paths index
  instead of a full linear scan (with per-entry `rsplit`/`lower`) on
  every call.
* Pak file lists parse via a single `struct.iter_unpack` pass rather than
  a per-entry offset-and-unpack loop (~1.3x on the hundreds of thousands
  of entries in a retail install).

### Fixed (parsers)

* The stats parser no longer silently drops malformed structural lines.
  A `data`/`type`/`using`/`new entry`/`key` line that fails to parse —
  a stray trailing token, a missing close quote — used to be discarded
  with no trace; it now raises `StatsParseError` naming the line.
  Genuinely unmodeled directives (`new itemcolor`, …) are still
  tolerated. A trailing `// comment` outside quotes is stripped rather
  than defeating the line match.
* Goal scripts now honor `/* … */` block comments and trailing `//`
  comments. Retail sources comment out rules and facts with both;
  previously a block-commented `IF` inflated the rule count and
  commented-out `QuestUpdate` calls contributed phantom quest refs.
* `is_lsj` recognizes a UTF-8 BOM, so BOM-prefixed `.lsj` files are no
  longer misrouted to the XML parser (`parse_lsj` already decoded with
  `utf-8-sig`).
* `RootTemplateIndex.resolved_tags` now follows engine per-property
  inheritance: a template that defines its own `Tags` list *replaces*
  its ancestor's rather than unioning with it, so items no longer report
  tags the engine never applies. Templates without a `Tags` list still
  inherit the nearest ancestor's.
* The dialog parser captures `Jump` nodes' `jumptarget`, and
  `Dialog.walk` follows it — traversal previously dead-ended at every
  Jump.

### Fixed (parsers)

* The stats parser no longer silently drops malformed structural lines.
  A `data`/`type`/`using`/`new entry`/`key` line that fails to parse —
  a stray trailing token, a missing close quote — used to be discarded
  with no trace; it now raises `StatsParseError` naming the line.
  Genuinely unmodeled directives (`new itemcolor`, …) are still
  tolerated. A trailing `// comment` outside quotes is stripped rather
  than defeating the line match.
* Goal scripts now honor `/* … */` block comments and trailing `//`
  comments. Retail sources comment out rules and facts with both;
  previously a block-commented `IF` inflated the rule count and
  commented-out `QuestUpdate` calls contributed phantom quest refs.
* `is_lsj` recognizes a UTF-8 BOM, so BOM-prefixed `.lsj` files are no
  longer misrouted to the XML parser (`parse_lsj` already decoded with
  `utf-8-sig`).
* `RootTemplateIndex.resolved_tags` now follows engine per-property
  inheritance: a template that defines its own `Tags` list *replaces*
  its ancestor's rather than unioning with it, so items no longer report
  tags the engine never applies. Templates without a `Tags` list still
  inherit the nearest ancestor's.
* The dialog parser captures `Jump` nodes' `jumptarget`, and
  `Dialog.walk` follows it — traversal previously dead-ended at every
  Jump.

### Fixed

* `Extractor` now persists its incremental manifest even when a pak
  fails partway through (disk full, a truncated entry, KeyboardInterrupt).
  The manifest is saved in a `finally` block, so files already written
  are recorded and a re-run resumes instead of re-extracting the whole
  archive; a save failure during error unwinding never masks the
  original error.
* `Mod.add_string` no longer lets a status, spell, passive, and item
  that share a name collide onto one localization handle — the string
  keys are now qualified by content kind, so each gets its own handle
  and text.

* `write_lsx` now refuses C0 control characters (other than
  tab/newline/carriage return) in node ids, keys, and attribute
  ids/types/handles/values. XML 1.0 cannot represent them at all — not
  even as character references — but ElementTree wrote them through
  verbatim, producing documents that `parse_lsx`, the game, and every
  conforming XML parser reject. Offenders now raise `LsxError` naming
  the field; legal whitespace still round-trips exactly.

* CLI robustness: `bg3forge unpack` now reports a damaged archive on
  stderr and exits non-zero instead of silently skipping it as a
  "foreign file" — including when the corrupt pak was named explicitly,
  which used to print `done` and exit 0. `bg3forge patches` with
  `--extracted-dir` exits with a clear error instead of crashing with a
  `TypeError` traceback (`Path(None)`), and the patch-detection scan
  skips unreadable `.pak` paths (permissions, directories) instead of
  letting `OSError` escape.

* `validate_data` and `bg3forge doctor` no longer report a broken
  install as healthy. A damaged archive — LSPK signature present but the
  file list unreadable — was counted as a routine "skipped part"
  (`pak_parts_skipped`) by validate and silently skipped by doctor's
  content scan, so `report.ok` stayed true with entire paks missing from
  the sweep. Corrupt archives now produce a `stage="pak"` validation
  issue (tracked by the new `paks_corrupt` count) and a FAIL doctor
  check; genuine secondary parts and foreign files still skip silently.
  The LSPK-signature probe is shared with `Game` as
  `bg3forge.pak.reader.file_is_lspk`.

* The stats writer now refuses strings the format cannot carry. The
  stats ``.txt`` grammar has no escape syntax, so a double quote or
  newline in an entry name, type, ``using`` reference, data key/value,
  or global silently reparsed as *different* data — a value containing
  a newline could even inject whole ``data`` directives into the
  generated file. ``write_stats``/``write_stats_document`` (and
  therefore ``Mod.build``) now raise the new ``StatsWriteError`` (a
  ``ValueError``) naming the offending field instead of corrupting the
  output.

* A file re-shipped by a higher-priority archive now overrides the base
  copy wholesale, as the engine loads it. `_iter_files` previously
  yielded *every* copy of a matching archived path from every pak, so
  the collections built by extension — quests, objectives, markers,
  categories, treasure tables, atlases, equipment — contained both the
  stale and the patched records after any patch or mod override, and
  every reverse index built from them (objectives-for-quest,
  quests-in-category, markers-by-id) returned duplicates. Record-level
  layering across distinct paths (stats `using` chains, `.loca`
  versions, progression UUIDs) is unchanged, and the lazy indexes
  already used the same last-wins rule via `_locate_entries`.

* LSPK v15/v16 archives (DOS2 DE, BG3 Early Access) are now actually
  readable. Both advertised versions were parsed with the v18 272-byte
  entry layout, but real v15/v16 entries are 296 bytes (LSLib's
  `FileEntry15`, with u64 offset/size fields), and the v15 header carries
  no `num_parts` — so opening any genuine legacy archive failed with an
  uncaught size-mismatch error. `PakReader` now selects the header and
  entry layout by version, and `PakWriter` rejects legacy versions
  instead of stamping them onto v18 structures.

* Malformed binary files can no longer crash whole collection loads.
  `Game` documents that a bad file is recorded in `load_issues` and
  skipped, but the binary parsers leaked `struct.error`, `zlib.error`,
  `IndexError`, and native-LZ4 exceptions — none of them `ValueError`
  subclasses — past every `except ValueError` containment, so one
  truncated `.pak` or `.lsf` (an interrupted download or patch) aborted
  `Game()`, `validate_data()`, and `run_doctor()`. All parser entrypoints
  now hold their documented error contract: `parse_lsf` raises `LsfError`
  for any malformed input (guaranteed by a contract wrapper plus targeted
  guards), `parse_loca` validates its entry table up front, `PakReader`
  rejects truncated file lists and implausible file counts as `PakError`,
  and both LZ4 backends raise `LZ4Error`. A byte-flip sweep over a full
  LSF resource pins the contract in CI.
* Corrupt LSF adjacency data can no longer hang the parser: attribute
  chains with cyclic or out-of-range `first_attr`/`next_attr` links, and
  `TranslatedFSString` values with negative lengths or unbounded argument
  nesting, now raise `LsfError` instead of looping or recursing forever.
  Attribute value lengths are validated against their type before
  decoding.
* Native LZ4 block decompression silently returned *short* output when
  the expected size field was larger than the actual content;
  `lz4compat.decompress` now enforces the exact size with both backends,
  and the pure-Python decoder rejects truncated literal runs it
  previously truncated silently.
* A damaged archive with a valid LSPK signature is now recorded in
  `Game.load_issues` instead of being silently skipped as a "foreign
  file" — a corrupt primary pak previously vanished with no diagnostic
  anywhere.

* LSF guid attributes now render in canonical text form. Larian stores
  the last two guid groups as little-endian 16-bit words; earlier
  releases rendered those bytes swapped (e.g. the scroll ClassId read as
  `…-aa9e-4877c0e8094d` instead of `…-9eaa-7748e8c04d09`). On-disk bytes
  were always correct — reader and writer were symmetric — so packs and
  round trips are unaffected; only text comparisons across formats (LSF
  guid vs. LSX/stats text) saw the mismatch. Found when the scroll
  `ClassId` turned out to be the Wizard ClassDescription UUID (the class
  marked `IsDefaultForUseSpellAction`).

* README Python snippets are now executed by the test suite
  (`tests/test_readme.py`): each ```python block runs statement-by-
  statement against the synthetic fixture game, so renamed APIs, wrong
  signatures, or syntax errors in the docs fail CI. Only data-dependent
  misses (retail names the fixture lacks, illustrative placeholders) are
  tolerated.

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
  status + the items that deliver them, all in one mod). Retail-verified:
  a scroll of a cloned Fire Bolt cast in game with the overridden 3d10
  damage, auto-derived damage tooltip, and inherited range/cost/visuals —
  confirming the scroll action and `CanUseSpellScroll` accept modded
  SpellData names.
* `add_class_spell` supports cantrips: the level guard is symmetric, so
  `level=0` extends exactly the class's cantrip lists (clone a cantrip
  base like `Projectile_FireBolt` to inherit `Level 0` and the slotless
  cost). Covered by a fixture cantrip list wired into the wizard's
  level-1 selectors.
* Added `add_class_spell(game, mod, class_name, spell, level=…)`: makes a
  custom spell a real class spell by extending every list the class
  selects from (progression `SelectSpells`) or prepares/learns from
  (`ClassDescription` pool) that already carries spells of that level —
  cantrip lists are never polluted, and lists already containing the
  spell are skipped. The read side supplies current lists so the mod
  tracks the installed patch. Works for classes without a convenient
  sibling spell (e.g. adding a Misty Step clone to Bard).
* `new_scroll` now emits the ActionType 33 learn action (`SpellId`)
  alongside the cast action, making scrolls wizard-transcribable by
  default (`learnable=False` for cast-only, retail's pattern for
  unteachable spells). Found by diffing our scroll against retail's in
  the live engine after list membership alone produced no "Learn Spell" —
  which also corrects the survey catalog's ActionType 33 entry ("secondary
  cast variant" → the transcription action; its 111 occurrences are
  retail's learnable scrolls).
* Added teachable spells: `mod.replace_spell_list(uuid, spells, name=…)`
  ships a full spell-list replacement (`Lists/SpellLists.lsx`, backed by
  new `build_spell_list_node`/`build_spell_lists_document` writers).
  Adding a custom spell to the Wizard ClassDescription's list
  (`WIZARD_LEARNABLE_LIST`) makes its scroll transcribable — "Learn
  Spell" for 50 gp × level. Traced through retail: learnability is pure
  list membership (wizard progressions carry `SelectSpells` only at
  level 1); the game swaps lists wholesale, so extending one means
  re-shipping its current spells plus yours (documented conflict caveat).
  `SpellList.display_name` now reads the retail `Name` attribute.
* Added `cooldown=` to `new_spell` and made `use_costs=""` an explicit
  empty override, completing the hotbar casting-economy recipes learned
  from retail's Misty Step family: leveled slot costs
  (`SpellSlotsGroup:1:1:N`), item free-casts recharging per short rest
  (`OncePerShortRestPerItem`), per-long-rest and per-turn cooldowns, and
  fully free casts. Retail items grant spells with the bare
  `UnlockSpell(...)` form `grants_spells` already emits.
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
