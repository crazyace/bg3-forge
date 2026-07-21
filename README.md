# BG3 Forge

BG3 Forge is an open-source toolkit for extracting, parsing, and exporting
Baldur's Gate 3 assets and game data into developer-friendly formats.

Instead of relying on community wikis or manually unpacking files, BG3 Forge
reads the original game data directly from the installed game and builds a
structured representation of the game's assets — a fast, offline, and
reproducible pipeline for developers, modders, and data enthusiasts.

**Library first, CLI second.** Every feature is implemented as a reusable
Python module; the `bg3forge` command is a thin layer of glue on top. Other
projects can import the library directly instead of invoking external
scripts.

```python
from bg3forge import Game

game = Game()  # auto-locates the install (or pass path= / data_dir=)

for item in game.items:
    print(item.name, item.display_name, item.rarity)

for spell in game.spells:
    print(f"[{spell.level}] {spell.display_name}: {spell.damage}")
```

```console
$ bg3forge list Shared.pak
$ bg3forge unpack -p "*/Stats/*" -o extracted
$ bg3forge spells -f json -o spells.json
$ bg3forge items -f csv -o items.csv
$ bg3forge export sqlite -o export
$ bg3forge icons Icons_Items.lsx Icons_Items.dds -o icons -f webp
$ bg3forge convert Weapons.lsf Weapons.lsx
$ bg3forge patches --update
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

```python
game = Game(path="/path/to/Baldurs Gate 3")     # or data_dir= / extracted_dir=
game = Game(language="German")                   # localization language
```

The install is auto-located via `$BG3_PATH` and well-known Steam/GOG paths
on Windows, macOS, and Linux.

## Goals

* Work completely offline
* Never depend on community wikis
* Stay compatible with new BG3 patches (patch detection + incremental extraction)
* Produce deterministic exports
* Make BG3 data easy to consume for websites, tools, and mods

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

* Character / equipment / dialog metadata parsers
* GR2 model metadata
* Virtual texture (GTS/GTP) atlas support

## Development

```console
pip install -e ".[dev]"
pytest
```

The test suite builds real LSPK/`.loca` fixtures in memory, so it runs
without a game install.

## Legal

BG3 Forge reads data from **your own legally purchased copy** of Baldur's
Gate 3. It ships no game assets and is not affiliated with Larian Studios.

## License

MIT
