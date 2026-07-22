"""Build (and read back) a module manifest — ``Mods/<Folder>/meta.lsx``.

Every BG3 mod is announced to the engine by a ``meta.lsx`` describing one
``ModuleInfo``: its name, folder, UUID, packed version, and a handful of
housekeeping fields.  :func:`build_meta_document` assembles the standard
modern layout as an :class:`~bg3forge.parsers.lsx.LsxDocument` that
:func:`~bg3forge.parsers.lsx.write_lsx` serializes into a game-readable
file; :func:`parse_meta` reads one back.

This is a write primitive for programmatic mod authoring — the manifest
half of creating a new mod, alongside the stats and RootTemplate content.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lsf import pack_version64, unpack_version64
from .lsx import LsxAttribute, LsxDocument, LsxError, LsxNode


@dataclass
class ModuleInfo:
    """The identity of a mod module, as carried by ``meta.lsx``."""

    name: str
    uuid: str
    folder: str = ""  # defaults to ``name`` when left blank
    author: str = ""
    description: str = ""
    version: tuple[int, int, int, int] = (1, 0, 0, 0)
    mod_type: str = "Add-on"

    def __post_init__(self) -> None:
        self.folder = self.folder or self.name
        self.version = tuple(self.version)  # normalize list -> tuple for equality


def _attr(attr_id: str, attr_type: str, value: str) -> LsxAttribute:
    return LsxAttribute(id=attr_id, type=attr_type, value=value)


# ModuleInfo housekeeping fields the game expects present, even if empty.
_EMPTY_FIXED = (
    "CharacterCreationLevelName",
    "GMTemplate",
    "LobbyLevelName",
    "MainMenuBackgroundVideo",
    "MenuLevelName",
    "PhotoBooth",
    "StartupLevelName",
)


def build_meta_document(module: ModuleInfo) -> LsxDocument:
    """Assemble the ``Config`` region for a module's ``meta.lsx``.

    Serialize the result with :func:`bg3forge.parsers.lsx.write_lsx`.
    """
    version64 = str(pack_version64(*module.version))

    attributes = {
        "Author": _attr("Author", "LSString", module.author),
        "Description": _attr("Description", "LSString", module.description),
        "Folder": _attr("Folder", "LSString", module.folder),
        "MD5": _attr("MD5", "LSString", ""),
        "Name": _attr("Name", "LSString", module.name),
        "NumPlayers": _attr("NumPlayers", "uint8", "4"),
        "Tags": _attr("Tags", "LSString", ""),
        "Type": _attr("Type", "FixedString", module.mod_type),
        "UUID": _attr("UUID", "FixedString", module.uuid),
        "Version64": _attr("Version64", "int64", version64),
    }
    for field_id in _EMPTY_FIXED:
        attributes[field_id] = _attr(field_id, "FixedString", "")

    module_info = LsxNode(
        id="ModuleInfo",
        attributes=dict(sorted(attributes.items())),
        children=[
            LsxNode(
                id="PublishVersion",
                attributes={"Version64": _attr("Version64", "int64", version64)},
            ),
            LsxNode(id="Scripts"),
            LsxNode(
                id="TargetModes",
                children=[
                    LsxNode(
                        id="Target",
                        attributes={"Object": _attr("Object", "FixedString", "Story")},
                    )
                ],
            ),
        ],
    )

    root = LsxNode(id="root", children=[LsxNode(id="Dependencies"), module_info])
    return LsxDocument(regions={"Config": root})


def parse_meta(document: LsxDocument) -> ModuleInfo:
    """Read a module's identity back out of a parsed ``meta.lsx``.

    The inverse of :func:`build_meta_document` at the identity level.
    Raises :class:`~bg3forge.parsers.lsx.LsxError` if no ``ModuleInfo`` is
    present.
    """
    for node in document.find_all("ModuleInfo"):
        raw_version = node.get("Version64")
        version = unpack_version64(int(raw_version)) if raw_version else (0, 0, 0, 0)
        return ModuleInfo(
            name=node.get("Name", "") or "",
            uuid=node.get("UUID", "") or "",
            folder=node.get("Folder", "") or "",
            author=node.get("Author", "") or "",
            description=node.get("Description", "") or "",
            version=version,
            mod_type=node.get("Type", "Add-on") or "Add-on",
        )
    raise LsxError("no ModuleInfo node in meta document")
