import pytest

from bg3forge.assets import parse_atlas, IconExtractor, match_icons
from bg3forge.parsers.lsx import parse_lsx

from conftest import ATLAS_LSX


@pytest.fixture
def atlas():
    return parse_atlas(parse_lsx(ATLAS_LSX))


def test_parse_atlas(atlas):
    assert atlas.texture_path == "Assets/Textures/Icons/Icons_Items.dds"
    assert (atlas.width, atlas.height) == (128, 128)
    assert (atlas.icon_width, atlas.icon_height) == (64, 64)
    assert len(atlas) == 2
    uv = atlas.icons["Spell_Evocation_Fireball"]
    assert uv.pixel_box(128, 128) == (64, 0, 128, 64)


def test_match_icons(atlas):
    class Obj:
        def __init__(self, icon):
            self.icon = icon

    matched = match_icons([Obj("Item_WPN_Longsword"), Obj("Unknown_Icon"), Obj(None)], [atlas])
    assert set(matched) == {"Item_WPN_Longsword"}
    assert matched["Item_WPN_Longsword"] is atlas


def test_icon_extraction(tmp_path, atlas):
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    # Build a 128x128 texture: left half red, right half blue.
    texture = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
    for x in range(64, 128):
        for y in range(64):
            texture.putpixel((x, y), (0, 0, 255, 255))
    texture_path = tmp_path / "atlas.png"
    texture.save(texture_path)

    extractor = IconExtractor(atlas, texture_path)
    fireball = extractor.extract("Spell_Evocation_Fireball")
    assert fireball.size == (64, 64)
    assert fireball.getpixel((10, 10)) == (0, 0, 255, 255)

    result = extractor.export_all(tmp_path / "icons", format="png")
    assert sorted(result.written) == ["Item_WPN_Longsword", "Spell_Evocation_Fireball"]
    assert (tmp_path / "icons" / "Item_WPN_Longsword.png").exists()

    webp = extractor.export("Item_WPN_Longsword", tmp_path / "icons", format="webp")
    assert webp.suffix == ".webp" and webp.exists()


def test_icon_extraction_requires_pillow_or_errors(atlas, tmp_path):
    from bg3forge.assets.icons import IconError

    extractor = IconExtractor(atlas, tmp_path / "missing.dds")
    with pytest.raises((IconError, Exception)):
        extractor.extract("Item_WPN_Longsword")
