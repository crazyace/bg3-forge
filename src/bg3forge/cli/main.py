"""``bg3forge`` command-line entry point.

The CLI is intentionally thin: every subcommand is a few lines of glue
around the library so that other projects can do the same things by
importing :mod:`bg3forge` directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .. import __version__
from ..exporters import FORMATS, export_json
from ..game import Game, GameNotFoundError
from ..pak.extractor import Extractor
from ..pak.patches import PatchDetector
from ..pak.reader import PakReader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bg3forge",
        description="Extract, parse, and export Baldur's Gate 3 game data.",
    )
    parser.add_argument("--version", action="version", version=f"bg3forge {__version__}")
    parser.add_argument(
        "--game-path",
        type=Path,
        help="game install root (default: auto-detect / $BG3_PATH)",
    )
    parser.add_argument(
        "--data-dir", type=Path, help="directory containing .pak archives directly"
    )
    parser.add_argument(
        "--extracted-dir", type=Path, help="use a previously extracted directory tree"
    )
    parser.add_argument(
        "--language", default="English", help="localization language (default: English)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    unpack = sub.add_parser("unpack", help="extract .pak archives incrementally")
    unpack.add_argument("pak", type=Path, nargs="?", help="a single .pak (default: all game paks)")
    unpack.add_argument("-o", "--output", type=Path, default=Path("extracted"))
    unpack.add_argument("-p", "--pattern", action="append", help="glob filter, repeatable")
    unpack.add_argument("--force", action="store_true", help="rewrite unchanged files too")

    listing = sub.add_parser("list", help="list the contents of a .pak archive")
    listing.add_argument("pak", type=Path)

    search = sub.add_parser(
        "search", help="search archived file paths across all game paks (index-only, fast)"
    )
    search.add_argument(
        "pattern",
        help="case-insensitive substring, or a glob when it contains * or ? "
        '(e.g. "*/journal/*.lsf")',
    )
    search.add_argument("--limit", type=int, default=50, help="matches to print (default: 50)")
    search.add_argument(
        "--dirs", action="store_true",
        help="aggregate matches by directory (count + path), best for discovering "
        "where a dataset lives",
    )

    patches = sub.add_parser("patches", help="detect game archives changed by a patch")
    patches.add_argument("--snapshot", type=Path, default=Path(".bg3forge-paks.json"))
    patches.add_argument("--update", action="store_true", help="store the current state")

    for name, help_text in (
        ("items", "export items"),
        ("spells", "export spells"),
        ("passives", "export passives"),
        ("statuses", "export statuses"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        _add_export_args(cmd, default_output=Path(f"{name}.json"))

    export = sub.add_parser("export", help="export every dataset at once")
    export.add_argument("format", choices=sorted(FORMATS))
    export.add_argument("-o", "--output", type=Path, default=Path("export"))

    sub.add_parser(
        "doctor", help="diagnose the installation and environment"
    )

    validate = sub.add_parser(
        "validate", help="parse every recognized file in the game data and report failures"
    )
    validate.add_argument(
        "--max-issues", type=int, default=20, help="issues to print in full (default: 20)"
    )
    validate.add_argument(
        "--no-progress", action="store_true",
        help="disable the live progress line (auto-disabled when stderr is not a terminal)",
    )

    benchmark = sub.add_parser(
        "benchmark", help="time each pipeline stage against the game data"
    )
    benchmark.add_argument(
        "--export-dir", type=Path, help="keep the benchmark's JSON exports here"
    )

    convert = sub.add_parser("convert", help="convert between .lsf and .lsx resources")
    convert.add_argument("input", type=Path, help="source resource (.lsf or .lsx)")
    convert.add_argument("output", type=Path, help="target file; extension picks the format")
    convert.add_argument(
        "--lsf-version", type=int, default=6, choices=(5, 6, 7),
        help="LSF version to write (default: 6)",
    )

    icons = sub.add_parser("icons", help="extract icons from a DDS atlas")
    icons.add_argument("atlas_lsx", type=Path, help="atlas definition (.lsx)")
    icons.add_argument("texture", type=Path, help="atlas texture (.dds)")
    icons.add_argument("-o", "--output", type=Path, default=Path("icons"))
    icons.add_argument("-f", "--format", choices=("png", "webp"), default="png")
    return parser


def _add_export_args(cmd: argparse.ArgumentParser, default_output: Path) -> None:
    cmd.add_argument("-o", "--output", type=Path, default=default_output)
    cmd.add_argument("-f", "--format", choices=sorted(FORMATS), default="json")


class _LiveProgress:
    """Single self-overwriting status line; call clear() when done."""

    def __init__(self, stream, owns_stream: bool = False):
        self._stream = stream
        self._owns_stream = owns_stream
        self._width = 0

    def __call__(self, message: str) -> None:
        padded = message.ljust(self._width)
        self._width = max(self._width, len(message))
        try:
            print(f"\r{padded}", end="", file=self._stream, flush=True)
        except OSError:
            pass  # console went away; progress is best-effort

    def clear(self) -> None:
        try:
            if self._width:
                print("\r" + " " * self._width + "\r", end="", file=self._stream, flush=True)
        except OSError:
            pass
        finally:
            if self._owns_stream:
                self._stream.close()


def _open_console():
    """The controlling console device, bypassing any stream redirection."""
    path = "CONOUT$" if os.name == "nt" else "/dev/tty"
    return open(path, "w")


def _console_progress() -> _LiveProgress | None:
    """A progress renderer that stays visible even under redirection.

    Prefers stderr when it's an interactive terminal; when the streams
    are redirected (`bg3forge validate *> report.txt`), falls back to
    writing straight to the console device so the live line still shows
    without ever contaminating the captured file.  Returns None in truly
    headless environments (no console at all).
    """
    if getattr(sys.stderr, "isatty", lambda: False)():
        return _LiveProgress(sys.stderr)
    try:
        return _LiveProgress(_open_console(), owns_stream=True)
    except OSError:
        return None


def _open_game(args) -> Game:
    return Game(
        path=args.game_path,
        data_dir=args.data_dir,
        extracted_dir=args.extracted_dir,
        language=args.language,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (GameNotFoundError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args) -> int:
    if args.command == "list":
        with PakReader(args.pak) as pak:
            for entry in pak:
                print(f"{entry.size:>12}  {entry.name}")
        return 0

    if args.command == "search":
        import fnmatch
        from collections import Counter

        game = _open_game(args)
        needle = args.pattern.lower()
        if any(ch in needle for ch in "*?["):
            predicate = lambda n: fnmatch.fnmatch(n.lower(), needle)  # noqa: E731
        else:
            predicate = lambda n: needle in n.lower()  # noqa: E731
        sources = game._locate_entries(predicate)

        if args.dirs:
            directories = Counter(name.rsplit("/", 1)[0] for name in sources)
            for directory, count in directories.most_common(args.limit):
                print(f"{count:>7,}  {directory}")
            shown = min(len(directories), args.limit)
            summary = f"{len(sources)} match(es) in {len(directories)} directorie(s)"
            if len(directories) > shown:
                summary += f", top {shown} shown"
            print(summary)
        else:
            for name, source in list(sources.items())[: args.limit]:
                print(f"{getattr(source, 'name', source)}  {name}")
            shown = min(len(sources), args.limit)
            summary = f"{len(sources)} match(es)"
            if len(sources) > shown:
                summary += f", first {shown} shown"
            print(summary)
        return 0

    if args.command == "unpack":
        extractor = Extractor(args.output)
        if args.pak is not None:
            paks = [args.pak]
        else:
            game = _open_game(args)
            if game.data_dir is None:
                print("error: unpack needs a game install or --data-dir", file=sys.stderr)
                return 1
            paks = sorted(game.data_dir.rglob("*.pak"))
        total_extracted = total_skipped = 0
        for pak_path in paks:
            try:
                result = extractor.extract(pak_path, patterns=args.pattern, force=args.force)
            except ValueError:
                continue  # secondary archive part or foreign file
            total_extracted += len(result.extracted)
            total_skipped += len(result.skipped)
            if result.total:  # keep quiet about paks with nothing matching
                print(f"{pak_path.name}: {len(result.extracted)} extracted, "
                      f"{len(result.skipped)} unchanged")
        print(f"done: {total_extracted} extracted, {total_skipped} unchanged")
        return 0

    if args.command == "patches":
        game = _open_game(args)
        detector = PatchDetector(args.snapshot)
        report = detector.compare(game.data_dir)
        for name in report.added:
            print(f"added:   {name}")
        for name in report.changed:
            print(f"changed: {name}")
        for name in report.removed:
            print(f"removed: {name}")
        if not report.dirty:
            print("no changes detected")
        if args.update:
            detector.update(game.data_dir)
            print(f"snapshot written to {args.snapshot}")
        return 0

    if args.command in ("items", "spells", "passives", "statuses"):
        game = _open_game(args)
        objects = getattr(game, args.command)
        FORMATS[args.format](objects, args.output)
        print(f"wrote {len(objects)} {args.command} to {args.output}")
        return 0

    if args.command == "export":
        game = _open_game(args)
        exporter = FORMATS[args.format]
        suffix = {"json": "json", "csv": "csv", "sqlite": "db",
                  "markdown": "md", "yaml": "yaml"}[args.format]
        for dataset in ("items", "spells", "passives", "statuses"):
            objects = getattr(game, dataset)
            if args.format == "sqlite":
                exporter(objects, args.output / "bg3.db", table=dataset)
            else:
                exporter(objects, args.output / f"{dataset}.{suffix}")
            print(f"exported {len(objects)} {dataset}")
        return 0

    if args.command == "doctor":
        from ..doctor import format_report, run_doctor

        report = run_doctor(
            path=args.game_path, data_dir=args.data_dir, language=args.language
        )
        encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
        print(format_report(report, unicode_symbols="utf" in encoding))
        return 0 if report.ok else 1

    if args.command == "validate":
        from ..validate import format_report, validate_data

        game = _open_game(args)
        if game.data_dir is None:
            print("error: validate needs a game install or --data-dir", file=sys.stderr)
            return 1
        progress = None if args.no_progress else _console_progress()
        try:
            report = validate_data(game.data_dir, progress=progress)
        finally:
            if progress:
                progress.clear()
        print(format_report(report, max_issues=args.max_issues))
        return 0 if report.ok else 1

    if args.command == "benchmark":
        from ..benchmark import format_report, run_benchmark

        report = run_benchmark(_open_game(args), export_dir=args.export_dir)
        print(format_report(report))
        return 0

    if args.command == "convert":
        from ..parsers.lsf import write_lsf
        from ..parsers.lsx import write_lsx
        from ..parsers.resource import load_resource

        document = load_resource(args.input)
        suffix = args.output.suffix.lower()
        if suffix == ".lsx":
            args.output.write_text(write_lsx(document), "utf-8")
        elif suffix == ".lsf":
            args.output.write_bytes(write_lsf(document, version=args.lsf_version))
        else:
            print(f"error: unsupported output format {suffix!r}", file=sys.stderr)
            return 1
        print(f"converted {args.input} -> {args.output}")
        return 0

    if args.command == "icons":
        from ..assets.icons import IconExtractor
        from ..assets.atlases import parse_atlas
        from ..parsers.lsx import load_lsx

        atlas = parse_atlas(load_lsx(args.atlas_lsx))
        extractor = IconExtractor(atlas, args.texture)
        result = extractor.export_all(args.output, format=args.format)
        print(f"wrote {len(result.written)} icons to {args.output}")
        return 0

    raise AssertionError(f"unhandled command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
