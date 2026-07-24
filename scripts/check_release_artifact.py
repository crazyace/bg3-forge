"""Validate a built bg3forge wheel before a release is published."""

from __future__ import annotations

import argparse
import email
import tomllib
import zipfile
from pathlib import Path


def check_wheel(wheel: Path) -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))["project"]
    version = project["version"]
    init_text = Path("src/bg3forge/__init__.py").read_text("utf-8")
    expected = f'__version__ = "{version}"'
    if expected not in init_text:
        raise SystemExit(
            f"version mismatch: pyproject.toml is {version!r}, "
            "but src/bg3forge/__init__.py does not agree"
        )

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        unexpected = []
        for name in names:
            root = name.partition("/")[0]
            package_file = root == "bg3forge"
            metadata_file = root.startswith("bg3forge-") and root.endswith(".dist-info")
            if not (package_file or metadata_file):
                unexpected.append(name)
        if unexpected:
            rendered = "\n  ".join(unexpected)
            raise SystemExit(f"unexpected wheel contents:\n  {rendered}")

        metadata_names = [
            name for name in names
            if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise SystemExit(
                f"expected one METADATA file, found {len(metadata_names)}"
            )
        metadata = email.message_from_bytes(archive.read(metadata_names[0]))

    if metadata["Name"] != project["name"]:
        raise SystemExit(
            f"package name mismatch: {metadata['Name']!r} != {project['name']!r}"
        )
    if metadata["Version"] != version:
        raise SystemExit(
            f"wheel version mismatch: {metadata['Version']!r} != {version!r}"
        )

    requirements = metadata.get_all("Requires-Dist", [])
    runtime_requirements = [
        requirement
        for requirement in requirements
        if "extra ==" not in requirement and "extra==" not in requirement
    ]
    if runtime_requirements:
        rendered = "\n  ".join(runtime_requirements)
        raise SystemExit(f"core wheel has required dependencies:\n  {rendered}")

    print(
        f"validated {wheel.name}: version {version}, "
        f"{len(names)} files, zero required dependencies"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    check_wheel(args.wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
