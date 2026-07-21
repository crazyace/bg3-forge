"""Exporters for parsed game data."""

from .json import export_json
from .csv import export_csv
from .sqlite import export_sqlite
from .markdown import export_markdown
from .yaml import export_yaml

FORMATS = {
    "json": export_json,
    "csv": export_csv,
    "sqlite": export_sqlite,
    "markdown": export_markdown,
    "yaml": export_yaml,
}

__all__ = [
    "export_json",
    "export_csv",
    "export_sqlite",
    "export_markdown",
    "export_yaml",
    "FORMATS",
]
