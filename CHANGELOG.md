# Changelog

## 0.1.0 — unreleased

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
  `game.goals` — listing from pak indexes only, parse per file on
  demand
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
