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
  `write_lsf`.  LSX and LSF parse into the *same* document structure, and
  `parse_resource` sniffs the format, so downstream code never cares
  which one the game shipped
* **RootTemplates** (`.lsx` or `.lsf`) with `ParentTemplateId`
  inheritance — `RootTemplateIndex`
* **Progressions** (class/race level tables) — `parse_progressions`
* **Treasure tables** — `parse_treasure_tables`
* `bg3forge convert` converts `.lsf` ↔ `.lsx` from the command line — no
  lslib/divine required

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
atlases, and treasure tables straight out of the installed `.pak` archives
(no extraction step needed) or from a previously extracted tree, and joins
them into typed models (`Item`, `Spell`, `Passive`, `Status`) with resolved
inheritance and localized display text.

Collections support list iteration, name lookup, and search:

```python
game = Game(path="/path/to/Baldurs Gate 3")     # or data_dir= / extracted_dir=
game = Game(language="German")                   # localization language

game.spells["Projectile_Fireball"]               # lookup by stats name
game.items.find("amulet")                        # search names + display names
game.items.get("WPN_Maybe", default=None)        # tolerant lookup
```

Models form a relationship graph rather than isolated records. Forward
edges resolve an object's references (`item.passives`, `item.spells`,
`item.statuses`, `item.owner_templates`, `item.tags`); reverse edges
answer "who references me?" (`passive.items`, `spell.items`,
`status.items`, backed by a one-pass index built on first use). All
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
├── parsers/        # stats, loca, lsx, roottemplates, progressions, treasure
├── assets/         # texture atlases, icon extraction
├── exporters/      # json, sqlite, csv, markdown, yaml
├── cli/            # thin argparse front-end
├── models.py       # typed domain models (Item, Spell, Passive, Status)
├── game.py         # Game facade
└── locate.py       # install discovery
```

## Roadmap

* ✅ PAK reader/writer (LSPK v15–v18, multi-part, incremental extraction)
* ✅ Patch detection
* ✅ Stats parser with `using` inheritance
* ✅ Localization (`.loca`) parser
* ✅ LSX parser/writer
* ✅ LSF (binary) parser/writer + `bg3forge convert`
* ✅ RootTemplate parser with parent-template inheritance
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
* ⏳ Dialog metadata parser (retail dialog `.lsf` files now parse;
  next: a typed model over them)
* ⏳ Character / equipment / dialog metadata parsers
* ⏳ GR2 model metadata
* ⏳ Virtual texture (GTS/GTP) atlas support
* ⏳ PyPI release

## Development

```console
pip install -e ".[dev]"
pytest
```

The test suite builds real LSPK/`.loca`/LSF fixtures in memory, so it
runs without a game install. See [CONTRIBUTING.md](CONTRIBUTING.md) for
setup, style, and pull-request guidelines.

## Legal

BG3 Forge reads data from **your own legally purchased copy** of Baldur's
Gate 3. It ships no game assets and is not affiliated with Larian Studios.

## License

MIT
