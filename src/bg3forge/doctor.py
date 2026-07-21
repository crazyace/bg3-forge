"""Environment and installation diagnostics (``bg3forge doctor``).

Answers "is it my setup or is it the tool?" before anyone files a bug:
is the game found, are the paks readable and their format versions
supported, which game-data version is installed, is localization present
for the chosen language, and are the optional native dependencies
available.

Complements :mod:`bg3forge.validate`: *doctor* checks the environment,
*validate* checks every byte of game data.
"""

from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .locate import find_game
from .pak import lz4compat
from .pak.format import SUPPORTED_VERSIONS, PakHeader
from .pak.reader import PakReader
from .parsers.lsf import _unpack_version64
from .parsers.resource import parse_resource

OK = "ok"
WARN = "warn"
FAIL = "fail"

_META_RE = re.compile(r"^mods/[^/]+/meta\.lsx$")


@dataclass(frozen=True)
class CheckResult:
    status: str  # OK / WARN / FAIL
    label: str
    detail: str = ""


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def ok(self) -> bool:
        return not self.failures


def run_doctor(
    path: str | Path | None = None,
    data_dir: str | Path | None = None,
    language: str = "English",
) -> DoctorReport:
    report = DoctorReport()
    add = report.checks.append

    # -- environment ---------------------------------------------------------
    python_ok = sys.version_info >= (3, 10)
    add(CheckResult(OK if python_ok else FAIL, "Python", platform.python_version()))
    add(CheckResult(OK, "bg3forge", __version__))
    if lz4compat.HAVE_NATIVE_LZ4:
        add(CheckResult(OK, "Native LZ4", "available"))
    else:
        add(CheckResult(
            WARN, "Native LZ4",
            "not installed — the pure-Python fallback works but full-game "
            "unpacks will be slow; pip install bg3forge[lz4]",
        ))
    for module, extra, feature in (
        ("PIL", "icons", "icon extraction"),
        ("yaml", "yaml", "YAML export"),
        ("zstandard", "zstd", "zstd-compressed entries"),
    ):
        try:
            __import__(module)
            add(CheckResult(OK, f"Optional: {extra}", "installed"))
        except ImportError:
            add(CheckResult(OK, f"Optional: {extra}",
                            f"not installed — {feature} disabled (bg3forge[{extra}])"))

    # -- installation --------------------------------------------------------
    if data_dir is not None:
        resolved = Path(data_dir)
        if not (resolved.is_dir() and any(resolved.rglob("*.pak"))):
            add(CheckResult(FAIL, "BG3 data directory",
                            f"{resolved} has no .pak archives"))
            return report
        add(CheckResult(OK, "BG3 data directory", str(resolved)))
    else:
        root = find_game(path)
        if root is None:
            add(CheckResult(
                FAIL, "BG3 installation",
                "not found — set BG3_PATH, or pass --game-path / --data-dir",
            ))
            return report
        add(CheckResult(OK, "BG3 installation", str(root)))
        resolved = root / "Data"

    _check_paks(resolved, language, report)
    return report


def _check_paks(data_dir: Path, language: str, report: DoctorReport) -> None:
    add = report.checks.append
    primaries: list[Path] = []
    parts = 0
    unsupported: list[str] = []
    unreadable: list[str] = []
    versions: set[int] = set()

    for pak_path in sorted(data_dir.rglob("*.pak")):
        try:
            with pak_path.open("rb") as fh:
                head = fh.read(64)
        except OSError as exc:
            unreadable.append(f"{pak_path.name} ({exc})")
            continue
        try:
            header = PakHeader.parse(head)
        except ValueError as exc:
            if head[:4] == b"LSPK":
                unsupported.append(f"{pak_path.name} ({exc})")
            else:
                parts += 1  # secondary archive part (no LSPK header)
            continue
        primaries.append(pak_path)
        versions.add(header.version)

    if not primaries:
        add(CheckResult(FAIL, "Pak archives", f"no readable archives in {data_dir}"))
        return
    version_list = ", ".join(f"v{v}" for v in sorted(versions))
    add(CheckResult(OK, "Pak archives",
                    f"{len(primaries)} readable ({version_list}), {parts} part files"))
    for problem in unsupported:
        add(CheckResult(FAIL, "Unsupported pak version", problem))
    for problem in unreadable:
        add(CheckResult(FAIL, "Unreadable pak", problem))
    bad_versions = versions - set(SUPPORTED_VERSIONS)
    if bad_versions:  # pragma: no cover - PakHeader.parse already rejects these
        add(CheckResult(FAIL, "Pak format",
                        f"unsupported LSPK version(s): {sorted(bad_versions)}"))

    names = {p.name.lower() for p in primaries}
    if "shared.pak" in names:
        add(CheckResult(OK, "Shared.pak", "present"))
    else:
        add(CheckResult(WARN, "Shared.pak",
                        "not found — core game data may be incomplete"))
    if any(name.startswith("gustav") for name in names):
        add(CheckResult(OK, "Gustav pak", "present"))
    else:
        add(CheckResult(WARN, "Gustav pak",
                        "no Gustav*.pak found — campaign data may be missing"))

    _scan_pak_contents(primaries, language, report)


def _scan_pak_contents(primaries: list[Path], language: str, report: DoctorReport) -> None:
    """One pass over the pak indexes: module versions + localization."""
    add = report.checks.append
    module_versions: dict[str, tuple[int, int, int, int]] = {}
    language_found = False
    needle = f"/{language.lower()}/"

    for pak_path in primaries:
        try:
            reader = PakReader(pak_path)
        except ValueError:
            continue
        with reader:
            for entry in reader:
                lowered = entry.name.lower()
                if lowered.endswith(".loca") and needle in f"/{lowered}":
                    language_found = True
                elif _META_RE.match(lowered):
                    version = _module_version(reader, entry)
                    if version is not None:
                        module = entry.name.split("/")[1]
                        module_versions[module] = max(
                            version, module_versions.get(module, version)
                        )

    if module_versions:
        module, version = max(module_versions.items(), key=lambda kv: kv[1])
        add(CheckResult(OK, "Game data version",
                        f"{'.'.join(map(str, version))} (module {module})"))
    else:
        add(CheckResult(WARN, "Game data version",
                        "no Mods/*/meta.lsx found — cannot detect the installed version"))

    if language_found:
        add(CheckResult(OK, f"{language} localization", "present"))
    else:
        add(CheckResult(WARN, f"{language} localization",
                        "no .loca files found for this language"))


def _module_version(reader: PakReader, entry) -> tuple[int, int, int, int] | None:
    try:
        document = parse_resource(reader.read(entry))
    except ValueError:
        return None
    for node in document.find_all("ModuleInfo"):
        raw = node.get("Version64")
        if raw:
            try:
                return _unpack_version64(int(raw))
            except ValueError:
                continue
    return None


def format_report(report: DoctorReport, unicode_symbols: bool = True) -> str:
    symbols = (
        {OK: "✓", WARN: "⚠", FAIL: "✗"}
        if unicode_symbols
        else {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
    )
    lines = []
    for check in report.checks:
        detail = f" — {check.detail}" if check.detail else ""
        if not unicode_symbols:
            detail = detail.replace("—", "-")
        lines.append(f"{symbols[check.status]} {check.label}{detail}")
    lines += ["", "Warnings", "--------"]
    if report.warnings or report.failures:
        for check in [*report.failures, *report.warnings]:
            prefix = "FAIL: " if check.status == FAIL else ""
            lines.append(f"{prefix}{check.label}: {check.detail}")
    else:
        lines.append("None")
    return "\n".join(lines)
