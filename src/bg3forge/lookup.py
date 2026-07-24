"""Resolve a name / UUID / handle to everything BG3 Forge knows about it.

The lookup modders do constantly: "what *is* this name, what's its UUID,
what's its handle, what grants it?"  ``lookup`` takes a stats name, a
template/tag UUID, or a localization handle and returns a resolved
summary with the graph's cross-references; a partial name returns
ranked suggestions instead.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field

from .game import Game

#: (label, Game attribute) for the typed collections a name may live in.
_KINDS = (
    ("item", "items"),
    ("spell", "spells"),
    ("passive", "passives"),
    ("status", "statuses"),
    ("character", "characters"),
)

_MAX_SUGGESTIONS = 25
_MAX_LIST = 12


@dataclass
class Section:
    """One resolved entity, rendered as a titled block of label/value rows."""
    title: str
    rows: list[tuple[str, str]] = field(default_factory=list)

    def add(self, label: str, value: str | None) -> None:
        if value:
            self.rows.append((label, value))


@dataclass
class LookupResult:
    query: str
    sections: list[Section] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.sections)


def _looks_like_uuid(value: str) -> bool:
    try:
        _uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _names(objects, limit: int = _MAX_LIST) -> str:
    names = [getattr(o, "name", str(o)) for o in objects]
    if not names:
        return ""
    shown = names[:limit]
    suffix = f", … (+{len(names) - limit} more)" if len(names) > limit else ""
    return ", ".join(shown) + suffix


def lookup(game: Game, query: str) -> LookupResult:
    """Resolve ``query`` against the game graph."""
    result = LookupResult(query=query)

    # 1. A localization handle → its text.
    if query.startswith("h") and query in game.localization:
        section = Section("Localization handle")
        section.add("handle", query)
        section.add("text", game.localization.resolve(query))
        result.sections.append(section)

    # 2. A UUID → the template and/or tag it identifies.
    if _looks_like_uuid(query):
        template = game.templates.get(query)
        if template is not None:
            result.sections.append(_template_section(game, template))
        tag = game.tags.get(query)
        if tag is not None:
            result.sections.append(_tag_section(tag))

    # 3. An exact stats/model name in any typed collection.
    for label, attr in _KINDS:
        obj = getattr(game, attr).get(query)
        if obj is not None:
            result.sections.append(_object_section(label, obj))

    # 4. A tag by engine name (e.g. "LONGSWORD").
    tag = game.tags.get(query)
    if tag is not None and not _looks_like_uuid(query):
        result.sections.append(_tag_section(tag))

    if result.sections:
        return result

    # 5. Nothing exact — offer substring suggestions across collections.
    for label, attr in _KINDS:
        for obj in getattr(game, attr).find(query):
            display = f" — {obj.display_name}" if obj.display_name else ""
            result.suggestions.append(f"{label:9} {obj.name}{display}")
            if len(result.suggestions) >= _MAX_SUGGESTIONS:
                return result
    return result


def _object_section(kind: str, obj) -> Section:
    section = Section(f"{kind}: {obj.name}")
    section.add("type", obj.stats_type)
    section.add("display name", obj.display_name)
    if obj.description:
        section.add("description", _truncate(obj.description))
    section.add("icon", getattr(obj, "icon", None))
    section.add("UUID (RootTemplate)", getattr(obj, "map_key", None))
    section.add("DisplayName handle", obj.get("DisplayName"))

    if kind == "item":
        section.add("rarity", obj.rarity)
        section.add("slot", obj.slot)
        section.add("grants passives", _names(obj.passives))
        section.add("applies statuses", _names(obj.statuses))
        section.add("unlocks spells", _names(obj.spells))
        section.add("tags", ", ".join(t.name for t in obj.tags) or "")
        section.add("owner templates", _names(obj.owner_templates))
    elif kind == "spell":
        section.add("spell type", obj.spell_type)
        section.add("level", str(obj.level) if obj.level is not None else "")
        section.add("school", obj.school)
        section.add("damage", obj.damage)
        section.add("unlocked by items", _names(obj.items))
        section.add("granted by progressions", _names(obj.progressions))
    elif kind == "passive":
        section.add("granted by items", _names(obj.items))
        section.add("on characters", _names(obj.characters))
        section.add("granted by progressions", _names(obj.progressions))
    elif kind == "status":
        section.add("status type", obj.status_type)
        section.add("applied by items", _names(obj.items))
    elif kind == "character":
        section.add("level", str(obj.level) if obj.level is not None else "")
        section.add("archetype", obj.archetype)
        section.add("passives", ", ".join(obj.passive_names[:_MAX_LIST]))
    return section


def _template_section(game: Game, template) -> Section:
    section = Section(f"template: {template.name or template.map_key}")
    section.add("UUID (MapKey)", template.map_key)
    section.add("stats", template.stats_name)
    section.add("parent template", template.parent_id)
    section.add("icon", template.icon)
    section.add(
        "display name",
        game.localization.resolve(template.display_name_handle),
    )
    section.add("DisplayName handle", template.display_name_handle)
    return section


def _tag_section(tag) -> Section:
    section = Section(f"tag: {tag.name or tag.uuid}")
    section.add("UUID", tag.uuid)
    section.add("name", tag.name)
    section.add("display name", tag.display_name)
    section.add("categories", ", ".join(tag.categories))
    return section


def _truncate(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_report(result: LookupResult) -> str:
    if not result.sections and not result.suggestions:
        return f"No match for {result.query!r}."
    lines: list[str] = []
    for section in result.sections:
        lines.append(section.title)
        lines.append("-" * len(section.title))
        width = max((len(label) for label, _ in section.rows), default=0)
        for label, value in section.rows:
            lines.append(f"  {label:<{width}}  {value}")
        lines.append("")
    if result.suggestions:
        lines.append(f"No exact match for {result.query!r}. Did you mean:")
        lines.extend(f"  {s}" for s in result.suggestions)
    return "\n".join(lines).rstrip()
