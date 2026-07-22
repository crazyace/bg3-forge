# BG3 Forge

BG3 Forge is an open-source toolkit for extracting, parsing, and exporting
Baldur's Gate 3 assets and game data into developer-friendly formats.

## Why?

Building anything on top of BG3 data today means scraping community wikis
(incomplete, unversioned, rate-limited) or hand-rolling a pipeline of
unpacking tools, format converters, and one-off scripts — and redoing it
after every game patch.

BG3 Forge replaces that with a reproducible, offline pipeline that reads
the original data directly from **your installed copy** of the game: pak
archives, stats, localization, templates, and icons in, clean datasets and
a typed Python API out. Same input, byte-identical output, every time.

**Library first, CLI second.** Every feature is implemented as a reusable
Python module; the `bg3forge` command is a thin layer of glue on top. Other
projects can import the library directly instead of invoking external
scripts.

## What it looks like

BG3 Forge doesn't just unpack files — it *understands* the data. Values
are resolved across sources (stats inheritance, RootTemplates,
localization, atlases) so you never need to know where they came from:

```python
from bg3forge import Game

game = Game()  # auto-locates the install (or pass path= / data_dir=)

sword = game.items["WPN_Longsword"]  # or any magic item's stats name
sword.display_name      # localized name, via RootTemplate + .loca
sword.description       # localized description
sword.icon              # atlas icon name
sword.rarity            # from stats, `using` inheritance applied
sword.requirements      # ["Str 13"]
sword.tags              # [Tag(...)] named, localized, from the template chain
sword.owner_templates   # RootTemplates whose Stats point at this entry
sword.passives          # [Passive(...)] granted on equip
sword.statuses          # [Status(...)] applied on equip
sword.spells            # [Spell(...)] unlocked by the item's boosts

# ...and the graph works backwards, too:
game.passives["ExtraAttack"].items      # items granting a passive
game.spells["Projectile_Fireball"].items  # items unlocking a spell
game.statuses["BURNING"].items          # items applying a status
game.tags["LONGSWORD"].items            # items carrying a tag (by name or UUID)

# Dialogs are indexed, not eagerly parsed (there are ~9,400 of them):
game.dialogs.find("Karlach")            # search archived paths — free
dialog = game.dialogs.load(path)        # parses just this one file
game.dialogs.lines(path)                # (speaker, localized text) pairs
game.timelines.for_dialog(dialog)       # the cinematic staging the dialog

# Quests join the graph too:
quest = game.quests["PLA_ZhentShipment"]
quest.title                             # localized quest title
quest.steps[0].description              # localized journal entry
quest.goals                             # Osiris goal scripts driving the quest
quest.category.display_name             # journal section, localized
quest.objectives[0].markers             # objective -> map marker join
game.quest_markers                      # localized map markers

# Compiled Osiris stories are large, so they parse one file at a time:
story_path = game.story.paths[0]
story = game.story.load(story_path)
story.header.version                    # "1.15"
story.goals[0].name                     # compiled goal metadata
story.databases[0].name                 # database name/signature metadata
game.uncompiled_goals()                 # source goals absent from all compiled stories

# ...and so do characters:
goblin = game.characters["GOB_Warrior_Melee"]
goblin.display_name                     # localized, via its template
goblin.strength, goblin.vitality        # stat block with `using` inheritance
goblin.passives                         # [Passive(...)]
goblin.equipment_items                  # loadout resolved into Item models
game.passives["SavageAttacks"].characters  # reverse: who has this passive

game.items.find("longsword")   # search by name / display name
for spell in game.spells:
    print(f"[{spell.level}] {spell.display_name}: {spell.damage}")
```

Everything resolves **lazily**: constructing `Game()` reads nothing,
collections load on first access, and each relationship is resolved once
and cached on the instance. You only pay for the data you actually touch.

And from the command line:

```console
$ bg3forge export json -o export
exported 12842 items
exported 4051 spells
exported 1876 passives
exported 2410 statuses
```

(Counts are illustrative — they depend on your game version.)

```console
$ bg3forge list Shared.pak
$ bg3forge search "journal"   # find archived paths across all paks — fast
$ bg3forge unpack -p "*/Stats/*" -o extracted
$ bg3forge spells -f json -o spells.json
$ bg3forge items -f csv -o items.csv
$ bg3forge export sqlite -o export
$ bg3forge icons Icons_Items.lsx Icons_Items.dds -o icons -f webp
$ bg3forge convert Weapons.lsf Weapons.lsx
$ bg3forge patches --update
$ bg3forge doctor       # diagnose the install and environment
$ bg3forge validate     # parse everything, report any file that fails
$ bg3forge benchmark    # repeatable stage timings + peak RSS
```

`doctor` answers "is it my setup or the tool?" before anything else:

```console
$ bg3forge doctor
✓ Python — 3.11.15
✓ Native LZ4 — available
✓ BG3 installation — /home/you/.steam/steam/steamapps/common/Baldurs Gate 3
✓ Pak archives — 34 readable (v18), 12 part files
✓ Shared.pak — present
✓ Game data version — 4.68.1.200 (module Gustav)
✓ English localization — present

Warnings
--------
None
```

## Installation

```console
pip install bg3forge            # core: zero dependencies
pip install "bg3forge[all]"     # native LZ4, zstd, icon pipeline, YAML
```

The core library has **no required dependencies** — it includes a
pure-Python LZ4 block codec. For full-game unpacks install the `lz4` extra
for native-speed decompression.

| Extra   | Enables                                        |
| ------- | ---------------------------------------------- |
| `lz4`   | native-speed LZ4 (strongly recommended)        |
| `zstd`  | zstd-compressed pak entries                    |
| `icons` | DDS atlas decoding, PNG/WebP export (Pillow)   |
| `yaml`  | YAML exporter (PyYAML)                         |

## Features

### Asset extraction (`bg3forge.pak`)

* Read LSPK `.pak` archives directly (v15/v16/v18, multi-part archives,
  LZ4/zlib/zstd entries) — `PakReader`
* Incremental extraction with a content-hash manifest: re-runs only write
  files whose archived bytes changed — `Extractor`
* Automatic patch detection via data-directory fingerprint snapshots —
  `PatchDetector`
* Selective extraction with glob patterns (`-p "*/Stats/*"`)
* `PakWriter` for building archives (fixtures, repacking)

### Game data parsing (`bg3forge.parsers`)

* **Stats** `.txt` (weapons, armor, objects, spells, passives, statuses,
  interrupts) with full `using` inheritance resolution — `StatsCollection`
* **Localization** `.loca` binary archives with handle→text lookup and
  version precedence — `Localization`
* **LSX** node trees (XML) — `parse_lsx` / `write_lsx`
* **LSF** node trees (binary, versions 1–7 incl. current BG3 keyed-node
  output; zlib/LZ4-frame/zstd section compression) — `parse_lsf` /
  `write_lsf`
* **LSJ** node trees (JSON, e.g. editor-side dialogs) — `parse_lsj`.
  All three serializations parse into the *same* document structure,
  and `parse_resource` sniffs the format, so downstream code never
  cares which one the game shipped
* **RootTemplates** (`.lsx` or `.lsf`) with `ParentTemplateId`
  inheritance — `RootTemplateIndex` (see *Mod authoring* for building new
  ones)
* **Progressions** (class/race level tables) and referenced spell lists —
  `parse_progressions` / `parse_spell_lists`
* **Treasure tables** — `parse_treasure_tables`
* **Tag registry** (`Tags/*.lsx|.lsf`) — UUID/name lookup with categories
  and localized display strings — `TagRegistry`
* **Dialogs** (`Story/DialogsBinary/**.lsf`) — node graphs with
  constructors, speakers, flow edges, and text handles — `parse_dialog`
* **Quest journal** (`Story/Journal/`) — quest catalog with steps,
  rewards, objectives, categories, localized titles/descriptions, and
  map markers —
  `parse_quests` / `parse_markers`
* **Osiris goal scripts** (`Story/RawFiles/Goals/*.txt`) — metadata
  level: sections, rule counts, and which quests/steps each goal's
  logic touches — `parse_goal`
* **Compiled Osiris stories** (`Story/story.div.osi`, versions 1.13–1.15)
  — metadata-level traversal of headers, types, functions, databases,
  goals, and rules — `parse_osiris`
* **Equipment sets** (`Stats/Generated/Equipment.txt`) — character
  loadouts with weapon sets and slot groups — `parse_equipment_sets`
* `bg3forge convert` converts `.lsf` ↔ `.lsx` from the command line — no
  lslib/divine required

### Mod authoring (experimental)

The inverse of everything above: generate a mod programmatically. A `Mod`
mints stable UUIDs and localization handles, lays files out under the
folder convention BG3 expects, and packs a `.pak` — writing only to the
output path you choose, never to your install.

```python
from bg3forge import Mod

mod = Mod("SunforgedArmors", author="you")
mod.new_armor(
    "ARM_Sunforged_Plate",
    armor_class=21,
    stats_using="_Armor",                 # inherit stats from a base entry
    parent_template="<base-template-uuid>",  # reuse an existing item's visuals
    display_name="Sunforged Plate",       # localized; a handle is minted for you
    description="Warm to the touch.",
    icon="Item_Plate_Body",
    boosts=["Ability(Strength,2)"],       # applied on equip
    grants_spells=["Target_Fireball"],    # added as UnlockSpell(...)
)
mod.build("SunforgedArmors.pak")          # stats + template + meta + loca → pak
```

Rebuilding the same mod reproduces byte-identical identifiers (UUID5 from
the mod name). Under the hood it composes the write primitives:

* **Stats content** — `write_stats` / `write_stats_document`
* **Item templates** — `build_root_template_node` /
  `build_templates_document` (with `ParentTemplateId` to reuse visuals)
* **Module manifest** — `build_meta_document` (+ `parse_meta`)
* **Version64** — `pack_version64` / `unpack_version64`
* plus the existing `.loca` writer and `PakWriter`

**Retail-verified:** a capstone-built mod loads in a Patch 8 game — the
item spawns, its stats and localized name/description resolve, the icon
inherits, and equip boosts apply to the character. See
[`docs/mod-authoring.md`](docs/mod-authoring.md) for the load-test steps
and [`docs/baseline.md`](docs/baseline.md) for the verified result.

### Icon pipeline (`bg3forge.assets`)

* Parse texture atlas definitions (`IconUVList` LSX)
* Slice icons out of DDS atlases, preserving original quality
* Export individual PNG or WebP files
* Automatically match icons on items/spells to the atlas containing them —
  `match_icons`

### Data export (`bg3forge.exporters`)

JSON, SQLite, CSV, Markdown, and YAML — all deterministic: identical
inputs produce byte-identical exports.

```python
from bg3forge.exporters import export_sqlite
export_sqlite(game.spells, "bg3.db", table="spells")
```

### High-level API

`Game` ties it all together: it reads stats, localization, root templates,
tags, atlases, and treasure tables straight out of the installed `.pak`
archives (no extraction step needed) or from a previously extracted tree,
and joins them into typed models (`Item`, `Spell`, `Passive`, `Status`,
`Tag`) with resolved inheritance and localized display text. Dialogs are
exposed through a lazy `DialogIndex` (`game.dialogs`) that lists from the
pak indexes and parses per file on demand.

Collections support list iteration, name lookup, and search:

```python
game = Game(path="/path/to/Baldurs Gate 3")     # or data_dir= / extracted_dir=
game = Game(language="German")                   # localization language

game.spells["Projectile_Fireball"]               # lookup by stats name
game.items.find("amulet")                        # search names + display names
game.items.get("WPN_Maybe", default=None)        # tolerant lookup
game.item_templates                               # RootTemplates + placed global items
levels = game.progressions.by_table(table_uuid)   # ordered level records
levels[0].passives                                # resolved Passive models
levels[0].spells                                  # automatic AddSpells grants
levels[0].selectable_spells                       # SelectSpells choices
game.export_icons(                                # read atlases from paks, write WebP
    {item.icon for item in game.items if item.icon}, "assets/icons"
)
```

`game.item_templates` mirrors the runtime's item-template view. It includes
stable story-facing objects from `Mods/*/{Globals,Levels}/*/Items` and resolves
their `TemplateName` references back through the RootTemplate inheritance
chain. Use `game.templates` when only canonical RootTemplates are wanted.

Models form a relationship graph rather than isolated records. Forward
edges resolve an object's references (`item.passives`, `item.spells`,
`item.statuses`, `item.owner_templates`, `item.tags`); reverse edges
answer "who references me?" (`passive.items`, `spell.items`,
`status.items`, `passive.progressions`, `spell.progressions`, backed by
one-pass indexes built on first use). Progression spell grants and choices
stay distinct: ``AddSpells`` feeds ``progression.spells`` while
``SelectSpells`` feeds ``progression.selectable_spells``. All
edges resolve lazily and are cached per instance — treat them as
read-only snapshots. The raw resolved stats stay available via
`obj.data` when you need a field the typed model doesn't surface.

The install is auto-located via `$BG3_PATH` and well-known Steam/GOG paths
on Windows, macOS, and Linux.

## Goals

* Work completely offline
* Never depend on community wikis
* Stay compatible with new BG3 patches (patch detection + incremental extraction)
* Produce deterministic exports
* Make BG3 data easy to consume for websites, tools, and mods
* Pay for complexity only when the data demands it — see the
  [design principles](CONTRIBUTING.md#design-principles)

## Project layout

```
src/bg3forge/
├── pak/            # LSPK reader/writer, incremental extractor, patch detection
├── parsers/        # stats, loca, lsx, lsf, lsj, osiris, roottemplates,
│                   # tags, dialogs, progressions, spell lists, treasure
├── assets/         # texture atlases, icon extraction
├── exporters/      # json, sqlite, csv, markdown, yaml
├── cli/            # thin argparse front-end
├── models.py       # typed domain models (Item, Spell, Passive, Status)
├── game.py         # Game facade, relationship graph, DialogIndex
├── locate.py       # install discovery
├── doctor.py       # install/environment diagnostics
├── validate.py     # format-coverage sweep
└── benchmark.py    # repeatable pipeline measurements
```

## Roadmap

* ✅ PAK reader/writer (LSPK v15–v18, multi-part, incremental extraction)
* ✅ Patch detection
* ✅ Stats parser with `using` inheritance
* ✅ Localization (`.loca`) parser
* ✅ LSX parser/writer
* ✅ LSF (binary) parser/writer + `bg3forge convert`
* ✅ RootTemplate parser with parent-template inheritance
* ✅ Placed item templates with `TemplateName` → RootTemplate inheritance
* ✅ Atlas definitions + icon extraction (PNG/WebP)
* ✅ Progressions and treasure tables
* ✅ JSON / SQLite / CSV / Markdown / YAML exporters
* ✅ Typed Python API with cross-source resolution
* ✅ Relationship graph (forward + reverse edges, lazy + cached)
* ✅ `bg3forge doctor` — install/environment diagnostics with game
  version detection
* ✅ `bg3forge validate` — format coverage sweep with per-file failures
* ✅ `bg3forge benchmark` — repeatable stage timings and peak RSS
* ✅ Validated against a full retail install — every recognized file
  parses cleanly; see [docs/baseline.md](docs/baseline.md) for the
  numbers (~14.6 s for the full pipeline, 826 MB peak)
* ✅ Tag registry (`game.tags`) — tag UUIDs resolve to named, localized
  `Tag` objects, with the reverse `tag.items` edge
* ✅ Dialog metadata (`game.dialogs`) — lazy indexed access to dialog
  graphs: speakers, flow edges, localized lines
* ✅ Timeline (cinematic) index (`game.timelines`) with dialog↔timeline
  linkage; internals unmodeled so far
* ✅ LSJ (JSON) resource format — the third serialization, covering
  editor-side dialogs
* ✅ Quest journal (`game.quests`, `game.quest_markers`,
  `game.objectives`, `game.quest_categories`) — the complete journal
  layer: localized quests, steps, objectives (with marker links),
  categories, and quest↔goal cross-links
* ✅ Osiris goal metadata (`game.goals`) — lazy index over the shipped
  quest-logic source, with quest references extracted
* ✅ Compiled Osiris metadata (`game.story`) — lazy `story.div.osi`
  index with goal/database/function signatures, rule counts, validation,
  and source↔compiled goal cross-checking
* ✅ Characters (`game.characters`) — NPC stat blocks joined to
  templates: abilities, passives, tags, and equipment resolved to items
* ✅ Equipment sets (`game.equipment`)
* ✅ First real consumer integration — item, passive, status, template,
  and icon datasets generated entirely through BG3 Forge; the integration
  drove placed-template coverage and direct in-pak icon export
* ✅ PyPI release — [0.1.0 is available](https://pypi.org/project/bg3forge/0.1.0/)
* ✅ Typed progression graph (`game.progressions`) — classes/races → level
  records → granted `AddSpells` and selectable `SelectSpells`, resolved
  spell lists and passives, with reverse links on `Spell`/`Passive`
* ✅ Mod authoring — a `Mod` capstone assembles stats, RootTemplate
  (`_merged.lsf`), `meta.lsx`, and localization into a `.pak`, with
  equip boosts/passives/statuses/spells; **retail-verified in a Patch 8
  game** (item spawns, stats + localized text resolve, boosts apply)
* ⏳ Virtual texture (GTS/GTP) atlas support
* ⏳ GR2 model metadata
* ⏳ Full Osiris rule decompilation — metadata traversal is complete;
  reconstructing executable rule semantics remains intentionally separate

## Development

```console
pip install -e ".[dev]"
pytest
```

The test suite builds real LSPK/`.loca`/LSF fixtures in memory, so it
runs without a game install. See [CONTRIBUTING.md](CONTRIBUTING.md) for
setup, style, and pull-request guidelines, and
[docs/retail-testing.md](docs/retail-testing.md) for running the
validation sweep against a real install.

## Legal

BG3 Forge reads data from **your own legally purchased copy** of Baldur's
Gate 3. It ships no game assets and is not affiliated with Larian Studios.

## License

MIT
