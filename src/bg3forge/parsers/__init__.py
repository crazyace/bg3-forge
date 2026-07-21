"""Parsers for BG3 data formats."""

from .stats import StatsCollection, StatsEntry, StatsParseError, parse_stats
from .localization import Localization, LocaEntry, LocaError, parse_loca, write_loca
from .lsx import (
    LsxAttribute,
    LsxDocument,
    LsxError,
    LsxNode,
    load_lsx,
    parse_lsx,
    write_lsx,
)
from .lsf import LsfError, is_lsf, load_lsf, parse_lsf, write_lsf
from .resource import load_resource, parse_resource
from .roottemplates import RootTemplate, RootTemplateIndex, parse_root_templates
from .progressions import Progression, parse_progressions
from .treasure import TreasureTable, parse_treasure_tables

__all__ = [
    "StatsCollection",
    "StatsEntry",
    "StatsParseError",
    "parse_stats",
    "Localization",
    "LocaEntry",
    "LocaError",
    "parse_loca",
    "write_loca",
    "LsxAttribute",
    "LsxDocument",
    "LsxError",
    "LsxNode",
    "load_lsx",
    "parse_lsx",
    "write_lsx",
    "LsfError",
    "is_lsf",
    "load_lsf",
    "parse_lsf",
    "write_lsf",
    "load_resource",
    "parse_resource",
    "RootTemplate",
    "RootTemplateIndex",
    "parse_root_templates",
    "Progression",
    "parse_progressions",
    "TreasureTable",
    "parse_treasure_tables",
]
