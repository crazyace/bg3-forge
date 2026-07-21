"""SQLite exporter."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .base import ensure_parent, normalize

_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _ident(name: str) -> str:
    """Sanitize a name into a safe SQL identifier (quoted at use sites)."""
    cleaned = _IDENT_RE.sub("_", name)
    return cleaned or "_"


def export_sqlite(
    objects: Iterable[Any],
    path: str | Path,
    table: str = "records",
    replace: bool = True,
) -> Path:
    """Write objects into a table of a SQLite database.

    All columns are stored as TEXT except ints/floats which keep their
    affinity.  Re-exporting with ``replace=True`` (default) drops and
    recreates the table so repeated runs are idempotent.
    """
    path = ensure_parent(path)
    records, columns = normalize(objects)
    table_sql = f'"{_ident(table)}"'
    column_idents = [_ident(c) for c in columns]
    with sqlite3.connect(path) as conn:
        if replace:
            conn.execute(f"DROP TABLE IF EXISTS {table_sql}")
        if not columns:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table_sql} (id INTEGER PRIMARY KEY)")
            return path
        column_defs = ", ".join(f'"{c}"' for c in column_idents)
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table_sql} ({column_defs})")
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {table_sql} VALUES ({placeholders})",
            [
                tuple(_scalar(record.get(column)) for column in columns)
                for record in records
            ],
        )
    return path


def _scalar(value: Any):
    if value is None or isinstance(value, (str, int, float)):
        return value
    if isinstance(value, bool):
        return int(value)
    return str(value)
