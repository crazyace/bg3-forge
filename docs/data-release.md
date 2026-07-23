# Publishing a data-export release

BG3 Forge's most valuable output for the wider community is the *resolved*
game data — items, spells, passives, statuses, characters, progressions,
and spell lists, with names, descriptions, and cross-references already
joined. Most of the people who want that data (wiki editors, build-planner
sites, spreadsheet theorycrafters, Discord bots) don't run Python. So we
publish the datasets themselves as a downloadable bundle attached to each
release.

## Why this is a manual step

Generating the datasets reads a **real, copyrighted install** of the game.
Public CI has no such install and legally cannot, so the bundle is built
locally by a maintainer who owns the game, then uploaded to the release.
The tool is what *regenerates* the bundle each patch — the data is a
byproduct, never checked into the repo.

## Building the bundle

On a machine with BG3 installed:

```console
$ python scripts/build_data_release.py
  items           12,842
  spells           4,051
  passives         1,876
  statuses         2,410
  characters       3,190
  progressions     1,004
  spell_lists        315

wrote dist/bg3forge-data-4.1.1.4859133.zip (18.4 MB)

attach it to a release with:
  gh release upload <tag> dist/bg3forge-data-4.1.1.4859133.zip
```

The install is auto-located; pass `--data-dir /path/to/Data`,
`--game-path /path/to/"Baldurs Gate 3"`, or `--extracted-dir /unpacked`
to point it explicitly. `--label` overrides the version suffix in the
filename (it otherwise uses the detected game version).

## What's in the bundle

| Path | Form |
| --- | --- |
| `bg3forge-data.sqlite` | one table per dataset — the browsable form (open in any SQLite viewer) |
| `json/<dataset>.json` | nested-record JSON |
| `csv/<dataset>.csv` | flat tabular CSV |
| `MANIFEST.json` | `bg3forge` version, detected game version, per-dataset row counts, and the validation-sweep coverage summary (provenance) |

The bundle is **deterministic**: the same install produces a
byte-identical zip (entries sorted, a fixed timestamp), so anyone can
verify it by re-running the script. The `MANIFEST.json` records which
game version and which `bg3forge` version produced it.

## Release procedure

1. Cut the code release first (bump the version, tag, let the publish
   pipeline ship to PyPI — see [release-checklist.md](release-checklist.md)).
2. Build the bundle against the current retail patch (above).
3. Attach it: `gh release upload <tag> dist/bg3forge-data-<version>.zip`.
4. In the release notes, state the game patch the data was built from and
   link this doc so consumers know how it was produced.

## Licensing note

The bundle is *derived data* describing the game — names, numbers, and
relationships — generated from the user's own install. It ships **no
Larian assets** (no textures, audio, models, or raw game files). Keep the
`MANIFEST.json` note intact; it records the provenance.
