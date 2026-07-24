# BG3 Forge

BG3 Forge is an open-source toolkit for reading Baldur's Gate 3 game data,
finding the records a mod needs, validating mods before release, and building
new content programmatically.

> [!IMPORTANT]
> **BG3 Forge is a development tool, not an in-game mod.** Do not install it
> with BG3 Mod Manager or Vortex. Mod authors run Forge from PowerShell or
> Python; players install the `.pak` files those authors create.

Forge reads the original data from **your own installed copy** of the game and
turns it into a connected, typed model. It does not depend on a community wiki,
does not modify the game installation, and ships no Larian assets.

[Quick start](#quick-start) ·
[Common tasks](#common-tasks) ·
[Mod authoring](#mod-authoring) ·
[Python API](#python-api) ·
[Data releases](#resolved-data-releases) ·
[Contributing](#development)

## Who is it for?

| You want to… | Start with |
| --- | --- |
| Find a stats name, UUID, localization handle, or related record | `bg3forge lookup` |
| Check a `.pak` before uploading it to Nexus Mods | `bg3forge lint` |
| Build armor, weapons, consumables, passives, statuses, or spells | [`Mod`](#mod-authoring) |
| Add a spell to a class's real level-up lists | [`add_class_spell`](#add-a-class-spell) |
| Export items, spells, or other resolved datasets | `bg3forge export` |
| Build a browser, planner, bot, database, or GUI | [`Game`](#python-api) |
| Use the data without installing Python | [Download a release bundle](#resolved-data-releases) |

BG3 Forge complements
[LSLib](https://github.com/Norbyte/lslib),
[BG3 Modders Multitool](https://github.com/ShinyHobo/BG3-Modders-Multitool),
[BG3 Mod Manager](https://github.com/LaughingLeader/BG3ModManager),
[Script Extender](https://github.com/Norbyte/bg3se), and the
[BG3 Community Library](https://github.com/BG3-Community-Library-Team/BG3-Community-Library).
It is the programmatic data and authoring layer alongside them, not a
replacement for them.

## Quick start

BG3 Forge supports Python 3.10–3.13. Python 3.12 is a good default on Windows.

### Windows PowerShell

From your project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "bg3forge[all]==0.2.0"
bg3forge doctor
```

If PowerShell blocks virtual-environment activation, allow it for the current
window and try again:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

### Linux and macOS

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "bg3forge[all]==0.2.0"
bg3forge doctor
```

`doctor` confirms that Python, optional features, the game installation,
archives, version metadata, and localization are ready. If Forge cannot locate
the game automatically, point it at the installation:

```powershell
bg3forge --game-path "E:\SteamLibrary\steamapps\common\Baldurs Gate 3" doctor
```

You can also set the path once for the current PowerShell window:

```powershell
$env:BG3_PATH = "E:\SteamLibrary\steamapps\common\Baldurs Gate 3"
bg3forge doctor
```

## Common tasks

### Look up game data

Search by internal name, display name, UUID, or localization handle:

```powershell
bg3forge lookup Projectile_Fireball_4
bg3forge lookup "Fireball"
bg3forge lookup WPN_Longsword
```

Names are matched case-insensitively when the result is unambiguous. Partial
queries return ranked suggestions and the true match count, so a broad search
never silently hides how much it found. Multi-word display names may be quoted
as usual.

Lookup results connect the graph instead of showing an isolated row:

- items show stats, templates, tags, passives, statuses, and unlocked spells;
- spells show items and progressions that grant them;
- passives and statuses show what grants or applies them;
- characters show their stat block, passives, tags, and equipment; and
- classes, races, progressions, and spell lists retain their distinct
  grant-versus-selection relationships.

### Check a mod before uploading it

Run the internal checks without a game installation:

```powershell
bg3forge lint "D:\Mods\MyMod.pak"
```

Point Forge at BG3 to also resolve references against the base game:

```powershell
bg3forge --game-path "E:\SteamLibrary\steamapps\common\Baldurs Gate 3" lint "D:\Mods\MyMod.pak"
```

`lint` checks the module manifest, folder consistency, supported resource
formats, UUIDs, localization handles, inheritance chains, and references to
passives, statuses, and spells. It is intended to catch the common “the mod
doesn't appear” and “the item loads but part of it is broken” failures before
they reach Nexus users.

### Export resolved data

Export every public dataset in one format:

```powershell
bg3forge export json -o export
bg3forge export csv -o export
bg3forge export sqlite -o export
```

Or export one dataset:

```powershell
bg3forge items -f csv -o items.csv
bg3forge spells -f json -o spells.json
bg3forge spell-lists -f json -o spell-lists.json
```

Supported formats are JSON, CSV, SQLite, Markdown, and YAML. YAML requires the
`yaml` extra.

### Inspect or extract archives

```powershell
bg3forge list "E:\SteamLibrary\steamapps\common\Baldurs Gate 3\Data\Shared.pak"
bg3forge search "journal"
bg3forge search "*/Stats/*" --dirs
bg3forge unpack -p "*/Stats/*" -o extracted
bg3forge convert Weapons.lsf Weapons.lsx
bg3forge patches --update
```

### Diagnose and validate an installation

```powershell
bg3forge doctor
bg3forge validate
bg3forge benchmark
```

`validate` parses every recognized file and reports coverage and failures.
`benchmark` runs the complete connected-data pipeline with stage timings and
peak memory use.

## Installation choices

The core library has no required dependencies. It includes a pure-Python LZ4
block codec, so the basic package installs anywhere supported Python does.
Extras provide speedups or feature-specific integrations:

| Install | Enables |
| --- | --- |
| `bg3forge` | Dependency-free core |
| `bg3forge[lz4]` | Native-speed LZ4; recommended for full game archives |
| `bg3forge[zstd]` | Zstandard-compressed archive entries |
| `bg3forge[icons]` | DDS decoding and PNG/WebP icon export |
| `bg3forge[yaml]` | YAML export |
| `bg3forge[all]` | Every optional runtime feature |

For a command-line installation, `[all]` is the easiest choice. Projects
embedding Forge can depend on the core and add only the extras they use:

```toml
dependencies = ["bg3forge>=0.2,<0.3"]
```

BG3 Forge is pre-1.0: minor versions may evolve the public API, while patch
releases within the same minor line will not intentionally break it.

## Python API

`Game` auto-locates the installation and loads each collection only when it is
first accessed:

```python
from bg3forge import Game

game = Game()
fireball = game.spells["Projectile_Fireball"]

print(fireball.display_name)
print(fireball.level)
print(fireball.damage)
```

Models are connected across stats, templates, localization, tags, atlases,
progressions, spell lists, and equipment:

```python
sword = game.items["WPN_Longsword"]

print(sword.display_name)
print(sword.owner_templates)
print(sword.passives)
print(sword.statuses)
print(sword.spells)

print(game.passives["ExtraAttack"].items)
print(game.spells["Projectile_Fireball"].progressions)
print(game.classes["Wizard"].spell_list)
print(game.races["Elf"].subraces)
```

Collections support iteration, exact lookup, tolerant lookup, and search:

```python
for spell in game.spells.find("fire"):
    print(spell.name, spell.display_name)

maybe_item = game.items.get("WPN_Maybe", default=None)
print(maybe_item)
```

Large resources stay lazy. Dialogs and compiled Osiris stories are indexed
first and parsed individually on demand:

```python
dialog_paths = game.dialogs.find("Karlach")
for dialog_path in dialog_paths[:1]:
    dialog = game.dialogs.load(dialog_path)
    lines = game.dialogs.lines(dialog_path)
    print(len(lines))

for story_path in game.story.paths[:1]:
    story = game.story.load(story_path)
    print(story.header.version)
```

Forward and reverse relationships are cached per `Game` instance. Raw resolved
stats remain available through `object.data` when a typed model does not yet
surface a field.

## Mod authoring

The `Mod` API creates deterministic project identifiers, writes BG3 resource
files, lays out the module correctly, and packages the result as a `.pak`.
Forge writes only to the output path you choose.

### Build an item

```python
from bg3forge import Mod

mod = Mod("SunforgedArmors", author="you")
template_uuid = mod.new_armor(
    "ARM_Sunforged_Plate",
    armor_class=21,
    stats_using="_Armor",
    parent_template="<base-template-uuid>",
    display_name="Sunforged Plate",
    description="Warm to the touch.",
    icon="Item_Plate_Body",
    boosts=["Ability(Strength,2)"],
    treasure="TUT_Chest_Potions",
)

print(template_uuid)
print(mod.build("SunforgedArmors.pak"))
```

`parent_template` reuses an existing item's visuals. Find a suitable template
directly from the installed game:

```python
plate = game.items["ARM_Body_Plate"]
parent_template = plate.owner_templates[0].map_key

print(parent_template)
```

The generated `SunforgedArmors.pak` is the file to test in BG3 and eventually
upload to Nexus Mods. BG3 Forge itself remains a development dependency.

The high-level API also provides:

- `new_weapon`
- `new_potion`
- `new_elixir`
- `new_scroll`
- `new_passive`
- `new_status`
- `new_spell`
- `place_in_treasure`

### Add a class spell

`add_class_spell` reads the class's real spell lists and writes compatible
replacements with the custom spell added. It handles cantrip lists separately
from leveled spell lists:

```python
from bg3forge import add_class_spell

spell_mod = Mod("SunstepForBards", author="you")
sunstep = spell_mod.new_spell(
    "Target_Sunstep",
    using="Target_MistyStep",
    display_name="Sunstep",
    icon="Spell_Conjuration_DimensionDoor",
)

add_class_spell(game, spell_mod, "Bard", sunstep, level=2)
print(spell_mod.build("SunstepForBards.pak"))
```

Authoring has been retail-verified in Patch 8 for armor, weapons, potions,
elixirs, scrolls, passives, statuses, custom spells, wizard transcription,
treasure placement, and class level-up selection. See the
[mod-authoring guide](docs/mod-authoring.md) for the repeatable in-game test
procedure and [retail baseline](docs/baseline.md)
for the results.

## Resolved data releases

GitHub releases can include a patch-labeled bundle such as
`bg3forge-data-4.8.700.7143220.zip`. It contains:

| Path | Contents |
| --- | --- |
| `bg3forge-data.sqlite` | All datasets as browsable SQLite tables |
| `json/<dataset>.json` | Nested JSON records |
| `csv/<dataset>.csv` | Flat CSV tables |
| `MANIFEST.json` | Forge version, game version, row counts, and validation provenance |

This is intended for wiki editors, theorycrafters, spreadsheet users, planner
sites, Discord bots, and other consumers that want resolved data without
running Python. The bundle is deterministic and contains no textures, models,
audio, or other Larian assets.

Download bundles from
[GitHub Releases](https://github.com/crazyace/bg3-forge/releases).
The format and regeneration procedure are documented in
[`docs/data-release.md`](docs/data-release.md).

## Retail validation snapshot

Version 0.2.0 was validated against the English Steam build
`4.8.700.7143220`:

| Check | Result |
| --- | ---: |
| Readable primary pak archives | 30 |
| Corrupt pak archives | 0 |
| Resolved stats entries | 16,132 |
| Items | 3,139 |
| Spells | 4,687 |
| Passives | 1,827 |
| Statuses | 4,631 |
| Characters | 1,550 |
| Progressions | 1,004 |
| Spell lists | 315 |
| Missing progression passive references | 0 |
| Missing progression spell-list references | 0 |
| Missing spell-list spell references | 0 |

Every recognized file parsed cleanly. The complete connected pipeline finished
in approximately 11.2 seconds with 828 MB peak RSS on the release machine.
These numbers describe that installation and patch; other versions may differ.
See [`docs/baseline.md`](docs/baseline.md) for the complete coverage report and
benchmark history.

## Capabilities

### Archives and resources

- LSPK v15, v16, and v18 archives, including multi-part archives
- LZ4, zlib, and zstd entries
- incremental extraction with content-hash manifests
- LSX, LSF v1–v7, and LSJ parsing into one document model
- LSF ↔ LSX conversion
- pak writing for generated mods

### Connected game data

- stats with `using` inheritance and retail load-order layering
- localization and RootTemplate inheritance
- tags, texture atlases, treasure tables, and equipment sets
- items, spells, passives, statuses, and characters
- progressions, classes, races, and spell lists
- quests, journal steps, objectives, categories, and map markers
- lazy dialog and cinematic-timeline indexes
- source goals and compiled Osiris metadata
- forward and reverse references across the model graph

### Tooling

- deterministic JSON, CSV, SQLite, Markdown, and YAML exports
- DDS atlas slicing to PNG or WebP
- install diagnostics and full-format validation
- mod linting with optional base-game reference checks
- deterministic mod authoring and packaging
- a typed package with a PEP 561 `py.typed` marker

For the detailed design and future format work, see
[`docs/plan.md`](docs/plan.md).

## Development

Clone the repository and install the development dependencies:

```console
git clone https://github.com/crazyace/bg3-forge.git
cd bg3-forge
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pytest
```

The unit suite builds real LSPK, `.loca`, LSF, and mod fixtures in memory, so it
does not require an installed copy of BG3. Retail-only verification is
documented separately:

- [Contributing and design principles](CONTRIBUTING.md)
- [Retail testing](docs/retail-testing.md)
- [Release checklist](docs/release-checklist.md)
- [Changelog](CHANGELOG.md)

## Acknowledgements

BG3 Forge stands on years of community reverse-engineering work:

- **[LSLib](https://github.com/Norbyte/lslib)** by **Norbyte** is the
  reference implementation for Larian's formats. BG3 Forge is an independent
  implementation and uses no LSLib code, but its binary layouts are informed
  by and verified against LSLib.
- **[bg3.wiki](https://bg3.wiki/wiki/Modding:PAK_files)** and the wider BG3
  modding community documented the formats, conventions, and folder layouts
  that make independent tooling possible.
- The maintainers of BG3 Modders Multitool, BG3 Mod Manager, Script Extender,
  and the BG3 Community Library built the ecosystem Forge is intended to
  support.
- **Larian Studios** created Baldur's Gate 3 and shipped it in formats the
  community could learn to understand.

If you build something on BG3 Forge, a credit and link back are appreciated.
Please preserve the LSLib credit in that chain.

## Legal

BG3 Forge reads data from your own legally purchased copy of Baldur's Gate 3.
It ships no game assets and is not affiliated with or endorsed by Larian
Studios.

## License

[MIT](LICENSE)
