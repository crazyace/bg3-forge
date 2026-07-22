"""Survey retail item/template wiring to verify authoring assumptions.

Run on a machine with the game installed::

    python scripts/wiring_survey.py

Sweeps every RootTemplate in the install and prints a compact census of
the structures ``bg3forge.authoring`` writes, so its assumptions are
checked against the whole corpus rather than single examples (the
``OnUseDescription``-is-the-blurb mistake was invisible until a second
example falsified it).  Rerun after a game patch to catch retail drift.

Checks:

- ActionType census: every ``OnUsePeaceActions`` action type with counts
  and the attribute-name -> attribute-type sets seen (flags any attribute
  that appears with conflicting LSF types)
- OnUseDescription: is it always a short use-verb ("Drink")?
- Scroll actions (12): is ``ClassId`` really one shared constant?
- Consume actions (7): ``StatusDuration`` value distribution, and whether
  every ``StatsId`` resolves to a stats entry
- Text-slot presence and unresolved-handle counts
"""

from __future__ import annotations

from collections import Counter, defaultdict

from bg3forge import Game
from bg3forge.game import _is_roottemplate_file
from bg3forge.parsers import parse_resource

_TEXT_SLOTS = ("DisplayName", "Description", "TechnicalDescription", "OnUseDescription")


def main() -> None:
    game = Game()
    templates = 0
    action_counts: Counter[str] = Counter()
    attr_types: dict[tuple[str, str], Counter] = defaultdict(Counter)
    onuse_texts: Counter[str] = Counter()
    scroll_classids: Counter[str] = Counter()
    consume_durations: Counter[str] = Counter()
    consume_missing_status: list[str] = []
    slot_presence: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()

    for _name, data in game._iter_files(_is_roottemplate_file):
        try:
            doc = parse_resource(data)
        except ValueError:
            continue
        for node in doc.find_all("GameObjects"):
            templates += 1
            for slot in _TEXT_SLOTS:
                attr = node.attributes.get(slot)
                if attr is None or not attr.handle:
                    continue
                slot_presence[slot] += 1
                text = game.localization.resolve(attr.handle)
                if not text:
                    unresolved[slot] += 1
                elif slot == "OnUseDescription":
                    onuse_texts[text.strip()] += 1
            for child in node.children:
                if child.id != "OnUsePeaceActions":
                    continue
                for action in child.children:
                    if action.id != "Action":
                        continue
                    action_type = action.get("ActionType") or "?"
                    action_counts[action_type] += 1
                    for attrs in action.children:
                        if attrs.id != "Attributes":
                            continue
                        for attr in attrs.attributes.values():
                            attr_types[(action_type, attr.id)][attr.type] += 1
                        if action_type == "12":
                            scroll_classids[attrs.get("ClassId") or "?"] += 1
                        elif action_type == "7":
                            consume_durations[attrs.get("StatusDuration") or "?"] += 1
                            status = attrs.get("StatsId")
                            if status and status not in game.stats:
                                consume_missing_status.append(status)

    print(f"templates scanned: {templates:,}")
    print("\n== text-slot presence (with unresolved handle counts) ==")
    for slot in _TEXT_SLOTS:
        print(f"  {slot:22} {slot_presence[slot]:6,}   unresolved: {unresolved[slot]}")

    print("\n== OnUseDescription: use-verb theory ==")
    long_texts = [t for t in onuse_texts if len(t) > 25]
    print(f"  distinct texts: {len(onuse_texts)}, longer than 25 chars: {len(long_texts)}")
    for text, count in onuse_texts.most_common(8):
        print(f"    {count:5,}x {text[:60]!r}")
    for text in long_texts[:5]:
        print(f"    LONG: {text[:100]!r}")

    print("\n== OnUsePeaceActions ActionType census ==")
    for action_type, count in sorted(action_counts.items(), key=lambda kv: -kv[1]):
        ids = sorted({a for (t, a) in attr_types if t == action_type})
        print(f"  ActionType {action_type:>3}: {count:6,}x  attrs: {', '.join(ids)}")

    print("\n== attribute-type conflicts (same attr, multiple LSF types) ==")
    conflicts = {k: c for k, c in attr_types.items() if len(c) > 1}
    if conflicts:
        for (action_type, attr_id), counter in sorted(conflicts.items()):
            print(f"  ActionType {action_type} {attr_id}: {dict(counter)}")
    else:
        print("  none — every action attribute has one consistent type")

    print("\n== scroll (ActionType 12) ClassId values ==")
    for class_id, count in scroll_classids.most_common():
        print(f"  {count:6,}x {class_id}")

    print("\n== consume (ActionType 7) StatusDuration values ==")
    for duration, count in consume_durations.most_common():
        print(f"  {count:6,}x {duration}")
    print(f"  StatsId missing from stats: {len(consume_missing_status)}"
          + (f"  e.g. {consume_missing_status[:5]}" if consume_missing_status else ""))


if __name__ == "__main__":
    main()
