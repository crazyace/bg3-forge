"""Extract individual icons from DDS atlas textures.

Requires Pillow (``pip install bg3forge[icons]``), which decodes the
DXT/BC-compressed DDS atlases the game ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .._paths import UnsafePathError, safe_output_path
from .atlases import TextureAtlas


class IconError(RuntimeError):
    pass


def _load_pillow():
    try:
        from PIL import Image
    except ImportError:
        raise IconError(
            "icon extraction requires Pillow; install with: pip install bg3forge[icons]"
        ) from None
    return Image


@dataclass
class IconExportResult:
    written: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class IconExtractor:
    """Slice a DDS atlas into individual icon images.

    Usage::

        extractor = IconExtractor(atlas, "extracted/.../Icons_Skills.dds")
        extractor.export_all("out/icons", format="png")
    """

    def __init__(self, atlas: TextureAtlas, texture_path: str | Path):
        self.atlas = atlas
        self.texture_path = Path(texture_path)
        self._image = None

    def _image_handle(self):
        if self._image is None:
            Image = _load_pillow()
            try:
                self._image = Image.open(self.texture_path).convert("RGBA")
            except OSError as exc:
                raise IconError(f"cannot decode atlas texture {self.texture_path}: {exc}")
        return self._image

    def extract(self, icon_name: str):
        """Return a PIL image for one icon."""
        uv = self.atlas.icons.get(icon_name)
        if uv is None:
            raise IconError(f"icon {icon_name!r} not in atlas")
        image = self._image_handle()
        return image.crop(uv.pixel_box(image.width, image.height))

    def export(
        self,
        icon_name: str,
        output_dir: str | Path,
        format: str = "png",
        lossless: bool = True,
    ) -> Path:
        """Write one icon as PNG or WebP; returns the written path."""
        output_format = format.lower()
        if output_format not in {"png", "webp"}:
            raise IconError(f"unsupported icon format: {format}")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            target = safe_output_path(output_dir, f"{icon_name}.{output_format}")
        except UnsafePathError as exc:
            raise IconError(f"unsafe icon output name {icon_name!r}: {exc}") from None
        icon = self.extract(icon_name)
        if output_format == "webp":
            icon.save(target, format="WEBP", lossless=lossless)
        else:
            icon.save(target, format="PNG")
        return target

    def export_all(
        self,
        output_dir: str | Path,
        format: str = "png",
        names: Iterable[str] | None = None,
    ) -> IconExportResult:
        result = IconExportResult()
        wanted = list(names) if names is not None else [uv.name for uv in self.atlas]
        for name in wanted:
            if name not in self.atlas:
                result.missing.append(name)
                continue
            self.export(name, output_dir, format=format)
            result.written.append(name)
        return result


def match_icons(objects: Iterable, atlases: Iterable[TextureAtlas]) -> dict[str, TextureAtlas]:
    """Map each object's ``icon`` name to the atlas that contains it.

    ``objects`` is any iterable of models with an ``icon`` attribute
    (Items, Spells, …).  Returns ``{icon_name: atlas}`` for every icon
    that was found; look at the difference with the input to find
    unmatched icons.
    """
    atlas_list = list(atlases)
    matched: dict[str, TextureAtlas] = {}
    for obj in objects:
        icon = getattr(obj, "icon", None)
        if not icon or icon in matched:
            continue
        for atlas in atlas_list:
            if icon in atlas:
                matched[icon] = atlas
                break
    return matched
