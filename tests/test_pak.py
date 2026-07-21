import pytest

from bg3forge.pak import (
    CompressionMethod,
    Extractor,
    PakError,
    PakReader,
    PakWriter,
    PatchDetector,
)
from bg3forge.pak import lz4compat

from conftest import fixture_files


@pytest.mark.parametrize(
    "compression",
    [CompressionMethod.NONE, CompressionMethod.ZLIB, CompressionMethod.LZ4],
)
def test_roundtrip(tmp_path, compression):
    files = fixture_files()
    writer = PakWriter(compression=compression)
    for name, data in files.items():
        writer.add(name, data)
    pak_path = writer.write(tmp_path / "test.pak")

    with PakReader(pak_path) as pak:
        assert len(pak) == len(files)
        assert set(pak.names()) == set(files)
        for name, data in files.items():
            assert pak.read(name) == data


def test_read_by_entry_and_contains(sample_pak):
    with PakReader(sample_pak) as pak:
        name = "Localization/English/english.loca"
        assert name in pak
        entry = pak.entry(name)
        assert pak.read(entry) == pak.read(name)
        assert entry.size == len(pak.read(name))


def test_missing_entry_raises(sample_pak):
    with PakReader(sample_pak) as pak:
        with pytest.raises(PakError, match="nope"):
            pak.read("nope")


def test_not_a_pak(tmp_path):
    bogus = tmp_path / "bogus.pak"
    bogus.write_bytes(b"NOPE" + b"\x00" * 100)
    with pytest.raises(ValueError, match="signature"):
        PakReader(bogus)


def test_pure_python_lz4_roundtrip():
    data = b"abcabcabcabc" * 50 + b"tail"
    compressed = lz4compat._py_compress_literals(data)
    assert lz4compat._py_decompress(compressed, len(data)) == data


@pytest.mark.skipif(not lz4compat.HAVE_NATIVE_LZ4, reason="lz4 not installed")
def test_pure_python_decoder_reads_native_blocks():
    import lz4.block

    data = b"the quick brown fox " * 100
    compressed = lz4.block.compress(data, store_size=False)
    assert lz4compat._py_decompress(compressed, len(data)) == data


def test_extractor_incremental(tmp_path, sample_pak):
    out = tmp_path / "out"
    extractor = Extractor(out)
    first = extractor.extract(sample_pak)
    assert len(first.extracted) == len(fixture_files())
    assert not first.skipped
    target = out / "Public/Shared/Stats/Generated/Data/Weapon.txt"
    assert target.read_bytes() == fixture_files()["Public/Shared/Stats/Generated/Data/Weapon.txt"]

    second = Extractor(out).extract(sample_pak)
    assert not second.extracted
    assert len(second.skipped) == len(fixture_files())

    forced = Extractor(out).extract(sample_pak, force=True)
    assert len(forced.extracted) == len(fixture_files())


def test_extractor_patterns(tmp_path, sample_pak):
    out = tmp_path / "out"
    result = Extractor(out).extract(sample_pak, patterns=["*/stats/generated/data/*"])
    assert len(result.extracted) == 6
    assert all("Stats/Generated/Data" in name for name in result.extracted)


def test_patch_detection(tmp_path, data_dir):
    detector = PatchDetector(tmp_path / "snapshot.json")
    report = detector.compare(data_dir)
    assert report.added == ["Shared.pak"]

    detector.update(data_dir)
    assert not detector.compare(data_dir).dirty

    writer = PakWriter()
    writer.add("Public/Shared/Stats/Generated/Data/New.txt", b'new entry "X"\ntype "Weapon"\n')
    writer.write(data_dir / "Patch1.pak")
    report = detector.compare(data_dir)
    assert report.added == ["Patch1.pak"]
    assert not report.changed

    (data_dir / "Patch1.pak").unlink()
    writer = PakWriter()
    writer.add("changed.txt", b"different content")
    writer.write(data_dir / "Shared.pak")
    report = detector.compare(data_dir)
    assert report.changed == ["Shared.pak"]
