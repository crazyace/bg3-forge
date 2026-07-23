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


def test_truncated_pak_raises_pakerror(tmp_path, sample_pak):
    """Truncation anywhere — mid-header, mid-file-list — must raise a
    ValueError subclass, never a raw struct.error (a truncated download
    used to crash Game(), validate_data(), and run_doctor())."""
    blob = sample_pak.read_bytes()
    for cut in (20, 45, len(blob) - 5):
        truncated = tmp_path / f"cut{cut}.pak"
        truncated.write_bytes(blob[:cut])
        with pytest.raises(ValueError):
            PakReader(truncated)


def _file_list_offset(blob: bytes) -> int:
    from bg3forge.pak.format import HEADER_STRUCT

    return HEADER_STRUCT.unpack_from(blob)[2]


def test_implausible_file_count(tmp_path, sample_pak):
    """A corrupt num_files must be rejected before it drives a giant
    allocation in the decompressor."""
    blob = bytearray(sample_pak.read_bytes())
    offset = _file_list_offset(blob)
    blob[offset : offset + 4] = (0x7FFFFFFF).to_bytes(4, "little")
    bad = tmp_path / "huge.pak"
    bad.write_bytes(bytes(blob))
    with pytest.raises(PakError, match="implausible file count"):
        PakReader(bad)


def test_corrupt_file_list(tmp_path, sample_pak):
    blob = bytearray(sample_pak.read_bytes())
    offset = _file_list_offset(blob)
    # Replace the whole compressed table with an endless literal run —
    # invalid for both the native and the pure-Python decoder.
    blob[offset + 8 :] = b"\xff" * (len(blob) - offset - 8)
    bad = tmp_path / "corrupt.pak"
    bad.write_bytes(bytes(blob))
    with pytest.raises(PakError, match="file list"):
        PakReader(bad)


def _write_legacy_pak(path, version):
    """Hand-build a v15/v16 archive in LSLib's FileEntry15 layout: the
    entry table is 296 bytes per entry with u64 offset/size fields, and
    the v15 header carries no num_parts."""
    from bg3forge.pak.format import (
        ENTRY15_STRUCT,
        FILE_LIST_HEADER_STRUCT,
        HEADER15_STRUCT,
        HEADER_STRUCT,
        SIGNATURE,
    )

    content = b"hello from a legacy archive"
    header_size = HEADER15_STRUCT.size if version == 15 else HEADER_STRUCT.size
    name = b"Public/Legacy/file.txt".ljust(256, b"\x00")
    # offset, size_on_disk, uncompressed (0: stored), part, flags, crc, unknown2
    table = ENTRY15_STRUCT.pack(name, header_size, len(content), 0, 0, 0, 0, 0)
    compressed = lz4compat.compress(table)
    file_list = FILE_LIST_HEADER_STRUCT.pack(1, len(compressed)) + compressed
    file_list_offset = header_size + len(content)
    if version == 15:
        header = HEADER15_STRUCT.pack(
            SIGNATURE, version, file_list_offset, len(file_list), 0, 0, b"\x00" * 16
        )
    else:
        header = HEADER_STRUCT.pack(
            SIGNATURE, version, file_list_offset, len(file_list), 0, 0, b"\x00" * 16, 1
        )
    path.write_bytes(header + content + file_list)
    return content


@pytest.mark.parametrize("version", [15, 16])
def test_reads_legacy_entry_layout(tmp_path, version):
    """v15/v16 entries are 296 bytes (FileEntry15), not the 272-byte v18
    layout — parsing them with the v18 struct used to fail on every
    genuine legacy archive."""
    pak_path = tmp_path / f"legacy{version}.pak"
    content = _write_legacy_pak(pak_path, version)
    with PakReader(pak_path) as pak:
        assert pak.names() == ["Public/Legacy/file.txt"]
        assert pak.header.version == version
        assert pak.read("Public/Legacy/file.txt") == content


def test_legacy_struct_sizes_pinned():
    from bg3forge.pak.format import ENTRY15_SIZE, HEADER15_STRUCT, HEADER_STRUCT

    assert ENTRY15_SIZE == 296
    assert HEADER15_STRUCT.size == 38  # no num_parts
    assert HEADER_STRUCT.size == 40


def test_writer_rejects_legacy_versions(tmp_path):
    with pytest.raises(ValueError, match="v18"):
        PakWriter(version=16)


def test_lz4_errors_are_valueerrors():
    """Both LZ4 backends must fail with LZ4Error (a ValueError) — the
    native package's own exceptions don't subclass ValueError and used
    to escape every `except ValueError` in the pipeline."""
    with pytest.raises(lz4compat.LZ4Error) as excinfo:
        lz4compat.decompress(b"\xff" + b"\x00" * 5, 10)
    assert isinstance(excinfo.value, ValueError)

    with pytest.raises(lz4compat.LZ4Error):
        lz4compat.decompress_frame(b"garbage12345")


def test_lz4_size_mismatch_rejected():
    """Native lz4 returns short output when the expected size is larger
    than the real content; both backends must reject the mismatch."""
    compressed = lz4compat.compress(b"exact payload")
    assert lz4compat.decompress(compressed, 13) == b"exact payload"
    with pytest.raises(lz4compat.LZ4Error, match="mismatch|corrupt"):
        lz4compat.decompress(compressed, 100)


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


@pytest.mark.parametrize(
    "entry_name",
    [
        "../escaped.txt",
        "safe/../../escaped.txt",
        "/absolute.txt",
        r"..\escaped.txt",
        r"C:\escaped.txt",
        r"\\server\share\escaped.txt",
    ],
)
def test_extractor_rejects_paths_outside_output(tmp_path, entry_name):
    writer = PakWriter()
    writer.add(entry_name, b"must not be written")
    pak_path = writer.write(tmp_path / "malicious.pak")
    output_dir = tmp_path / "output"

    with pytest.raises(PakError, match="unsafe archive entry path"):
        Extractor(output_dir).extract(pak_path)

    assert not (tmp_path / "escaped.txt").exists()


def test_extractor_rejects_symlink_escape(tmp_path):
    output_dir = tmp_path / "output"
    outside_dir = tmp_path / "outside"
    output_dir.mkdir()
    outside_dir.mkdir()
    try:
        (output_dir / "linked").symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    writer = PakWriter()
    writer.add("linked/escaped.txt", b"must not be written")
    pak_path = writer.write(tmp_path / "symlink.pak")

    with pytest.raises(PakError, match="unsafe archive entry path"):
        Extractor(output_dir).extract(pak_path)

    assert not (outside_dir / "escaped.txt").exists()


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
