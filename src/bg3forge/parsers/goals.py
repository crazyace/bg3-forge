"""Metadata-level parser for Osiris goal scripts.

BG3 ships the *source* of its quest logic under
``Mods/<Mod>/Story/RawFiles/Goals/*.txt`` (a surprise confirmed against
retail — the compiled ``story.div.osi`` is not the only copy).  A goal
file looks like::

    Version 1
    SubGoalCombiner SGC_AND
    INITSECTION
    DB_SomeFact(...);
    KBSECTION
    IF
    SomeEvent(_Char)
    AND
    DB_QuestIsAccepted("SHA_Nightsong")
    THEN
    QuestUpdate(_Char, "SHA_Nightsong", "RefinedLocation");
    EXITSECTION
    ...

This module deliberately does NOT model Osiris semantics.  It extracts
metadata: sections, rule counts, and — most usefully — which quests and
quest steps the goal's logic touches, giving the quest↔logic edges of
the narrative graph.  Full Osiris parsing is a future milestone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SECTION_RE = re.compile(r"^(INITSECTION|KBSECTION|EXITSECTION|ENDSECTION)\s*$")
# Calls whose first quoted argument is a quest id, second (optional) a step.
_QUEST_CALL_RE = re.compile(
    r"\b(?:QuestUpdate|QuestAccept|QuestClose|QuestAdd|QuestUpdateIsUnlocked"
    r"|DB_QuestIsAccepted|DB_QuestDef_\w+)\s*\(([^)]*)\)"
)
_QUOTED_RE = re.compile(r'"([^"]*)"')


def _strip_comments(text: str) -> str:
    """Remove ``//`` line comments and ``/* ... */`` block comments.

    Retail goal sources use both — commented-out rules and facts are
    common in Larian's raw scripts.  Counting them (or harvesting quest
    refs from them) corrupts the metadata, and a trailing ``//`` after a
    statement used to hide the statement itself.  Quoted strings are
    respected; newlines inside block comments are preserved so line
    structure survives.
    """
    if "/" not in text:
        return text
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == '"':
                in_string = False
            i += 1
        elif ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif ch == "/" and text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end == -1 else end  # keep the newline itself
        elif ch == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                i = n  # unterminated block: the rest is comment
            else:
                out.append("\n" * text.count("\n", i, end + 2))
                i = end + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


@dataclass
class Goal:
    name: str                      # file stem, e.g. "Act1_DEN_AdventurersQuest"
    source: str | None = None
    version: str | None = None
    combiner: str | None = None    # e.g. "SGC_AND"
    sections: list[str] = field(default_factory=list)
    init_facts: int = 0            # statements in INITSECTION
    rules: int = 0                 # IF-blocks in KBSECTION
    quest_refs: dict[str, list[str]] = field(default_factory=dict)  # quest -> steps

    @property
    def quest_ids(self) -> list[str]:
        return list(self.quest_refs)


def parse_goal(text: str, source: str | None = None) -> Goal:
    name = source or "<goal>"
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    goal = Goal(name=name, source=source)

    section = None
    for raw_line in _strip_comments(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if match := _SECTION_RE.match(line):
            section = match.group(1)
            goal.sections.append(section)
            continue
        if section is None:
            if line.startswith("Version "):
                goal.version = line.split(None, 1)[1]
            elif line.startswith("SubGoalCombiner "):
                goal.combiner = line.split(None, 1)[1]
            continue
        if section == "INITSECTION" and line.endswith(";"):
            goal.init_facts += 1
        elif section == "KBSECTION" and line == "IF":
            goal.rules += 1
        for call in _QUEST_CALL_RE.finditer(line):
            quoted = _QUOTED_RE.findall(call.group(1))
            if not quoted:
                continue
            quest_id = quoted[0]
            steps = goal.quest_refs.setdefault(quest_id, [])
            if len(quoted) > 1 and quoted[1] and quoted[1] not in steps:
                steps.append(quoted[1])
    return goal
