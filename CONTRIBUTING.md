# Contributing to BG3 Forge

Thanks for your interest! BG3 Forge aims to be the standard developer
library for Baldur's Gate 3 data, and contributions of every size help.

## Setup

Python **3.10+** is required.

```console
git clone https://github.com/crazyace/bg3-forge
cd bg3-forge
pip install -e ".[all,dev]"
pytest
```

The test suite builds real LSPK/`.loca`/LSF fixtures in memory, so it runs
in a few hundred milliseconds **without a game install**. Please keep it
that way: new parser tests should construct fixtures with the library's
own writers (`PakWriter`, `write_loca`, `write_lsf`, …) rather than
depending on game files.

If you do have the game installed, `BG3_PATH=/path/to/game pytest` runs
the same suite — integration tests against a real install are welcome as
long as they skip cleanly when the game is absent
(`pytest.mark.skipif(find_game() is None, ...)`).

## Design principles

1. **Library first, CLI second.** Features live in importable modules;
   `bg3forge.cli` is a thin argparse layer. If a CLI subcommand needs more
   than a few lines of glue, the logic belongs in the library.
2. **Zero required dependencies for the core.** Native speedups (lz4,
   zstandard, Pillow, PyYAML) are optional extras with graceful fallbacks
   or clear error messages.
3. **Deterministic output.** Identical inputs must produce byte-identical
   exports — no timestamps, no dict-ordering surprises.
4. **Follow the reference.** Binary format code (`pak`, `lsf`, `loca`)
   follows Norbyte's [LSLib](https://github.com/Norbyte/lslib) struct
   layouts; cite the relevant structure in comments/docstrings when
   implementing a new one.
5. **Pay for complexity only when the data demands it.** BG3 Forge
   favors straightforward, deterministic implementations. Streaming,
   indexing, and partial parsing are introduced only when they provide a
   measurable benefit for real datasets — not because a dataset *might*
   someday be large. Stats, items, and spells are modest; parsing them
   eagerly and simply is a feature. If you propose an optimization,
   bring a measurement from real game data with it.

## Architecture roadmap

Complexity is added in phases, each justified by the data that forces it:

1. **Parse everything, resolve relationships, build a clean object
   model** — ✅ done (pak/stats/loca/LSX/LSF parsers, typed models,
   forward + reverse relationship graph).
2. **Relationship caching and hot-path optimization** — ✅ caching done
   (lazy `cached_property` edges, one-pass reverse indexes); further
   optimization only against measurements from real installs.
3. **Indexed datasets** for dialogs, quests, cinematics — the first
   datasets large enough that scanning whole paks per query stops being
   acceptable. Design starts when the first such parser lands.
4. **On-demand asset streaming** (textures, models, virtual textures) —
   only once phase 3 exists and the asset pipeline needs it.

If a change belongs to a later phase than the data it serves, it is
probably premature — the simplest architecture that scales with the
project's *actual* needs wins.

## Style

* Standard library `dataclasses`, type hints on public APIs.
* Keep modules small and focused; match the docstring style you see
  (a short format/purpose summary at the top of each module).
* No game assets, extracted data, or copyrighted material in the repo —
  fixtures are synthetic and built in code.

## Submitting changes

1. Fork and create a topic branch.
2. Add tests for anything you fix or add (`pytest` must pass; CI runs
   Linux/macOS/Windows on Python 3.10–3.12, plus a no-dependency job).
3. Keep commits focused with clear messages.
4. Open a pull request describing *what* and *why*; link related issues.

Bug reports with a failing test case (or a hexdump of the offending
bytes, for format issues) are the fastest to act on.
