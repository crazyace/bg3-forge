"""Tests for flag-gated / unreachable dialog discovery (``bg3forge secrets``)."""

import json
from dataclasses import replace

import pytest

from bg3forge import Game
from bg3forge.hidden import (
    analyze_dialog,
    find_hidden,
    format_report,
    game_names,
    scope_counts,
    to_records,
)
from bg3forge.parsers import parse_dialog, parse_lsx
from bg3forge.parsers.lsf import write_lsf
from bg3forge.parsers.localization import LocaEntry, write_loca
from bg3forge.pak.writer import PakWriter

# One dialog exercising every shape the analysis reads: an ungated
# greeting, a branch gated by one flag, a deeper branch that re-checks
# that flag and adds two more (the re-check must not count twice), a
# negated check, and a node nothing links to.
SECRET_DIALOG_LSX = """\
<save>
  <region id="dialog">
    <node id="dialog">
      <attribute id="UUID" type="FixedString" value="dddd0000-0000-0000-0000-0000000000s1" />
      <attribute id="category" type="LSString" value="Companion" />
      <children>
        <node id="speakerlist">
          <children>
            <node id="speaker">
              <attribute id="index" type="FixedString" value="0" />
            </node>
          </children>
        </node>
        <node id="nodes">
          <children>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="greeting" />
              <attribute id="constructor" type="FixedString" value="TagGreeting" />
              <attribute id="speaker" type="int32" value="0" />
              <attribute id="Root" type="bool" value="True" />
              {greeting_text}
              <children>
                <node id="children">
                  <children>
                    <node id="child">
                      <attribute id="UUID" type="FixedString" value="gated" />
                    </node>
                    <node id="child">
                      <attribute id="UUID" type="FixedString" value="negated" />
                    </node>
                  </children>
                </node>
              </children>
            </node>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="gated" />
              <attribute id="constructor" type="FixedString" value="TagAnswer" />
              <attribute id="speaker" type="int32" value="0" />
              {gated_text}
              <children>
                {checks_one}
                <node id="children">
                  <children>
                    <node id="child">
                      <attribute id="UUID" type="FixedString" value="deep" />
                    </node>
                  </children>
                </node>
              </children>
            </node>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="deep" />
              <attribute id="constructor" type="FixedString" value="TagQuestion" />
              <attribute id="speaker" type="int32" value="0" />
              <attribute id="endnode" type="bool" value="True" />
              {deep_text}
              <children>
                {checks_three}
              </children>
            </node>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="negated" />
              <attribute id="constructor" type="FixedString" value="TagAnswer" />
              <attribute id="speaker" type="int32" value="0" />
              <attribute id="endnode" type="bool" value="True" />
              {negated_text}
              <children>
                {checks_negated}
              </children>
            </node>
            <node id="node">
              <attribute id="UUID" type="FixedString" value="cut" />
              <attribute id="constructor" type="FixedString" value="TagAnswer" />
              <attribute id="speaker" type="int32" value="0" />
              <attribute id="endnode" type="bool" value="True" />
              {cut_text}
            </node>
          </children>
        </node>
      </children>
    </node>
  </region>
</save>
"""


def _text(handle: str) -> str:
    return f"""\
              <children>
                <node id="TaggedTexts"><children><node id="TaggedText">
                  <children><node id="TagTexts"><children><node id="TagText">
                    <attribute id="TagText" type="TranslatedString" handle="{handle}" version="1" />
                  </node></children></node></children>
                </node></children></node>
              </children>"""


def _flags(*specs: tuple[str, str, bool], wrapper: str = "checkflags") -> str:
    groups = []
    for scope, uuid, value in specs:
        groups.append(
            f"""\
                  <node id="flaggroup">
                    <attribute id="type" type="FixedString" value="{scope}" />
                    <children>
                      <node id="flag">
                        <attribute id="UUID" type="FixedString" value="{uuid}" />
                        <attribute id="value" type="bool" value="{value}" />
                        <attribute id="paramval" type="int32" value="0" />
                      </node>
                    </children>
                  </node>"""
        )
    inner = "\n".join(groups)
    return f'<node id="{wrapper}">\n  <children>\n{inner}\n  </children>\n</node>'


MET_FLAG = "aaaa1111-0000-0000-0000-0000000000f1"
TRUST_FLAG = "aaaa1111-0000-0000-0000-0000000000f2"
NIGHT_FLAG = "aaaa1111-0000-0000-0000-0000000000f3"
HOSTILE_FLAG = "aaaa1111-0000-0000-0000-0000000000f4"
TAG_UUID = "cccc2222-0000-0000-0000-0000000000a1"

DIALOG_LSX = SECRET_DIALOG_LSX.format(
    greeting_text=_text("hbbbb0000-0000-0000-0000-0000000000t1"),
    gated_text=_text("hbbbb0000-0000-0000-0000-0000000000t2"),
    deep_text=_text("hbbbb0000-0000-0000-0000-0000000000t3"),
    negated_text=_text("hbbbb0000-0000-0000-0000-0000000000t4"),
    cut_text=_text("hbbbb0000-0000-0000-0000-0000000000t5"),
    checks_one=_flags(("Global", MET_FLAG, "True")),
    # re-checks MET_FLAG (already satisfied upstream) and adds two more
    checks_three=_flags(
        ("Global", MET_FLAG, "True"),
        ("Object", TRUST_FLAG, "True"),
        ("Global", NIGHT_FLAG, "True"),
    ),
    # a world-state check and a party-composition check on one node
    checks_negated=_flags(
        ("Global", HOSTILE_FLAG, "False"), ("Tag", TAG_UUID, "True")
    ),
)

# A registry naming three of the four flags; the fourth stays a UUID.
FLAGS_LSX = f"""\
<save>
  <region id="Flags">
    <node id="root">
      <children>
        <node id="Flag">
          <attribute id="UUID" type="guid" value="{MET_FLAG}" />
          <attribute id="Name" type="LSString" value="COMP_MetInTavern" />
        </node>
        <node id="Flag">
          <attribute id="UUID" type="guid" value="{TRUST_FLAG}" />
          <attribute id="Name" type="LSString" value="COMP_TrustsYou" />
        </node>
        <node id="Flag">
          <attribute id="UUID" type="guid" value="{NIGHT_FLAG}" />
          <attribute id="Name" type="LSString" value="GLO_Night" />
        </node>
      </children>
    </node>
  </region>
</save>
"""

# Tag registry entry, the other half of the name resolution story.
TAGS_LSX = f"""\
<save>
  <region id="Tags">
    <node id="Tags">
      <attribute id="UUID" type="guid" value="{TAG_UUID}" />
      <attribute id="Name" type="FixedString" value="ASTARION" />
    </node>
  </region>
</save>
"""

LOCA = [
    LocaEntry("hbbbb0000-0000-0000-0000-0000000000t1", 1, "Well met."),
    LocaEntry("hbbbb0000-0000-0000-0000-0000000000t2", 1, "You again."),
    LocaEntry("hbbbb0000-0000-0000-0000-0000000000t3", 1, "I dreamt of\n you."),
    LocaEntry("hbbbb0000-0000-0000-0000-0000000000t4", 1, "Peace between us, then."),
    LocaEntry("hbbbb0000-0000-0000-0000-0000000000t5", 1, "The tadpole sings to me."),
]

DIALOG_PATH = "Mods/Shared/Story/DialogsBinary/Companion/COMP_Secret.lsf"


@pytest.fixture
def secrets_dir(tmp_path):
    """A Data dir holding one dialog, its flag registry, and localization."""
    writer = PakWriter()
    writer.add(DIALOG_PATH, write_lsf(parse_lsx(DIALOG_LSX), version=6))
    writer.add("Mods/Shared/Story/Flags/Companion.lsx", FLAGS_LSX.encode())
    writer.add(f"Public/Shared/Tags/{TAG_UUID}.lsx", TAGS_LSX.encode())
    writer.add("Localization/English/english.loca", write_loca(LOCA))
    return writer.write(tmp_path / "Secrets.pak").parent


# -- parser ------------------------------------------------------------------

def test_parse_dialog_reads_flag_conditions():
    dialog = parse_dialog(parse_lsx(DIALOG_LSX))
    gated = dialog.node("gated")
    assert [group.type for group in gated.check_flags] == ["Global"]
    (scope, flag), = gated.checks
    assert (scope, flag.uuid, flag.value, flag.paramval) == ("Global", MET_FLAG, True, 0)

    negated = dialog.node("negated")
    (_scope, hostile), (tag_scope, tag) = negated.checks
    assert hostile.uuid == HOSTILE_FLAG and hostile.value is False
    assert (tag_scope, tag.uuid) == ("Tag", TAG_UUID)

    assert dialog.node("greeting").checks == []
    assert dialog.node("greeting").set_flags == []


def test_flag_parsing_tolerates_casing_and_junk():
    """LSF and LSJ do not agree with LSX on casing, and an authored flag
    can be missing the UUID that makes it meaningful."""
    lsx = """\
<save><region id="dialog"><node id="dialog">
  <attribute id="UUID" type="FixedString" value="d1" />
  <children><node id="nodes"><children>
    <node id="node">
      <attribute id="UUID" type="FixedString" value="n1" />
      <children>
        <node id="CheckFlags"><children>
          <node id="FlagGroup">
            <attribute id="Type" type="FixedString" value="Object" />
            <children>
              <node id="Flag">
                <attribute id="uuid" type="FixedString" value="f1" />
                <attribute id="Value" type="bool" value="1" />
                <attribute id="ParamVal" type="LSString" value="not-a-number" />
              </node>
              <node id="Flag">
                <attribute id="Value" type="bool" value="True" />
              </node>
              <node id="comment"><attribute id="text" type="LSString" value="x" /></node>
            </children>
          </node>
        </children></node>
        <node id="SetFlags"><children>
          <node id="flaggroup"><children>
            <node id="flag"><attribute id="UUID" type="FixedString" value="f2" /></node>
          </children></node>
        </children></node>
      </children>
    </node>
  </children></node></children>
</node></region></save>
"""
    node = parse_dialog(parse_lsx(lsx)).node("n1")
    (scope, flag), = node.checks  # the UUID-less flag is dropped
    assert (scope, flag.uuid, flag.value, flag.paramval) == ("Object", "f1", True, None)
    assert node.set_flags[0].type == ""  # group with no type attribute
    assert node.set_flags[0].flags[0].uuid == "f2"


def test_orphans_and_entry_points():
    dialog = parse_dialog(parse_lsx(DIALOG_LSX))
    assert [node.uuid for node in dialog.orphans()] == ["cut"]
    assert [node.uuid for node in dialog.entry_points] == ["greeting"]
    assert "cut" not in {node.uuid for node in dialog.walk()}


def test_entry_points_fall_back_to_graph_sources():
    """A dialog that marks no Root still walks from its sources, instead
    of reporting every node as unreachable."""
    lsx = DIALOG_LSX.replace('<attribute id="Root" type="bool" value="True" />', "")
    dialog = parse_dialog(parse_lsx(lsx))
    assert [node.uuid for node in dialog.entry_points] == ["greeting", "cut"]
    assert [node.uuid for node in dialog.walk()] == [
        "greeting", "gated", "deep", "negated", "cut",
    ]


# -- analysis -----------------------------------------------------------------

def test_analyze_dialog_counts_the_cheapest_condition_path():
    dialog = parse_dialog(parse_lsx(DIALOG_LSX))
    lines = analyze_dialog(
        dialog,
        names={MET_FLAG: "COMP_MetInTavern", TRUST_FLAG: "COMP_TrustsYou"},
        resolve=lambda handle: {"hbbbb0000-0000-0000-0000-0000000000t2": "You again."}.get(
            handle, "text"
        ),
        path=DIALOG_PATH,
    )
    by_node = {line.node: line for line in lines}

    # the ungated greeting is not hidden and is left out entirely
    assert "greeting" not in by_node
    assert by_node["gated"].gate_count == 1
    assert by_node["gated"].text == "You again."

    # inherits the parent's flag, re-checks it once (counted once), adds two
    deep = by_node["deep"]
    assert deep.gate_count == 3
    assert [condition.label for condition in deep.conditions] == [
        "Global:COMP_MetInTavern",
        "Object:COMP_TrustsYou",
        f"Global:{NIGHT_FLAG}",  # unnamed flags keep their UUID
    ]

    # a false-valued check reads as a negation
    assert by_node["negated"].conditions[0].label == f"not Global:{HOSTILE_FLAG}"

    # unreachable nodes are reported even with no conditions of their own
    assert by_node["cut"].kind == "orphan" and by_node["cut"].gate_count == 0
    assert by_node["gated"].kind == "gated"

    # most-gated first, orphans ahead of equally-gated lines
    assert [line.node for line in lines] == ["deep", "negated", "gated", "cut"]


def test_dangling_links_do_not_break_the_search():
    """Retail dialogs link to node UUIDs that are not in the file; the
    condition search must step over them, not fail."""
    lsx = DIALOG_LSX.replace('value="deep" />\n', 'value="ghost" />\n', 1)
    lines = analyze_dialog(parse_dialog(parse_lsx(lsx)), resolve=lambda handle: "text")
    # "deep" is now linked by nothing, so it becomes an orphan carrying
    # only its own three checks -- the inherited one is gone with the edge.
    by_node = {line.node: line for line in lines}
    assert by_node["deep"].kind == "orphan" and by_node["deep"].gate_count == 3
    assert str(by_node["gated"].conditions[0]) == f"Global:{MET_FLAG}"


def test_tag_scope_resolves_through_the_tag_registry(secrets_dir):
    """Tag-scope conditions name entries in the tag registry, not story
    flags; retail prints a wall of GUIDs unless both are consulted."""
    game = Game(data_dir=secrets_dir)
    lookup = game_names(game)
    assert lookup("Tag", TAG_UUID.upper()) == "ASTARION"
    assert lookup("Global", MET_FLAG) == "COMP_MetInTavern"
    # a Tag UUID no registry knows falls through rather than inventing one
    assert lookup("Tag", HOSTILE_FLAG) is None

    tagged = [line for line in find_hidden(game).lines if line.node == "negated"][0]
    assert tagged.conditions[-1].label == "Tag:ASTARION"


def test_scope_filter_counts_only_the_scopes_asked_for(secrets_dir):
    game = Game(data_dir=secrets_dir)
    world_only = find_hidden(game, scopes=("Global", "Object"))
    by_node = {line.node: line for line in world_only.lines}
    # "negated" is gated by one Global and one Tag check; only the Global counts
    assert by_node["negated"].gate_count == 1
    assert all(
        condition.scope in ("Global", "Object")
        for line in world_only.lines
        for condition in line.conditions
    )
    assert scope_counts(world_only) == {"Global": 4, "Object": 1}
    assert scope_counts(find_hidden(game))["Tag"] == 1


def test_analyze_dialog_skips_unresolved_handles():
    dialog = parse_dialog(parse_lsx(DIALOG_LSX))
    assert analyze_dialog(dialog, resolve=lambda handle: None) == []


def test_flag_names_index(secrets_dir):
    game = Game(data_dir=secrets_dir)
    assert game.flag_names[MET_FLAG] == "COMP_MetInTavern"
    assert HOSTILE_FLAG not in game.flag_names


def test_find_hidden_end_to_end(secrets_dir):
    game = Game(data_dir=secrets_dir)
    report = find_hidden(game, min_gates=0)
    assert report.ok and report.dialogs_scanned == 1
    assert [(line.node, line.gate_count) for line in report.lines] == [
        ("deep", 3), ("negated", 2), ("gated", 1), ("cut", 0),
    ]
    deep = report.lines[0]
    assert deep.dialog == DIALOG_PATH and deep.category == "Companion"
    assert deep.text == "I dreamt of you."  # newlines collapsed for display
    assert deep.conditions[1].name == "COMP_TrustsYou"

    record = to_records(report)[0]
    assert record["gate_count"] == 3 and record["constructor"] == "TagQuestion"
    assert record["handle"] == "hbbbb0000-0000-0000-0000-0000000000t3"


def test_find_hidden_filters(secrets_dir):
    game = Game(data_dir=secrets_dir)
    assert [line.node for line in find_hidden(game, min_gates=2).lines] == [
        "deep", "negated",
    ]
    assert [line.node for line in find_hidden(
        game, min_gates=0, kinds=("orphan",)
    ).lines] == ["cut"]
    assert find_hidden(game, match="nothing-matches").lines == []
    assert find_hidden(game, category="Camp").dialogs_matched == 0
    assert find_hidden(game, category="companion").dialogs_matched == 1
    with pytest.raises(ValueError, match="unknown kind"):
        find_hidden(game, kinds=("mystery",))


def test_analyze_dialog_without_a_path_names_the_source():
    dialog = parse_dialog(parse_lsx(DIALOG_LSX), source="COMP_Secret.lsx")
    assert analyze_dialog(dialog)[0].dialog == "COMP_Secret.lsx"
    dialog.source = None
    assert analyze_dialog(dialog)[0].dialog == dialog.uuid


def test_unparseable_dialogs_are_reported_not_swallowed(tmp_path):
    """A file under DialogsBinary that is not a dialog resource must
    surface as a failure; a silent skip would understate the sweep."""
    writer = PakWriter()
    writer.add(DIALOG_PATH, write_lsf(parse_lsx(DIALOG_LSX), version=6))
    writer.add(
        "Mods/Shared/Story/DialogsBinary/Broken.lsx",
        b'<save><region id="Other"><node id="Other"/></region></save>',
    )
    writer.add("Localization/English/english.loca", write_loca(LOCA))
    game = Game(data_dir=writer.write(tmp_path / "Broken.pak").parent)

    seen = []
    report = find_hidden(game, min_gates=0, progress=seen.append)
    assert report.dialogs_scanned == 1 and not report.ok
    assert report.failures[0].file.endswith("Broken.lsx")
    assert seen == ["scanning dialogs: 1/2", "scanning dialogs: 2/2"]
    assert "1 dialog(s) failed to parse" in format_report(report)


def test_long_lines_are_truncated_to_the_console_width(secrets_dir):
    game = Game(data_dir=secrets_dir)
    report = find_hidden(game, min_gates=1)
    report.lines[0] = replace(report.lines[0], text="word " * 40)
    body = format_report(report, width=30)
    assert '"word word word word word wo..."' in body


def test_report_formatting(secrets_dir):
    game = Game(data_dir=secrets_dir)
    text = format_report(find_hidden(game, min_gates=0))
    assert text.isascii()
    assert "scanned 1 dialog(s); 3 node(s) carry conditions; found 4 line(s)" in text
    assert f"{DIALOG_PATH}  [Companion]" in text
    assert 'gated x3  speaker 0  "I dreamt of you."' in text
    assert "requires Global:COMP_MetInTavern, Object:COMP_TrustsYou" in text
    assert 'orphan    speaker 0  "The tadpole sings to me."' in text

    assert "... and 3 more" in format_report(find_hidden(game, min_gates=0), limit=1)
    assert "nothing matched" in format_report(find_hidden(game, min_gates=99))


def test_secrets_cli(secrets_dir, capsys, tmp_path):
    from bg3forge.cli.main import main

    out_json = tmp_path / "secrets.json"
    assert main([
        "--data-dir", str(secrets_dir), "secrets",
        "--min-gates", "0", "--json", str(out_json), "--no-progress",
    ]) == 0
    out = capsys.readouterr().out
    assert "Hidden dialog content" in out and "gated x3" in out

    records = json.loads(out_json.read_text())
    assert [record["node"] for record in records] == [
        "deep", "negated", "gated", "cut",
    ]
    assert records[0]["conditions"] == [
        "Global:COMP_MetInTavern",
        "Object:COMP_TrustsYou",
        "Global:GLO_Night",
    ]

    # nothing found is a non-zero exit, like `lookup`
    assert main([
        "--data-dir", str(secrets_dir), "secrets", "--min-gates", "99", "--no-progress",
    ]) == 1


def test_secrets_cli_kind_and_match(secrets_dir, capsys):
    from bg3forge.cli.main import main

    assert main([
        "--data-dir", str(secrets_dir), "secrets", "COMP_Secret",
        "--kind", "orphan", "--min-gates", "0", "--no-progress",
    ]) == 0
    assert "The tadpole sings to me." in capsys.readouterr().out

    assert main([
        "--data-dir", str(secrets_dir), "secrets", "no-such-dialog", "--no-progress",
    ]) == 1
