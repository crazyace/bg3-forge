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
Building BG3 Forge data release
[ 1/10] Exporting items...
  done — 3,139 rows
[ 2/10] Exporting spells...
  done — 4,687 rows
[ 3/10] Exporting passives...
  done — 1,827 rows
[ 4/10] Exporting statuses...
  done — 4,631 rows
[ 5/10] Exporting characters...
  done — 1,550 rows
[ 6/10] Exporting progressions...
  done — 1,004 rows
[ 7/10] Exporting spell_lists...
  done — 315 rows
[ 8/10] Detecting game version...
  done — 4.8.700.7143220
[ 9/10] Validating source archives...
  done — 30 paks, 0 issues
[10/10] Writing release bundle...
  done — 8.2 MB

wrote dist/bg3forge-data-4.8.700.7143220.zip (8.2 MB)

attach it to a release with:
  gh release upload <tag> dist/bg3forge-data-4.8.700.7143220.zip
```

The install is auto-located; pass `--data-dir /path/to/Data`,
`--game-path /path/to/"Baldurs Gate 3"`, or `--extracted-dir /unpacked`
to point it explicitly. `--label` overrides the version suffix in the
filename (it otherwise uses the detected game version).

The archive validation stage is deliberately fail-closed. Any parse failure
or unresolved progression-passive, progression-spell-list, or spell-list
spell reference stops the command with a non-zero exit status before a new
bundle is written. On an interactive terminal, the long archive sweep also
shows the pak currently being checked.

Every invocation builds in a new temporary staging directory and atomically
replaces the named ZIP only after validation and compression succeed. Files
left by an older run cannot leak into a later bundle. If a rebuild fails and
a same-named bundle already exists, that known-good bundle is left unchanged
and the error states that no new bundle was published.

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

1. From the release commit or release branch, build the bundle against the
   current retail patch (above). Keep the bundle only if validation reports
   zero issues.
2. Bump the version, tag, and let the publish pipeline ship to PyPI — see
   [release-checklist.md](release-checklist.md).
3. Attach the retained bundle:
   `gh release upload <tag> dist/bg3forge-data-<version>.zip`.
4. In the release notes, state the game patch the data was built from and
   link this doc so consumers know how it was produced.

## Licensing note

The bundle is *derived data* describing the game — names, numbers, and
relationships — generated from the user's own install. It ships **no
Larian assets** (no textures, audio, models, or raw game files). Keep the
`MANIFEST.json` note intact; it records the provenance.
