"""Build a distributable dataset bundle from an installed copy of the game.

Run on a machine with Baldur's Gate 3 installed::

    python scripts/build_data_release.py                 # auto-locate the install
    python scripts/build_data_release.py --data-dir /path/to/Data
    python scripts/build_data_release.py --extracted-dir /path/to/unpacked

This is the *data-export release* step.  Because generating the datasets
reads a real (copyrighted) install, it cannot run in public CI — the
maintainer runs it locally, then attaches the bundle to a GitHub release
so the wider community (wiki editors, planner sites, spreadsheet
theorycrafters) can consume BG3 Forge's resolved data without running
anything.  See docs/data-release.md.

The bundle contains, for the resolved item / spell / passive / status /
character / progression / spell-list datasets:

* ``bg3forge-data.sqlite`` — one table per dataset (the browsable form)
* ``json/<dataset>.json`` — the nested-record form
* ``csv/<dataset>.csv`` — the flat tabular form
* ``MANIFEST.json`` — bg3forge version, detected game version, row counts,
  and a coverage summary from the validation sweep (provenance)

Output is deterministic for a given install (no wall-clock stamp), so the
bundle can be verified by re-running.  The script prints the ``gh``
command to attach it to a release.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

# Allow running from a source checkout without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bg3forge import Game, GameNotFoundError, __version__  # noqa: E402
from bg3forge.doctor import OK, run_doctor  # noqa: E402
from bg3forge.exporters import export_csv, export_json, export_sqlite  # noqa: E402
from bg3forge.validate import validate_data  # noqa: E402

#: Datasets to export, matching ``bg3forge export``.
DATASETS = (
    "items", "spells", "passives", "statuses",
    "characters", "progressions", "spell_lists",
)


class _Progress:
    """Numbered build stages with an optional self-overwriting detail line."""

    def __init__(self, total: int, stream=None):
        self.total = total
        self.stream = stream or sys.stderr
        self.index = 0
        self.started = 0.0
        self._live_width = 0

    def start(self, label: str) -> None:
        self.index += 1
        self.started = time.perf_counter()
        width = len(str(self.total))
        print(
            f"[{self.index:>{width}}/{self.total}] {label}...",
            file=self.stream,
            flush=True,
        )

    def update(self, message: str) -> None:
        """Show validation detail only when the stream is a terminal."""
        if not getattr(self.stream, "isatty", lambda: False)():
            return
        line = f"  {message}"
        padded = line.ljust(self._live_width)
        self._live_width = max(self._live_width, len(line))
        print(f"\r{padded}", end="", file=self.stream, flush=True)

    def finish(self, detail: str = "") -> None:
        if self._live_width:
            print(
                "\r" + " " * self._live_width + "\r",
                end="",
                file=self.stream,
                flush=True,
            )
            self._live_width = 0
        elapsed = time.perf_counter() - self.started
        suffix = f" — {detail}" if detail else ""
        print(f"  done{suffix} ({elapsed:.1f}s)", file=self.stream, flush=True)


def _detect_game_version(game: Game) -> str:
    """The install's game-data version string, via the same detection the
    doctor uses.  ``"unknown"`` when there is no module meta to read from
    (e.g. an ``--extracted-dir`` that omits the manifests)."""
    if game.data_dir is None:
        return "unknown"
    report = run_doctor(data_dir=game.data_dir, language=game.language)
    for check in report.checks:
        # Only the OK check carries a version; the WARN case ("no meta
        # found") must not be mistaken for one.
        if check.label == "Game data version" and check.status == OK:
            # detail looks like "4.1.1.4859133 (module GustavDev)"
            return check.detail.split(" ", 1)[0]
    return "unknown"


def _open_game(args: argparse.Namespace) -> Game:
    if args.extracted_dir:
        return Game(extracted_dir=args.extracted_dir, language=args.language)
    if args.data_dir:
        return Game(data_dir=args.data_dir, language=args.language)
    return Game(path=args.game_path, language=args.language)


def build(args: argparse.Namespace) -> Path:
    progress = _Progress(len(DATASETS) + 3)
    print("Building BG3 Forge data release", file=sys.stderr, flush=True)
    game = _open_game(args)
    staging = args.output / "bundle"
    (staging / "json").mkdir(parents=True, exist_ok=True)
    (staging / "csv").mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for dataset in DATASETS:
        progress.start(f"Exporting {dataset}")
        objects = list(getattr(game, dataset))
        counts[dataset] = len(objects)
        export_sqlite(objects, staging / "bg3forge-data.sqlite", table=dataset)
        export_json(objects, staging / "json" / f"{dataset}.json")
        export_csv(objects, staging / "csv" / f"{dataset}.csv")
        progress.finish(f"{len(objects):,} rows")

    progress.start("Detecting game version")
    game_version = _detect_game_version(game)
    progress.finish(game_version)

    # Coverage/provenance: a validation sweep says whether every recognized
    # file in the install parsed cleanly, so consumers know the dataset was
    # built from a fully-understood install.
    progress.start("Validating source archives")
    coverage: dict[str, object] = {}
    if game.data_dir is not None:
        report = validate_data(game.data_dir, progress=progress.update)
        coverage = {
            "ok": report.ok,
            "issues": len(report.issues),
            "paks": report.counts.get("paks", 0),
        }
        validation_detail = (
            f"{coverage['paks']:,} paks, {coverage['issues']:,} issues"
        )
    else:
        validation_detail = "skipped for extracted data"
    progress.finish(validation_detail)

    progress.start("Writing release bundle")
    manifest = {
        "bg3forge_version": __version__,
        "game_version": game_version,
        "language": game.language,
        "datasets": counts,
        "coverage": coverage,
        "note": (
            "Resolved BG3 data generated by BG3 Forge from an installed copy "
            "of the game. Ships no Larian assets. https://github.com/crazyace/bg3-forge"
        ),
    }
    (staging / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), "utf-8"
    )

    label = args.label or game_version
    bundle = args.output / f"bg3forge-data-{label}.zip"
    _zip_dir(staging, bundle)
    progress.finish(f"{bundle.stat().st_size / 1_000_000:.1f} MB")
    return bundle


def _zip_dir(root: Path, bundle: Path) -> None:
    """Zip ``root`` into ``bundle`` deterministically (sorted entries, a
    fixed timestamp), so the same install produces byte-identical output."""
    files = sorted(p for p in root.rglob("*") if p.is_file())
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(root).as_posix()))
            info.date_time = (1980, 1, 1, 0, 0, 0)  # fixed epoch → reproducible
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-path", type=Path, help="BG3 install root")
    parser.add_argument("--data-dir", type=Path, help="the install's Data directory")
    parser.add_argument("--extracted-dir", type=Path, help="an unpacked data tree")
    parser.add_argument("--language", default="English")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument(
        "--label",
        help="bundle name suffix (default: detected game version)",
    )
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)

    try:
        bundle = build(args)
    except GameNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    size_mb = bundle.stat().st_size / 1_000_000
    print(f"\nwrote {bundle} ({size_mb:.1f} MB)")
    print("\nattach it to a release with:")
    print(f"  gh release upload <tag> {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
