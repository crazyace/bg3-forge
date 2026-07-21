"""Texture atlas definitions (icon UV maps).

Atlas definitions are LSX documents under
``Public/<Mod>/GUI/*.lsx`` describing, for one atlas texture, the UV
rectangle of every icon packed into it::

    <region id="IconUVList">
      <node id="root">
        <children>
          <node id="IconUV">
            <attribute id="MapKey" type="FixedString" value="Spell_Fire_Fireball"/>
            <attribute id="U1" type="float" value="0.0"/>
            <attribute id="V1" type="float" value="0.0"/>
            <attribute id="U2" type="float" value="0.0625"/>
            <attribute id="V2" type="float" value="0.0625"/>
          </node>
          ...

The companion ``TextureAtlasInfo`` region carries the atlas texture path
and dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..parsers.lsx import LsxDocument


@dataclass(frozen=True)
class IconUV:
    name: str
    u1: float
    v1: float
    u2: float
    v2: float

    def pixel_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        """(left, upper, right, lower) pixel rectangle in the atlas."""
        return (
            round(self.u1 * width),
            round(self.v1 * height),
            round(self.u2 * width),
            round(self.v2 * height),
        )


@dataclass
class TextureAtlas:
    texture_path: str | None
    width: int
    height: int
    icon_width: int
    icon_height: int
    icons: dict[str, IconUV]

    def __contains__(self, name: str) -> bool:
        return name in self.icons

    def __iter__(self) -> Iterator[IconUV]:
        return iter(self.icons.values())

    def __len__(self) -> int:
        return len(self.icons)


def parse_atlas(document: LsxDocument) -> TextureAtlas:
    texture_path = None
    width = height = 0
    icon_width = icon_height = 0
    info = document.region("TextureAtlasInfo")
    if info is not None:
        for node in [info, *info.find_all("TextureAtlasPath")]:
            texture_path = node.get("Path", texture_path)
        for node in [info, *info.find_all("TextureAtlasTextureSize")]:
            width = int(node.get("Width", str(width)) or 0)
            height = int(node.get("Height", str(height)) or 0)
        for node in [info, *info.find_all("TextureAtlasIconSize")]:
            icon_width = int(node.get("Width", str(icon_width)) or 0)
            icon_height = int(node.get("Height", str(icon_height)) or 0)

    icons: dict[str, IconUV] = {}
    uv_list = document.region("IconUVList")
    if uv_list is not None:
        for node in uv_list.find_all("IconUV"):
            name = node.get("MapKey")
            if not name:
                continue
            icons[name] = IconUV(
                name=name,
                u1=float(node.get("U1", "0") or 0),
                v1=float(node.get("V1", "0") or 0),
                u2=float(node.get("U2", "0") or 0),
                v2=float(node.get("V2", "0") or 0),
            )
    return TextureAtlas(
        texture_path=texture_path,
        width=width,
        height=height,
        icon_width=icon_width,
        icon_height=icon_height,
        icons=icons,
    )
