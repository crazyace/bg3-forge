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


def _write_multipart_pak(tmp_path):
    """Hand-build a two-part v18 archive: PakWriter only emits single-part
    archives, but retail Textures.pak + Textures_1.pak splits are real."""
    from bg3forge.pak.format import (
        FILE_LIST_HEADER_STRUCT,
        HEADER_STRUCT,
        PakEntry,
        PakHeader,
    )

    main_data = b"data living in the main archive"
    part_data = b"data living in the _1 sibling part"
    entries = [
        PakEntry(name="main.txt", offset=HEADER_STRUCT.size, archive_part=0,
                 flags=0, size_on_disk=len(main_data), uncompressed_size=0),
        PakEntry(name="sibling.txt", offset=0, archive_part=1,
                 flags=0, size_on_disk=len(part_data), uncompressed_size=0),
    ]
    table = b"".join(e.pack() for e in entries)
    compressed = lz4compat.compress(table)
    file_list = FILE_LIST_HEADER_STRUCT.pack(len(entries), len(compressed)) + compressed
    header = PakHeader(
        version=18, file_list_offset=HEADER_STRUCT.size + len(main_data),
        file_list_size=len(file_list), flags=0, priority=0,
        md5=b"\x00" * 16, num_parts=2,
    )
    pak_path = tmp_path / "Textures.pak"
    pak_path.write_bytes(header.pack() + main_data + file_list)
    (tmp_path / "Textures_1.pak").write_bytes(part_data)
    return pak_path, main_data, part_data


def test_multipart_pak_reads_from_sibling(tmp_path):
    """Entries with archive_part != 0 read transparently from the _N
    sibling file — previously exercised by zero tests."""
    pak_path, main_data, part_data = _write_multipart_pak(tmp_path)
    with PakReader(pak_path) as pak:
        assert pak.read("main.txt") == main_data
        assert pak.read("sibling.txt") == part_data


def test_multipart_pak_missing_part_raises(tmp_path):
    pak_path, _, _ = _write_multipart_pak(tmp_path)
    (tmp_path / "Textures_1.pak").unlink()
    with PakReader(pak_path) as pak:
        assert pak.read("main.txt")  # part 0 unaffected
        with pytest.raises(PakError, match="missing archive part"):
            pak.read("sibling.txt")


def test_zstd_pak_entry_roundtrip(tmp_path):
    """ZSTD-compressed entries decompress through the optional zstandard
    backend — previously exercised by zero tests."""
    zstd = pytest.importorskip("zstandard")
    from bg3forge.pak.format import (
        FILE_LIST_HEADER_STRUCT,
        HEADER_STRUCT,
        CompressionMethod,
        PakEntry,
        PakHeader,
    )

    payload = b"compressible payload " * 64
    blob = zstd.ZstdCompressor().compress(payload)
    entry = PakEntry(
        name="zstd.bin", offset=HEADER_STRUCT.size, archive_part=0,
        flags=int(CompressionMethod.ZSTD), size_on_disk=len(blob),
        uncompressed_size=len(payload),
    )
    table = entry.pack()
    compressed = lz4compat.compress(table)
    file_list = FILE_LIST_HEADER_STRUCT.pack(1, len(compressed)) + compressed
    header = PakHeader(
        version=18, file_list_offset=HEADER_STRUCT.size + len(blob),
        file_list_size=len(file_list), flags=0, priority=0,
        md5=b"\x00" * 16, num_parts=1,
    )
    pak_path = tmp_path / "zstd.pak"
    pak_path.write_bytes(header.pack() + blob + file_list)
    with PakReader(pak_path) as pak:
        assert pak.read("zstd.bin") == payload


def test_golden_entry_and_header_bytes():
    """Pin the on-disk layouts against drift: exact pack() bytes and the
    parse of a known-good byte string, independent of any writer."""
    from bg3forge.pak.format import PakEntry, PakHeader

    header = PakHeader(version=18, file_list_offset=0x11223344, file_list_size=0x55,
                       flags=1, priority=2, md5=bytes(range(16)), num_parts=3)
    packed = header.pack()
    assert packed.hex() == (
        "4c53504b"          # LSPK
        "12000000"          # version 18
        "4433221100000000"  # file_list_offset u64
        "55000000"          # file_list_size u32
        "01" "02"           # flags, priority
        "000102030405060708090a0b0c0d0e0f"
        "0300"              # num_parts u16
    )
    assert PakHeader.parse(packed) == header

    entry = PakEntry(name="a/b.txt", offset=0x0000A1B2C3D4, archive_part=1,
                     flags=2, size_on_disk=0x100, uncompressed_size=0x200)
    packed = entry.pack()
    assert len(packed) == 272
    assert packed[:7] == b"a/b.txt" and packed[7:256] == bytes(249)
    assert packed[256:].hex() == (
        "d4c3b2a1"  # offset low u32
        "0000"      # offset high u16
        "01" "02"   # archive_part, flags
        "00010000"  # size_on_disk u32
        "00020000"  # uncompressed_size u32
    )
    assert PakEntry.parse(packed) == entry


def test_parse_all_matches_per_entry_parse():
    """The bulk iter_unpack path must produce byte-identical entries to
    the per-offset parse, for both v18 and v15/v16 layouts."""
    from bg3forge.pak.format import (
        ENTRY15_STRUCT,
        ENTRY_SIZE,
        ENTRY15_SIZE,
        ENTRY_STRUCT,
        PakEntry,
    )

    v18 = b"".join(
        ENTRY_STRUCT.pack(f"P/f{i}.lsf".encode().ljust(256, b"\x00"),
                          i * 7 & 0xFFFFFFFF, i % 4, i % 3, 2, 100 + i, 200 + i)
        for i in range(50)
    )
    assert PakEntry.parse_all(v18, 18) == [
        PakEntry.parse(v18, i * ENTRY_SIZE) for i in range(50)
    ]

    v15 = b"".join(
        ENTRY15_STRUCT.pack(f"P/f{i}.lsf".encode().ljust(256, b"\x00"),
                            i * 9, 100 + i, 200 + i, i % 4, i % 3, 0, 0)
        for i in range(50)
    )
    assert PakEntry.parse_all(v15, 16) == [
        PakEntry.parse15(v15, i * ENTRY15_SIZE) for i in range(50)
    ]


def test_guard_size_rejects_implausible_declared_size():
    """A tiny compressed input declaring a huge output is rejected before
    any native decompressor pre-allocates that many bytes."""
    from bg3forge.pak.lz4compat import (
        DecompressionBombError,
        MAX_RATIO_LZ4,
        guard_size,
    )

    guard_size(1000, 200_000, MAX_RATIO_LZ4, "ok")  # 200x — within bound
    with pytest.raises(DecompressionBombError, match="implausible"):
        guard_size(100, 1_000_000_000, MAX_RATIO_LZ4, "bomb")  # ~10Mx


def test_zlib_decompress_roundtrip_and_corruption():
    import zlib

    from bg3forge.pak.lz4compat import LZ4Error, zlib_decompress

    payload = b"repeatable stats data " * 500
    assert zlib_decompress(zlib.compress(payload)) == payload
    with pytest.raises(LZ4Error, match="corrupt zlib"):
        zlib_decompress(b"definitely not a zlib stream")


def test_zlib_decompress_bounds_expansion():
    """The self-bound trips when the declared input hint is far smaller
    than the real expansion (the bomb shape)."""
    import zlib

    from bg3forge.pak.lz4compat import DecompressionBombError, zlib_decompress

    stream = zlib.compress(b"\x00" * 5_000_000)  # ~5 MB of zeros, tiny stream
    # Claiming the stream is only a handful of bytes makes 5 MB implausible.
    with pytest.raises(DecompressionBombError, match="1032"):
        zlib_decompress(stream, compressed_hint=8)


@pytest.mark.skipif(not lz4compat.HAVE_NATIVE_LZ4, reason="lz4 not installed")
def test_frame_decode_bounded_native():
    from bg3forge.pak.lz4compat import DecompressionBombError, compress_frame, decompress_frame

    payload = b"the quick brown fox " * 10_000
    frame = compress_frame(payload)
    assert decompress_frame(frame, max_output_size=len(payload)) == payload
    with pytest.raises(DecompressionBombError, match="exceeds bound"):
        decompress_frame(frame, max_output_size=1000)


@pytest.mark.skipif(not lz4compat.HAVE_NATIVE_LZ4, reason="lz4 not installed")
def test_frame_decode_bounded_pure():
    """The pure-Python frame decoder honors the same bound (frame built
    with native lz4, decoded by the fallback)."""
    import lz4.frame

    from bg3forge.pak.lz4compat import DecompressionBombError, _py_decompress_frame

    # Keep within one frame block: the pure decoder decodes blocks
    # independently and does not resolve cross-block (linked) matches.
    payload = b"pure python frame payload " * 300
    frame = lz4.frame.compress(payload)
    assert _py_decompress_frame(frame, max_output_size=len(payload)) == payload
    with pytest.raises(DecompressionBombError, match="exceeds bound"):
        _py_decompress_frame(frame, max_output_size=200)


def test_pak_entry_rejects_decompression_bomb(tmp_path):
    """End to end: a pak entry whose header lies about its uncompressed
    size (tiny LZ4 payload, 2 GB declared) fails with PakError rather than
    attempting a 2 GB allocation."""
    from bg3forge.pak.format import (
        FILE_LIST_HEADER_STRUCT,
        HEADER_STRUCT,
        CompressionMethod,
        PakEntry,
        PakHeader,
    )

    blob = lz4compat.compress(b"small")
    entry = PakEntry(
        name="bomb.bin", offset=HEADER_STRUCT.size, archive_part=0,
        flags=int(CompressionMethod.LZ4), size_on_disk=len(blob),
        uncompressed_size=2_000_000_000,
    )
    table = lz4compat.compress(entry.pack())
    file_list = FILE_LIST_HEADER_STRUCT.pack(1, len(table)) + table
    header = PakHeader(
        version=18, file_list_offset=HEADER_STRUCT.size + len(blob),
        file_list_size=len(file_list), flags=0, priority=0,
        md5=b"\x00" * 16, num_parts=1,
    )
    pak_path = tmp_path / "bomb.pak"
    pak_path.write_bytes(header.pack() + blob + file_list)
    with PakReader(pak_path) as pak:
        with pytest.raises(PakError, match="implausible|bomb"):
            pak.read("bomb.bin")


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


def test_extractor_persists_manifest_on_failure(tmp_path, sample_pak, monkeypatch):
    """If the loop aborts mid-pak, files already written must stay in the
    manifest so a re-run resumes instead of re-extracting everything."""
    out = tmp_path / "out"
    extractor = Extractor(out)
    reader = PakReader(sample_pak)
    entries = list(reader)
    boom_name = entries[2].name
    real_read = reader.read

    def read(entry):
        if getattr(entry, "name", None) == boom_name:
            raise PakError("simulated disk failure")
        return real_read(entry)

    monkeypatch.setattr(reader, "read", read)
    with pytest.raises(PakError, match="simulated"):
        extractor.extract(reader)
    reader.close()

    # The first two entries were written and recorded before the failure.
    resumed = Extractor(out).extract(sample_pak)
    assert boom_name in resumed.extracted            # the failed one now writes
    assert entries[0].name in resumed.skipped        # earlier ones already done
    assert entries[1].name in resumed.skipped


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


@pytest.mark.parametrize(
    "entry_name",
    [
        "Public/file.txt:stream",       # NTFS alternate data stream
        "Public/CON",                    # reserved device name
        "Public/nul.txt",                # reserved name with extension
        "COM1/inner.txt",                # reserved name as a directory
    ],
)
def test_extractor_rejects_windows_hazards(tmp_path, entry_name):
    """Colons (NTFS ADS) and reserved device names are rejected even
    though they pass the traversal checks."""
    writer = PakWriter()
    writer.add(entry_name, b"must not be written")
    pak_path = writer.write(tmp_path / "hazard.pak")
    with pytest.raises(PakError, match="unsafe archive entry path"):
        Extractor(tmp_path / "out").extract(pak_path)


def test_safe_output_path_accepts_normal_bg3_paths(tmp_path):
    """The Windows-hazard checks must not reject legitimate archive paths
    (device-name prefixes as substrings, dotted names)."""
    from bg3forge._paths import safe_output_path

    for ok in (
        "Public/Shared/Stats/Generated/Data/Weapon.txt",
        "Mods/CONtent/file.lsx",         # 'CON' only as a prefix, not the component
        "Public/Auxiliary/thing.lsf",    # 'AUX' only as a prefix
        "Localization/English/english.loca",
    ):
        safe_output_path(tmp_path, ok)  # does not raise


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
