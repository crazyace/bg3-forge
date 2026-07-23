import pytest

from bg3forge.pak import lz4compat
from bg3forge.pak.format import CompressionMethod
from bg3forge.parsers import (
    LsfError,
    is_lsf,
    parse_lsf,
    parse_lsx,
    parse_resource,
    write_lsf,
    write_lsx,
)
from bg3forge.parsers.lsx import LsxAttribute, LsxDocument, LsxNode

from conftest import ROOTTEMPLATE_LSX

ALL_TYPES_LSX = """\
<save>
  <region id="AllTypes">
    <node id="AllTypes" key="Name">
      <attribute id="Name" type="FixedString" value="TestObject" />
      <attribute id="Label" type="LSString" value="Ünïcode ✓ label" />
      <attribute id="APath" type="path" value="Public/Shared/Thing.lsf" />
      <attribute id="AString" type="string" value="plain" />
      <attribute id="Level" type="int32" value="-7" />
      <attribute id="Count" type="uint32" value="42" />
      <attribute id="Tiny" type="int8" value="-3" />
      <attribute id="Small" type="uint8" value="200" />
      <attribute id="Sixteen" type="int16" value="-1234" />
      <attribute id="USixteen" type="uint16" value="60000" />
      <attribute id="Big" type="int64" value="-9000000000" />
      <attribute id="UBig" type="uint64" value="18000000000" />
      <attribute id="Ratio" type="float" value="0.5" />
      <attribute id="Precise" type="double" value="0.125" />
      <attribute id="Enabled" type="bool" value="True" />
      <attribute id="Disabled" type="bool" value="False" />
      <attribute id="Position" type="fvec3" value="1.5 -2.5 0.25" />
      <attribute id="Grid" type="ivec2" value="3 -4" />
      <attribute id="Id" type="guid" value="12345678-1234-5678-1234-567812345678" />
      <attribute id="DisplayName" type="TranslatedString" handle="h77777777-7777-7777-7777-777777777777" version="3" />
      <attribute id="Blob" type="ScratchBuffer" value="aGVsbG8=" />
      <children>
        <node id="Child">
          <attribute id="Index" type="int32" value="1" />
        </node>
        <node id="Child">
          <attribute id="Index" type="int32" value="2" />
        </node>
      </children>
    </node>
  </region>
</save>
"""


def _assert_documents_equal(a: LsxDocument, b: LsxDocument):
    assert list(a.regions) == list(b.regions)
    for region_id in a.regions:
        _assert_nodes_equal(a.regions[region_id], b.regions[region_id])


def _assert_nodes_equal(a: LsxNode, b: LsxNode):
    assert a.id == b.id
    assert list(a.attributes) == list(b.attributes)
    for attr_id, attr_a in a.attributes.items():
        attr_b = b.attributes[attr_id]
        assert attr_a.type == attr_b.type, attr_id
        assert attr_a.handle == attr_b.handle, attr_id
        if attr_a.handle is None:
            assert _norm(attr_a) == _norm(attr_b), attr_id
    assert len(a.children) == len(b.children)
    for child_a, child_b in zip(a.children, b.children):
        _assert_nodes_equal(child_a, child_b)


def _norm(attr: LsxAttribute):
    # Numeric text can differ in representation ("0.5" vs repr(0.5)).
    if attr.type in ("float", "double"):
        return float(attr.value)
    if attr.type.startswith(("fvec", "mat")):
        return [float(p) for p in attr.value.split()]
    if attr.type.startswith("ivec"):
        return [int(p) for p in attr.value.split()]
    if attr.type == "guid":
        return attr.value.lower()
    return attr.value


@pytest.mark.parametrize("version", [5, 6, 7])
def test_roundtrip_all_types(version):
    original = parse_lsx(ALL_TYPES_LSX)
    blob = write_lsf(original, version=version)
    assert is_lsf(blob)
    parsed = parse_lsf(blob)
    _assert_documents_equal(original, parsed)
    node = parsed.regions["AllTypes"]
    assert node.attributes["DisplayName"].handle == "h77777777-7777-7777-7777-777777777777"
    assert node.attributes["DisplayName"].version == 3
    assert node.attributes["Enabled"].value == "True"
    assert node.attributes["Id"].value == "12345678-1234-5678-1234-567812345678"
    assert node.attributes["Blob"].value == "aGVsbG8="
    assert [c.attributes["Index"].value for c in node.children] == ["1", "2"]


def test_guid_layout_matches_retail():
    """Larian's LSF guid layout: ``bytes_le`` for the first three groups,
    the last two groups as little-endian 16-bit words.  Frozen against a
    retail-verified pair — the scroll-action ClassId bytes decode to the
    Wizard ClassDescription UUID exactly as Larian's own LSX text writes
    it.  The byte layout matches what earlier releases wrote; only the
    text rendering changed."""
    from bg3forge.parsers.lsf import _guid_from_text, _guid_to_text

    raw = bytes.fromhex("5f9665a81b50e946aa9e4877c0e8094d")
    canonical = "a865965f-501b-46e9-9eaa-7748e8c04d09"
    assert _guid_to_text(raw) == canonical
    assert _guid_from_text(canonical) == raw


def test_keyed_versions_preserve_node_keys():
    original = parse_lsx(ALL_TYPES_LSX)
    # Node keys exist from v6 (VerBG3NodeKeys) on; v5 predates them.
    assert parse_lsf(write_lsf(original, version=7)).regions["AllTypes"].key == "Name"
    assert parse_lsf(write_lsf(original, version=6)).regions["AllTypes"].key == "Name"
    assert parse_lsf(write_lsf(original, version=5)).regions["AllTypes"].key is None


def test_metadata_layout_sizes():
    """Pin the header layout: v5 uses the 40-byte metadata, v6 and v7 the
    48-byte extended metadata (keys sizes) — the split is at SIX.  Getting
    this wrong shifts every section by 8 bytes and broke ~36k retail v6
    files (dialogs, levels, localization) before it was caught."""
    from bg3forge.parsers.lsx import LsxDocument

    empty = LsxDocument()
    name_table = 4 + 512 * 2  # bucket count + 512 empty buckets
    assert len(write_lsf(empty, version=5)) == 8 + 8 + 40 + name_table
    assert len(write_lsf(empty, version=6)) == 8 + 8 + 48 + name_table
    assert len(write_lsf(empty, version=7)) == 8 + 8 + 48 + name_table
    # and the compression flags byte sits right after the size fields
    blob = write_lsf(empty, version=6)
    assert blob[16 + 40] == 0  # CompressionMethod.NONE


def test_roundtrip_roottemplates_matches_lsx():
    original = parse_lsx(ROOTTEMPLATE_LSX)
    parsed = parse_lsf(write_lsf(original))
    _assert_documents_equal(original, parsed)
    objects = list(parsed.find_all("GameObjects"))
    assert len(objects) == 3
    assert objects[2].get("DisplayName") == "h55555555-5555-5555-5555-555555555555"


@pytest.mark.parametrize(
    "compression",
    [
        CompressionMethod.NONE,
        CompressionMethod.ZLIB,
        pytest.param(
            CompressionMethod.LZ4,
            marks=pytest.mark.skipif(
                not lz4compat.HAVE_NATIVE_LZ4, reason="lz4 not installed"
            ),
        ),
    ],
)
def test_compressed_sections(compression):
    original = parse_lsx(ALL_TYPES_LSX)
    for version in (6, 7):
        blob = write_lsf(original, version=version, compression=compression)
        _assert_documents_equal(original, parse_lsf(blob))


@pytest.mark.skipif(not lz4compat.HAVE_NATIVE_LZ4, reason="lz4 not installed")
def test_pure_python_frame_decoder_reads_native_frames():
    import lz4.frame

    data = b"the quick brown fox jumps over the lazy dog " * 200
    assert lz4compat._py_decompress_frame(lz4.frame.compress(data)) == data
    # concatenated frames
    two = lz4.frame.compress(data) + lz4.frame.compress(b"tail")
    assert lz4compat._py_decompress_frame(two) == data + b"tail"


@pytest.mark.skipif(not lz4compat.HAVE_NATIVE_LZ4, reason="lz4 not installed")
def test_lz4_lsf_readable_without_native_lz4(monkeypatch):
    original = parse_lsx(ALL_TYPES_LSX)
    blob = write_lsf(original, version=6, compression=CompressionMethod.LZ4)
    monkeypatch.setattr(lz4compat, "_lz4block", None)
    _assert_documents_equal(original, parse_lsf(blob))


def test_rejects_garbage():
    with pytest.raises(LsfError, match="magic"):
        parse_lsf(b"XXXX" + b"\x00" * 60)
    with pytest.raises(LsfError, match="version"):
        parse_lsf(b"LSOF" + (99).to_bytes(4, "little") + b"\x00" * 60)
    with pytest.raises(LsfError, match="small"):
        parse_lsf(b"LS")


def test_truncated_file():
    blob = write_lsf(parse_lsx(ALL_TYPES_LSX))
    with pytest.raises(LsfError):
        parse_lsf(blob[: len(blob) // 2])


def test_truncated_header_and_metadata():
    """Cuts inside the engine version / metadata structs must raise
    LsfError, not leak struct.error (the Game load_issues contract)."""
    blob = write_lsf(parse_lsx(ALL_TYPES_LSX), version=6)
    for cut in (10, 14, 20, 40, 60):
        with pytest.raises(LsfError):
            parse_lsf(blob[:cut])


def test_corrupt_compressed_section():
    """A corrupt zlib stream must surface as LsfError, not zlib.error."""
    blob = bytearray(
        write_lsf(parse_lsx(ALL_TYPES_LSX), version=6, compression=CompressionMethod.ZLIB)
    )
    start = 16 + 48  # magic+version + engine version + v6 metadata
    blob[start : start + 4] = b"\x00\x00\x00\x00"  # clobber the zlib header
    with pytest.raises(LsfError):
        parse_lsf(bytes(blob))


def test_attribute_chain_guards():
    """V3 first_attr/next_attr are file-controlled: out-of-range and
    negative indices and cyclic chains must all raise LsfError — a cycle
    used to hang the parser forever."""
    from bg3forge.parsers.lsf import _AttrInfo, _NodeInfo, _build_document

    def build(nodes, attrs):
        return _build_document([["N"]], nodes, attrs, {}, b"", True, True)

    with pytest.raises(LsfError, match="invalid attribute"):
        build([_NodeInfo(name_ref=0, parent=-1, first_attr=5)], [])
    with pytest.raises(LsfError, match="invalid attribute"):
        # -2 is a valid *Python* index; it must not silently wrap
        build(
            [_NodeInfo(name_ref=0, parent=-1, first_attr=-2)],
            [_AttrInfo(name_ref=0, type_id=0, length=0, offset=0)],
        )
    with pytest.raises(LsfError, match="loops"):
        build(
            [_NodeInfo(name_ref=0, parent=-1, first_attr=0)],
            [_AttrInfo(name_ref=0, type_id=0, length=0, offset=0, next_attr=0)],
        )


def test_attribute_value_size_guards():
    """The stored value length is independent of the type id; a mismatch
    must raise LsfError instead of struct.error/IndexError."""
    from bg3forge.parsers.lsf import _AttrInfo, _decode_attribute

    def decode(type_id, payload):
        info = _AttrInfo(name_ref=0, type_id=type_id, length=len(payload), offset=0)
        return _decode_attribute([["N"]], info, payload, True)

    with pytest.raises(LsfError, match="needs 4"):
        decode(4, b"\x01\x02")  # int32 with 2 bytes
    with pytest.raises(LsfError, match="needs 12"):
        decode(12, b"\x00" * 4)  # fvec3 with 4 bytes
    with pytest.raises(LsfError, match="bool"):
        decode(19, b"")
    with pytest.raises(LsfError, match="guid"):
        decode(31, b"\x00" * 8)
    with pytest.raises(LsfError, match="TranslatedString"):
        decode(28, b"\x00")  # shorter than its own header


def test_translated_fs_guards():
    import struct

    from bg3forge.parsers.lsf import _decode_translated_fs

    def fs(depth):
        """A TranslatedFSString value nesting one argument per level."""
        leaf = struct.pack("<H", 1) + struct.pack("<i", 1) + b"\x00" + struct.pack("<i", 0)
        if depth == 0:
            return leaf
        inner = fs(depth - 1)
        return (
            struct.pack("<H", 1) + struct.pack("<i", 1) + b"\x00"  # version + handle
            + struct.pack("<i", 1)                                  # one argument
            + struct.pack("<i", 0)                                  # empty key
            + inner
            + struct.pack("<i", 0)                                  # empty value
        )

    handle, version, _ = _decode_translated_fs(fs(3), 0, True)
    assert version == 1

    with pytest.raises(LsfError, match="deeply"):
        _decode_translated_fs(fs(40), 0, True)
    with pytest.raises(LsfError, match="negative"):
        # negative handle length would walk pos backwards
        _decode_translated_fs(struct.pack("<H", 1) + struct.pack("<i", -5), 0, True)
    with pytest.raises(LsfError, match="argument count"):
        _decode_translated_fs(
            struct.pack("<H", 1) + struct.pack("<i", 1) + b"\x00" + struct.pack("<i", -1),
            0,
            True,
        )


def test_byte_flips_never_leak_raw_errors():
    """Contract sweep: flipping any single byte of a valid LSF must either
    still parse or raise LsfError — never struct.error, IndexError, zlib
    errors, or a hang."""
    blob = write_lsf(parse_lsx(ALL_TYPES_LSX), version=6)
    for offset in range(8, len(blob), 3):  # keep the magic intact
        corrupted = bytearray(blob)
        corrupted[offset] ^= 0xFF
        try:
            parse_lsf(bytes(corrupted))
        except LsfError:
            pass


def test_empty_document_roundtrip():
    parsed = parse_lsf(write_lsf(LsxDocument()))
    assert parsed.regions == {}


def test_parse_resource_dispatches():
    document = parse_resource(ROOTTEMPLATE_LSX.encode())
    assert "Templates" in document.regions
    document = parse_resource(write_lsf(parse_lsx(ROOTTEMPLATE_LSX)))
    assert "Templates" in document.regions


def test_write_lsx_roundtrip():
    original = parse_lsx(ALL_TYPES_LSX)
    parsed = parse_lsx(write_lsx(original))
    _assert_documents_equal(original, parsed)
    assert parsed.regions["AllTypes"].key == "Name"


def test_write_lsx_rejects_control_characters():
    """XML 1.0 cannot represent C0 controls at all (not even as character
    references), but ElementTree writes them through verbatim — the
    output used to be rejected by parse_lsx and the game alike."""
    from bg3forge.parsers.lsx import LsxError

    def doc_with(**attr_kwargs):
        document = LsxDocument()
        node = LsxNode(id=attr_kwargs.pop("node_id", "Node"))
        if attr_kwargs:
            attr = LsxAttribute(
                id=attr_kwargs.get("id", "A"),
                type=attr_kwargs.get("type", "LSString"),
                value=attr_kwargs.get("value"),
                handle=attr_kwargs.get("handle"),
            )
            node.attributes[attr.id] = attr
        document.regions[attr_kwargs.get("region", "R")] = node
        return document

    for bad_doc in (
        doc_with(value="bad\x01value"),
        doc_with(id="A\x00B", value="x"),
        doc_with(type="LSString\x1f", value="x"),
        doc_with(handle="h\x08handle"),
        doc_with(node_id="Node\x0b"),
    ):
        with pytest.raises(LsxError, match="control character"):
            write_lsx(bad_doc)

    # Legal XML whitespace round-trips exactly (ElementTree escapes it
    # as character references inside attribute values).
    ok = doc_with(value="line1\nline2\ttabbed")
    parsed = parse_lsx(write_lsx(ok))
    assert parsed.regions["R"].attributes["A"].value == "line1\nline2\ttabbed"
