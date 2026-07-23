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
game.spells["Shout_Rage"].progressions  # class/level progressions that grant it
game.classes["Wizard"].spell_list       # the pool wizards learn/transcribe from
game.races["Elf"].subraces              # the race tree (High Elf, Wood Elf, ...)

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

And it doesn't only *read* the game — Forge writes mods back into it. A
`Mod` composes the same models into a loadable `.pak`, retail-verified in
a Patch 8 game all the way from equip boosts to custom spells appearing
in the class level-up picker:

```python
from bg3forge import Mod

mod = Mod("MyArmors", author="you")
mod.new_armor(
    "ARM_Sunforged",
    armor_class=21,
    stats_using="_Armor",                 # inherit stats from a base entry
    parent_template="<base-template-uuid>",  # reuse an existing item's visuals
    display_name="Sunforged Plate",       # a localization handle is minted for you
    boosts=["Ability(Strength,2)"],       # applied on equip
)
mod.build("MyArmors.pak")
```

See [Mod authoring](#mod-authoring-experimental) below for the full API.

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
$ bg3forge lint MyMod.pak                        # check your own mod's consistency
$ bg3forge --data-dir "…/Data" lint MyMod.pak    # …and resolve its base-game references
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
✓ Game data version — 4.1.1.4859133 (module GustavDev)
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

> **Note:** this README documents the `main` branch. The released
> [0.1.0](https://pypi.org/project/bg3forge/0.1.0/) predates the mod
> authoring layer (`Mod`, `new_armor`, …) and the
> progressions/classes/races graph — for those, [install from
> source](#development) until 0.2.0 ships.

The core library has **no required dependencies** — it includes a
pure-Python LZ4 block codec, so it installs and runs anywhere Python does.
Every extra is either a *speedup* or *feature-specific*; none is required
for correctness, so you only add what you use.

| Extra   | Enables                                        |
| ------- | ---------------------------------------------- |
| `lz4`   | native-speed LZ4 (pure-Python fallback works, just slower) |
| `zstd`  | reading zstd-compressed pak entries            |
| `icons` | DDS atlas decoding, PNG/WebP icon export (Pillow) |
| `yaml`  | YAML exporter (PyYAML)                          |

**Which should I install?**

* **Embedding bg3forge in your own project** → bare `bg3forge`, then add
  only the extras your code path needs. The zero-dependency core keeps you
  from forcing native packages (Pillow, lz4, …) onto *your* users, and it
  installs in minimal or locked-down environments where compiled wheels
  aren't available.
* **CLI, unpacking the full game** → `bg3forge[lz4]` at minimum; native
  LZ4 is a large speedup over ~150 GB of archives.
* **Working with icons** → add `[icons]` (Pillow).
* **Want everything in one command** → `[all]`.

The extras (`lz4`, `zstd`, `icons`) are native/compiled packages, so a
smaller install also means less to build, less to audit, and fewer places
an install can fail.

## Embedding BG3 Forge

BG3 Forge is built to be built *on*. If you're making a mod-planning
site, a data browser, a Discord bot, a GUI over the game data, or your
own authoring pipeline, embed the library instead of shelling out to the
CLI — every command is a thin wrapper over an importable module.

**As a dependency.** The zero-dependency core makes Forge safe to depend
on: it won't force native packages (Pillow, lz4, …) onto *your* users,
and it installs anywhere Python does. Add only the extras your code path
needs.

```toml
# pyproject.toml
dependencies = ["bg3forge>=0.2,<0.3"]        # pin the minor while pre-1.0
```

**Bundled into a standalone tool.** Because the core has no compiled
dependencies, Forge freezes cleanly into a single executable
(PyInstaller, etc.) — nothing fragile to match against your users'
machines. Ship a GUI or CLI with the game-data engine baked in.

**Typed.** The package ships a `py.typed` marker (PEP 561), so your type
checker sees Forge's annotations — `game.find_files(...)` resolves to
`dict[str, Path]`, not `Any`.

**API stability.** Pre-1.0, the public API may change at *minor*
versions (0.2 → 0.3); patch releases won't break it. Pin `>=0.2,<0.3` and
watch the changelog. Everything exported from `bg3forge` (and the
documented `bg3forge.lint` / `bg3forge.validate` / `bg3forge.doctor`
entry points) is public surface; names with a leading underscore are not.

**A favor.** If you ship something built on BG3 Forge, a credit and a
link back are appreciated — and please keep the LSLib credit in the chain
(see [Acknowledgements](#acknowledgements)). If you hit a rough edge in
the API, open an issue; consumer feedback is how the surface gets better.

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
  ones); `game.item_templates.by_treasure_table("TUT_Chest_Potions")` finds
  the containers that fill from a treasure table (and their spawn UUIDs)
* **Progressions** (class/race level tables) and referenced spell lists —
  `parse_progressions` / `parse_spell_lists`
* **Class & race descriptions** — `game.classes` / `game.races`: the
  origin joins (learnable spell pools, `ParentGuid` class/race trees,
  progression-table links) — `parse_class_descriptions` / `parse_races`
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

### Mod authoring

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
    treasure="TUT_Chest_Potions",         # drops from the tutorial chest
)
status = mod.new_status("SUN_BLESSING",   # a custom status...
    boosts=["Ability(Strength,2)"], display_name="Sun's Blessing")
mod.new_potion("OBJ_Sunforged_Brew",      # ...applied by drinking this
    status=status, treasure="TUT_Chest_Potions")
spell = mod.new_spell("Projectile_Sunbolt",  # a custom spell cloned from
    using="Projectile_FireBolt",             # a retail base (visuals/sounds
    display_name="Sunbolt",                  # inherit; effects override)
    spell_success=["DealDamage(2d10,Fire,Magical)"])
mod.new_scroll("OBJ_Scroll_Sunbolt",      # ...cast from a scroll by anyone
    spell=spell)                          # (wizards can also Learn it once the
mod.build("SunforgedArmors.pak")          # spell joins their list — see below)
```

(Also available: `new_weapon`, `new_elixir`, `new_passive`, and
`place_in_treasure` — each one keyword-level sugar over the same
pipeline.)

To make a custom spell a real *class spell* — offered in the level-up
picker, prepared lists, and wizard transcription — bridge the read and
write sides with `add_class_spell`. It reads the class's current spell
lists from your installed game and ships them back extended, skipping
lists of the wrong level (`level=0` targets the cantrip lists):

```python
from bg3forge import Game, Mod, add_class_spell

game, mod = Game(), Mod("SunstepForBards")
spell = mod.new_spell("Target_Sunstep", using="Target_MistyStep",
    display_name="Sunstep", icon="Spell_Conjuration_DimensionDoor")
add_class_spell(game, mod, "Bard", spell, level=2)
mod.build("SunstepForBards.pak")
```

Rebuilding the same mod reproduces byte-identical identifiers (UUID5 from
the mod name). Under the hood it composes the write primitives:

* **Stats content** — `write_stats` / `write_stats_document`
* **Item templates** — `build_root_template_node` /
  `build_templates_document` (with `ParentTemplateId` to reuse visuals,
  and `on_use` consume/cast actions for consumables)
* **Module manifest** — `build_meta_document` (+ `parse_meta`)
* **Spell lists** — `build_spell_list_node` / `build_spell_lists_document`
  (behind `replace_spell_list` / `add_class_spell`)
* **Version64** — `pack_version64` / `unpack_version64`
* plus the existing `.loca` writer and `PakWriter`

**Retail-verified in a Patch 8 game:** items drop from base-game chests
with resolved stats, text, and icons; equip boosts, custom passives, and
custom statuses apply; potions and scrolls consume and cast; a custom
spell cast from its scroll; a wizard *learned* a custom spell from its
scroll (transcribe dialog, gold cost, spellbook cast); and custom spells
appeared in the class level-up picker — a leveled spell for a Sorcerer
and a cantrip — chosen and cast like any base-game spell. See
[`docs/mod-authoring.md`](docs/mod-authoring.md) for the load-test steps
and [`docs/baseline.md`](docs/baseline.md) for the verified results.

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
`Tag`, `ClassDescription`, `Race`) with resolved inheritance and
localized display text. Dialogs are
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
│                   # tags, dialogs, progressions, spell lists, classes,
│                   # races, treasure
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
* ✅ Class & race origin joins (`game.classes`, `game.races`) — learnable
  spell pools, prepared-vs-selection flags, the `ParentGuid` race tree,
  and tag links; **retail-verified** against all 70 class and 156 race
  records
* ✅ Mod authoring — a `Mod` capstone assembles stats, RootTemplate
  (`_merged.lsf`), `meta.lsx`, localization, treasure tables, and spell
  lists into a `.pak`: armor, weapons, consumables (potions/elixirs/
  scrolls), and custom passives, statuses, and spells — deliverable as
  equipment grants, castable scrolls, wizard-transcribable scrolls, and
  class level-up choices down to cantrips; **retail-verified in a Patch 8
  game** for every delivery path
* ⏳ Virtual texture (GTS/GTP) atlas support
* ⏳ GR2 model metadata
* ⏳ Full Osiris rule decompilation — compiled-story *metadata* (goals,
  databases, function signatures, rule counts) is exposed; reconstructing
  executable rule *logic* back to readable source is a separate, much
  larger project with no current consumer — read the shipped `.txt`
  goals (`game.goals`) for logic today

### Where this is going — community direction

The library and the parsers are mature; the focus now is on getting
BG3 Forge's *output* to the people who need it, most of whom don't write
Python:

* 🔜 **Data exports per patch** — the resolved item/spell/passive/status/
  character datasets published as downloadable SQLite + CSV bundles on
  each release, so wiki editors, planner sites, and spreadsheet
  theorycrafters can consume Forge's data without running anything.
  Generated locally from a real install (see
  [docs/data-release.md](docs/data-release.md)) and attached to the
  GitHub release; the tool is what regenerates them each patch.
* ✅ **`bg3forge lint`** — point it at *your own* mod `.pak` and get its
  internal consistency checked: is the `meta.lsx` module manifest present
  and its `Folder` consistent (the #1 "mod doesn't show up" bug, and it
  applies to *any* mod — assets and scripts included), does everything
  parse, are UUIDs well-formed, do `DisplayName` handles have `.loca`
  entries, and — with `--data-dir` pointing at an install — do `using`
  chains and equip references (passives/statuses/unlocked spells) resolve
  against the base game. Catches the mistakes that ship broken mods,
  before upload.
* 🔮 **Cross-patch data diff** — record-level "what changed between Patch
  N and N+1" (stats added/removed/changed, renamed boosts), the thing
  that silently breaks mods.
* 🔮 **`bg3forge lookup <name>`** — resolve a name ↔ display name ↔ UUID
  ↔ handle ↔ what grants it, the lookup modders do constantly.

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

## Acknowledgements

BG3 Forge stands on a decade of community reverse-engineering work, and
some debts deserve naming:

* **[LSLib](https://github.com/Norbyte/lslib)** by **Norbyte** — the
  reference implementation for Larian's file formats. BG3 Forge is an
  independent implementation (no LSLib code is used), but our LSPK, LSF,
  and compiled-Osiris struct layouts follow LSLib's serializers and are
  verified against them; where the two disagree, LSLib is presumed
  right. If you need GR2 models, granular editing, or the widest format
  coverage, use LSLib — it is the standard for a reason.
* **[bg3.wiki](https://bg3.wiki/wiki/Modding:PAK_files)** and the wider
  modding community — the documentation of formats, conventions, and
  folder layouts that makes independent implementations possible at all.
* The ecosystem this fits into:
  **[BG3 Modders Multitool](https://github.com/ShinyHobo/BG3-Modders-Multitool)**
  (ShinyHobo),
  **[BG3 Mod Manager](https://github.com/LaughingLeader/BG3ModManager)**
  (LaughingLeader),
  **[Script Extender](https://github.com/Norbyte/bg3se)** (Norbyte), and
  the **[BG3 Community Library](https://github.com/BG3-Community-Library-Team/BG3-Community-Library)**.
  Forge complements these — it is the data layer for reading the game
  and generating content programmatically, not a replacement for any of
  them.
* **Larian Studios** — for the game, and for shipping it in formats a
  determined community could learn to read.

If you build something on BG3 Forge, a credit and a link back are
appreciated (and please keep the LSLib credit alongside it).

## Legal

BG3 Forge reads data from **your own legally purchased copy** of Baldur's
Gate 3. It ships no game assets and is not affiliated with Larian Studios.

## License

MIT
