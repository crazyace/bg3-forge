"""Parsers for BG3 data formats."""

from .stats import (
    StatsCollection,
    StatsDocument,
    StatsEntry,
    StatsParseError,
    parse_stats,
    parse_stats_document,
)
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
from .lsj import LsjError, is_lsj, parse_lsj
from .resource import load_resource, parse_resource
from .roottemplates import RootTemplate, RootTemplateIndex, parse_root_templates
from .tags import Tag, TagRegistry, parse_tags
from .dialogs import Dialog, DialogError, DialogNode, Speaker, parse_dialog
from .progressions import Progression, parse_progressions
from .treasure import TreasureTable, parse_treasure_tables

__all__ = [
    "StatsCollection",
    "StatsDocument",
    "StatsEntry",
    "StatsParseError",
    "parse_stats",
    "parse_stats_document",
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
    "LsjError",
    "is_lsj",
    "parse_lsj",
    "load_resource",
    "parse_resource",
    "RootTemplate",
    "RootTemplateIndex",
    "parse_root_templates",
    "Tag",
    "TagRegistry",
    "parse_tags",
    "Dialog",
    "DialogError",
    "DialogNode",
    "Speaker",
    "parse_dialog",
    "Progression",
    "parse_progressions",
    "TreasureTable",
    "parse_treasure_tables",
]
