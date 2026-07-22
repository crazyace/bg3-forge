"""Tests for the validation sweep and benchmark suite."""

import pytest

from bg3forge import Game
from bg3forge.benchmark import format_report as format_benchmark, run_benchmark
from bg3forge.cli.main import main
from bg3forge.pak import PakWriter
from bg3forge.validate import format_report as format_validation, validate_data


# -- validate ----------------------------------------------------------------

def test_validate_clean_fixture(data_dir):
    report = validate_data(data_dir)
    assert report.ok
    assert report.counts["paks"] == 1
    assert report.counts["stats_files"] == 6
    assert report.counts["stats_entries"] == 8
    assert report.counts["stats_globals"] == 2
    assert report.counts["stats_resolved"] == 8  # inheritance checked cross-file
    assert report.counts["treasure_files"] == 1
    assert report.counts["treasure_tables"] == 1
    assert report.counts["loca_files"] == 1
    assert report.counts["loca_handles"] == 17
    assert report.counts["lsx_resources"] == 11  # templates, placed items, atlas, tags, registry, journal
    assert report.counts["lsf_resources"] == 2   # dialog + timeline
    assert report.counts["dialogs"] == 2   # binary + editor .lsj
    assert report.counts["dialog_nodes"] == 4
    assert report.counts["lsj_resources"] == 1
    assert report.counts["timelines"] == 1
    assert report.counts["quests"] == 1
    assert report.counts["quest_steps"] == 2
    assert report.counts["quest_markers"] == 1
    assert report.counts["objectives"] == 2
    assert report.counts["quest_categories"] == 1
    assert report.counts["goals"] == 1
    assert report.counts["goal_quest_refs"] == 2
    assert report.counts["compiled_stories"] == 1
    assert report.counts["story_functions"] == 2
    assert report.counts["story_databases"] == 1
    assert report.counts["story_goals"] == 1
    assert report.counts["story_rules"] == 1
    assert report.counts["source_goals_compiled"] == 1
    assert report.counts["source_goals_missing"] == 0
    assert report.counts["equipment_files"] == 1
    assert report.counts["equipment_sets"] == 1
    assert report.counts["root_templates"] == 3
    assert report.counts["atlases"] == 1
    text = format_validation(report)
    assert "OK: every recognized file parsed cleanly." in text


def test_validate_counts_lsf(tmp_path, data_dir):
    from bg3forge.parsers import parse_lsx, write_lsf
    from conftest import ROOTTEMPLATE_LSX

    writer = PakWriter()
    writer.add(
        "Public/Extra/RootTemplates/More.lsf",
        write_lsf(parse_lsx(ROOTTEMPLATE_LSX), version=7),
    )
    writer.write(data_dir / "Extra.pak")
    report = validate_data(data_dir)
    assert report.ok
    assert report.counts["lsf_resources"] == 3  # dialog + timeline + added templates
    assert report.counts["root_templates"] == 6


def test_validate_reports_corrupt_files(tmp_path, data_dir):
    writer = PakWriter()
    writer.add("Localization/English/broken.loca", b"LOCA" + b"\x01" * 4)  # truncated
    writer.add("Public/Bad/RootTemplates/broken.lsx", b"<save><region")     # malformed
    writer.add("Public/Bad/Stats/Generated/Data/ok.txt", b'new entry "X"\ntype "Weapon"\n')
    writer.write(data_dir / "Broken.pak")

    report = validate_data(data_dir)
    assert not report.ok
    assert len(report.issues) == 2
    stages = {issue.stage for issue in report.issues}
    assert stages == {"loca", "resource"}
    assert report.counts["stats_files"] == 7  # the good file still counted
    text = format_validation(report)
    assert "2 file(s) failed to parse" in text
    assert "broken.loca" in text


def test_validate_reports_corrupt_compiled_story(data_dir):
    writer = PakWriter()
    writer.add("Mods/Bad/Story/story.div.osi", b"not an Osiris story")
    writer.write(data_dir / "BrokenStory.pak")

    report = validate_data(data_dir)
    assert not report.ok
    issue = next(issue for issue in report.issues if issue.stage == "story")
    assert issue.file == "Mods/Bad/Story/story.div.osi"
    assert "invalid header marker" in issue.error


def test_validate_cross_checks_source_goals(tmp_path):
    from conftest import GOAL_TXT, make_story_osi

    writer = PakWriter()
    writer.add("Mods/Test/Story/RawFiles/Goals/MissingGoal.txt", GOAL_TXT.encode())
    writer.add("Mods/Test/Story/story.div.osi", make_story_osi())
    writer.write(tmp_path / "Story.pak")

    report = validate_data(tmp_path)
    assert not report.ok
    assert report.counts["source_goals_missing"] == 1
    issue = next(issue for issue in report.issues if issue.stage == "story-crosscheck")
    assert "MissingGoal" in issue.error


def test_validate_progress_callback(data_dir):
    messages = []
    report = validate_data(data_dir, progress=messages.append)
    assert report.ok
    assert any("Shared.pak" in m for m in messages)
    assert any("resolving inheritance" in m for m in messages)


def test_validate_no_progress_when_stderr_redirected(data_dir, capsys, monkeypatch):
    """With streams redirected (the `*> validate.txt` case) progress must
    never leak into the captured output — it goes to the console device
    or nowhere."""
    import sys as _sys
    cli_main = _sys.modules["bg3forge.cli.main"]

    console_writes = []

    class FakeConsole:
        def write(self, text):
            console_writes.append(text)
        def flush(self):
            pass
        def close(self):
            pass

    monkeypatch.setattr(cli_main, "_open_console", lambda: FakeConsole())
    assert main(["--data-dir", str(data_dir), "validate"]) == 0
    captured = capsys.readouterr()
    assert "\r" not in captured.err
    assert captured.err == ""
    # the live line went to the console device instead
    assert any("Shared.pak" in text for text in console_writes)


def test_validate_no_progress_headless(data_dir, capsys, monkeypatch):
    """No terminal at all (CI/cron): progress silently disables."""
    import sys as _sys
    cli_main = _sys.modules["bg3forge.cli.main"]

    def no_console():
        raise OSError("no controlling terminal")

    monkeypatch.setattr(cli_main, "_open_console", no_console)
    assert main(["--data-dir", str(data_dir), "validate"]) == 0
    assert capsys.readouterr().err == ""


def test_validate_no_progress_flag(data_dir, capsys, monkeypatch):
    import sys as _sys
    cli_main = _sys.modules["bg3forge.cli.main"]

    def fail_if_called():
        raise AssertionError("console should not be opened with --no-progress")

    monkeypatch.setattr(cli_main, "_open_console", fail_if_called)
    assert main(["--data-dir", str(data_dir), "validate", "--no-progress"]) == 0


def test_validate_cli(data_dir, capsys):
    assert main(["--data-dir", str(data_dir), "validate"]) == 0
    out = capsys.readouterr().out
    assert "stats entries" in out
    assert "OK" in out


def test_validate_cli_exit_code_on_issues(data_dir, capsys):
    writer = PakWriter()
    writer.add("Localization/English/broken.loca", b"XXXX")
    writer.write(data_dir / "Broken.pak")
    assert main(["--data-dir", str(data_dir), "validate"]) == 1
    assert "failed to parse" in capsys.readouterr().out


# -- benchmark ---------------------------------------------------------------

def test_run_benchmark(data_dir, tmp_path):
    report = run_benchmark(Game(data_dir=data_dir), export_dir=tmp_path / "export")
    labels = [label for label, _ in report.stages]
    assert labels == [
        "Read pak indexes",
        "Parse stats",
        "Parse localization",
        "Parse root templates",
        "Parse tags",
        "Parse atlases",
        "Index dialogs",
        "Index timelines",
        "Parse quests",
        "Index goals",
        "Parse compiled stories",
        "Build models",
        "Resolve relationships",
        "Export JSON",
    ]
    assert all(seconds >= 0 for _, seconds in report.stages)
    assert report.counts["items"] == 3
    assert report.counts["spells"] == 1
    assert report.counts["pak entries"] == 25
    assert report.counts["tags"] == 2
    assert report.counts["dialogs indexed"] == 1
    assert report.counts["timelines indexed"] == 1
    assert report.counts["quests"] == 1
    assert report.counts["objectives"] == 2
    assert report.counts["quest categories"] == 1
    assert report.counts["goals indexed"] == 1
    assert report.counts["compiled stories"] == 1
    assert report.counts["story goals"] == 1
    assert report.counts["story databases"] == 1
    assert report.counts["story rules"] == 1
    assert report.counts["characters"] == 2
    assert report.counts["equipment sets"] == 1
    assert (tmp_path / "export" / "items.json").exists()
    assert report.environment["Language"] == "English"

    text = format_benchmark(report)
    assert "Environment" in text and "Results" in text
    assert "Read pak indexes" in text


def test_benchmark_cli(data_dir, capsys):
    assert main(["--data-dir", str(data_dir), "benchmark"]) == 0
    out = capsys.readouterr().out
    assert "Resolve relationships" in out
    assert "Peak RSS" in out or "unavailable" in out
