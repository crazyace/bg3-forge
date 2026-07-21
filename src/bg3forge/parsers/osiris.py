"""Metadata reader for BG3's compiled Osiris ``story.div.osi`` files.

The byte layout follows LSLib's ``LS/Story/StoryReader`` and related
serializers.  This first version deliberately retains metadata only:
header/version, types, function signatures, database signatures and
fact counts, goals, and rule counts.  It still walks every serialized
object so truncated or structurally invalid stories fail validation.

BG3 Patch 8+ stories use Osiris versions 1.14 and 1.15.  Older formats
have different value and type-id encodings and are rejected rather than
being guessed at.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class OsirisError(ValueError):
    """A compiled story is truncated, corrupt, or unsupported."""


class FunctionType(IntEnum):
    EVENT = 1
    QUERY = 2
    CALL = 3
    DATABASE = 4
    PROC = 5
    SYS_QUERY = 6
    SYS_CALL = 7
    USER_QUERY = 8


@dataclass(frozen=True)
class StoryHeader:
    version_string: str
    major: int
    minor: int
    big_endian: bool
    debug_flags: int

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}"


@dataclass(frozen=True)
class OsirisType:
    index: int
    name: str
    alias: int


@dataclass(frozen=True)
class OsirisFunction:
    name: str
    kind: FunctionType
    parameter_types: tuple[int, ...]
    out_parameter_mask: bytes
    line: int
    node_index: int

    @property
    def arity(self) -> int:
        return len(self.parameter_types)


@dataclass(frozen=True)
class OsirisDatabase:
    index: int
    name: str | None
    parameter_types: tuple[int, ...]
    fact_count: int

    @property
    def arity(self) -> int:
        return len(self.parameter_types)


@dataclass(frozen=True)
class OsirisGoal:
    index: int
    name: str
    parent_indices: tuple[int, ...]
    subgoal_indices: tuple[int, ...]
    flags: int
    init_call_count: int
    exit_call_count: int
    rule_count: int = 0


@dataclass(frozen=True)
class CompiledStory:
    source: str | None
    header: StoryHeader
    types: tuple[OsirisType, ...]
    functions: tuple[OsirisFunction, ...]
    databases: tuple[OsirisDatabase, ...]
    goals: tuple[OsirisGoal, ...]
    enum_count: int
    div_object_count: int
    node_count: int
    adapter_count: int
    rule_count: int
    global_action_count: int

    def type_name(self, type_id: int) -> str:
        for item in self.types:
            if item.index == type_id:
                return item.name
        return f"TYPE{type_id}"

    def signature(self, parameter_types: tuple[int, ...]) -> tuple[str, ...]:
        return tuple(self.type_name(type_id) for type_id in parameter_types)

    @property
    def goal_names(self) -> set[str]:
        return {goal.name for goal in self.goals}


_MAX_COUNT = 10_000_000
_MAX_STRING = 16 * 1024 * 1024
_MIN_VERSION = 0x010E
_MAX_VERSION = 0x010F


class _Reader:
    def __init__(self, data: bytes, source: str | None):
        self.data = memoryview(data)
        self.offset = 0
        self.source = source or "<story.div.osi>"
        self.scramble = 0
        self.version = 0
        self.short_type_ids = True
        self.aliases: dict[int, int] = {}
        self.enum_types: set[int] = set()

    def fail(self, message: str) -> OsirisError:
        return OsirisError(f"{self.source}: byte 0x{self.offset:x}: {message}")

    def read(self, size: int) -> bytes:
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise self.fail(f"truncated input (need {size} bytes)")
        value = self.data[self.offset:end].tobytes()
        self.offset = end
        return value

    def skip(self, size: int) -> None:
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise self.fail(f"truncated input (need {size} bytes)")
        self.offset = end

    def unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        end = self.offset + size
        if end > len(self.data):
            raise self.fail(f"truncated input (need {size} bytes)")
        value = struct.unpack_from(fmt, self.data, self.offset)[0]
        self.offset = end
        return value

    def u8(self) -> int:
        return self.unpack("<B")

    def i8(self) -> int:
        return self.unpack("<b")

    def u16(self) -> int:
        return self.unpack("<H")

    def u32(self) -> int:
        return self.unpack("<I")

    def i32(self) -> int:
        return self.unpack("<i")

    def boolean(self) -> bool:
        value = self.u8()
        if value not in (0, 1):
            raise self.fail(f"invalid boolean {value}")
        return bool(value)

    def string(self) -> str:
        value = bytearray()
        while True:
            if len(value) >= _MAX_STRING:
                raise self.fail("string exceeds safety limit")
            byte = self.u8() ^ self.scramble
            if byte == 0:
                break
            value.append(byte)
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise self.fail(f"invalid UTF-8 string: {exc}") from exc

    def count(self, label: str, *, maximum: int = _MAX_COUNT) -> int:
        value = self.u32()
        if value > maximum:
            raise self.fail(f"implausible {label} count {value:,}")
        return value

    def type_id(self) -> int:
        return self.u16() if self.short_type_ids else self.u32()

    def parameters(self) -> tuple[int, ...]:
        return tuple(self.type_id() for _ in range(self.u8()))

    def refs(self, label: str) -> tuple[int, ...]:
        return tuple(self.u32() for _ in range(self.count(label)))

    def builtin_type(self, type_id: int) -> int:
        seen: set[int] = set()
        while type_id in self.aliases and self.aliases[type_id] != 0:
            if type_id in seen:
                raise self.fail(f"type alias cycle at {type_id}")
            seen.add(type_id)
            type_id = self.aliases[type_id]
        return type_id

    def value(self) -> None:
        # Compact Value layout introduced in Osiris 1.14.
        self.i8()  # logical index
        flags = self.u8()
        if not flags & 0x08:  # IsValid
            return

        discriminator = self.u8()
        if discriminator == ord("1"):
            self.type_id()
            self.skip(4)  # int32 reference/value
            return
        if discriminator == ord("e"):
            type_id = self.u16()
            if type_id not in self.enum_types:
                raise self.fail(f"enum value uses non-enum type {type_id}")
            self.string()
            return
        if discriminator != ord("0"):
            raise self.fail(f"unrecognized value discriminator 0x{discriminator:02x}")

        type_id = self.type_id()
        builtin = self.builtin_type(type_id)
        if builtin == 0:
            return
        if builtin == 1:
            self.skip(4)
        elif builtin == 2:
            self.skip(8)
        elif builtin == 3:
            self.skip(4)
        elif builtin in (4, 5):
            if self.u8() > 0:
                self.string()
        else:
            # Custom non-alias types serialize their textual value directly.
            self.string()

    def call(self) -> None:
        name = self.string()
        if name:
            if self.u8() > 0:
                for _ in range(self.u8()):
                    self.value()
            self.boolean()  # negate
        self.i32()  # goal id or debug hook

    def calls(self, label: str) -> int:
        count = self.count(label)
        for _ in range(count):
            self.call()
        return count

    def tuple(self) -> None:
        for _ in range(self.u8()):
            self.value()


def parse_osiris(data: bytes, source: str | None = None) -> CompiledStory:
    """Parse metadata from one compiled ``story.div.osi`` blob."""
    reader = _Reader(data, source)
    header = _read_header(reader)
    reader.version = (header.major << 8) | header.minor
    if not _MIN_VERSION <= reader.version <= _MAX_VERSION:
        raise reader.fail(
            f"unsupported Osiris version {header.version}; expected 1.14 or 1.15"
        )
    if header.big_endian:
        raise reader.fail("big-endian Osiris stories are unsupported")
    reader.scramble = 0xAD

    types = _read_types(reader)
    enum_count = _read_enums(reader)
    div_object_count = _read_div_objects(reader)
    functions = _read_functions(reader)
    node_count, rule_nodes, database_owners, rule_goals = _read_nodes(reader)
    adapter_count = _read_adapters(reader)
    databases = _read_databases(reader, database_owners)
    goals = _read_goals(reader, rule_goals)
    global_action_count = reader.calls("global action")

    if reader.offset != len(reader.data):
        raise reader.fail(f"{len(reader.data) - reader.offset} trailing bytes")

    return CompiledStory(
        source=source,
        header=header,
        types=tuple(sorted(types, key=lambda item: item.index)),
        functions=tuple(functions),
        databases=tuple(databases),
        goals=tuple(goals),
        enum_count=enum_count,
        div_object_count=div_object_count,
        node_count=node_count,
        adapter_count=adapter_count,
        rule_count=len(rule_nodes),
        global_action_count=global_action_count,
    )


def _read_header(reader: _Reader) -> StoryHeader:
    marker = reader.u8()
    if marker != 0:
        raise reader.fail(f"invalid header marker {marker}")
    version_string = reader.string()
    major = reader.u8()
    minor = reader.u8()
    big_endian = reader.boolean()
    reader.u8()  # unused
    version = (major << 8) | minor
    if version >= 0x0102:
        reader.skip(0x80)
    debug_flags = reader.u32() if version >= 0x0103 else 0
    return StoryHeader(version_string, major, minor, big_endian, debug_flags)


def _read_types(reader: _Reader) -> list[OsirisType]:
    by_index: dict[int, OsirisType] = {}
    for _ in range(reader.count("type", maximum=256)):
        name = reader.string()
        index = reader.u8()
        alias = reader.u8()
        by_index[index] = OsirisType(index, name, alias)
        reader.aliases[index] = alias
    # StoryReader installs these builtins after reading the serialized map.
    by_index.update(
        {
            0: OsirisType(0, "UNKNOWN", 0),
            1: OsirisType(1, "INTEGER", 0),
            2: OsirisType(2, "INTEGER64", 0),
            3: OsirisType(3, "REAL", 0),
            4: OsirisType(4, "STRING", 0),
        }
    )
    if 5 not in by_index:
        by_index[5] = OsirisType(5, "GUIDSTRING", 0)
    return list(by_index.values())


def _read_enums(reader: _Reader) -> int:
    count = reader.count("enum", maximum=65_536)
    for _ in range(count):
        underlying_type = reader.u16()
        reader.enum_types.add(underlying_type)
        for _ in range(reader.count("enum element")):
            reader.string()
            reader.skip(8)
    return count


def _read_div_objects(reader: _Reader) -> int:
    count = reader.count("DIV object")
    for _ in range(count):
        reader.string()
        reader.skip(1 + 4 * 4)
    return count


def _read_functions(reader: _Reader) -> list[OsirisFunction]:
    items = []
    for _ in range(reader.count("function")):
        line = reader.u32()
        reader.skip(8)  # condition/action reference counts
        node_index = reader.u32()
        kind_value = reader.u8()
        try:
            kind = FunctionType(kind_value)
        except ValueError as exc:
            raise reader.fail(f"unknown function type {kind_value}") from exc
        reader.skip(16)  # Meta1..Meta4
        name = reader.string()
        mask = reader.read(reader.count("out-parameter mask", maximum=1_000_000))
        parameters = reader.parameters()
        items.append(OsirisFunction(name, kind, parameters, mask, line, node_index))
    return items


def _entry(reader: _Reader) -> tuple[int, int]:
    node_index = reader.u32()
    reader.u32()  # entry point
    goal_index = reader.u32()
    return node_index, goal_index


def _node_base(reader: _Reader, owners: dict[int, tuple[str, int]]) -> None:
    database_index = reader.u32()
    name = reader.string()
    arity = reader.u8() if name else 0
    if database_index and name:
        previous = owners.get(database_index)
        owner = (name, arity)
        if previous is not None and previous != owner:
            raise reader.fail(f"database {database_index} has multiple named owners")
        owners[database_index] = owner


def _tree_base(
    reader: _Reader,
    owners: dict[int, tuple[str, int]],
    derived: list[tuple[int, int]],
) -> None:
    _node_base(reader, owners)
    derived.append(_entry(reader))


def _rel_base(
    reader: _Reader,
    owners: dict[int, tuple[str, int]],
    derived: list[tuple[int, int]],
) -> None:
    _tree_base(reader, owners, derived)
    reader.skip(12)  # parent, adapter, relation database node refs
    _entry(reader)
    reader.u8()  # database indirection


def _read_nodes(
    reader: _Reader,
) -> tuple[int, set[int], dict[int, tuple[str, int]], dict[int, int]]:
    count = reader.count("node")
    node_types: dict[int, int] = {}
    owners: dict[int, tuple[str, int]] = {}
    derived_entries: list[tuple[int, int]] = []
    for _ in range(count):
        node_type = reader.u8()
        node_index = reader.u32()
        if node_index in node_types:
            raise reader.fail(f"duplicate node index {node_index}")
        node_types[node_index] = node_type

        if node_type in (1, 2):  # DatabaseNode, ProcNode: DataNode
            _node_base(reader, owners)
            for _ in range(reader.count("node reference")):
                derived_entries.append(_entry(reader))
        elif node_type in (3, 8, 9):  # query nodes: Node
            _node_base(reader, owners)
        elif node_type in (4, 5):  # And/NotAnd: JoinNode
            _tree_base(reader, owners, derived_entries)
            reader.skip(16)  # left/right parent + adapter refs
            for _ in range(2):
                reader.u32()  # database node ref
                _entry(reader)
                reader.u8()
        elif node_type == 6:  # RelOpNode
            _rel_base(reader, owners, derived_entries)
            reader.skip(2)  # left/right value indices
            reader.value()
            reader.value()
            reader.i32()
        elif node_type == 7:  # RuleNode
            _rel_base(reader, owners, derived_entries)
            reader.calls("rule call")
            for _ in range(reader.u8()):
                reader.value()
            reader.u32()  # source line
            reader.boolean()  # is query
        else:
            raise reader.fail(f"unknown node type {node_type}")

    rule_nodes = {index for index, node_type in node_types.items() if node_type == 7}
    rule_goals: dict[int, int] = {}
    for node_index, goal_index in derived_entries:
        if node_index in rule_nodes and goal_index:
            previous = rule_goals.get(node_index)
            if previous is not None and previous != goal_index:
                raise reader.fail(f"rule node {node_index} belongs to multiple goals")
            rule_goals[node_index] = goal_index
    return count, rule_nodes, owners, rule_goals


def _read_adapters(reader: _Reader) -> int:
    count = reader.count("adapter")
    for _ in range(count):
        reader.u32()  # index
        reader.tuple()
        reader.skip(reader.u8())  # logical indices (sbytes)
        reader.skip(reader.u8() * 2)  # logical -> physical pairs
    return count


def _read_databases(
    reader: _Reader, owners: dict[int, tuple[str, int]]
) -> list[OsirisDatabase]:
    items = []
    for _ in range(reader.count("database")):
        index = reader.u32()
        parameters = reader.parameters()
        fact_count = reader.count("database fact")
        for _ in range(fact_count):
            for _ in range(reader.u8()):
                reader.value()
        owner = owners.get(index)
        items.append(
            OsirisDatabase(
                index=index,
                name=owner[0] if owner else None,
                parameter_types=parameters,
                fact_count=fact_count,
            )
        )
    return items


def _read_goals(reader: _Reader, rule_goals: dict[int, int]) -> list[OsirisGoal]:
    rule_counts: dict[int, int] = {}
    for goal_index in rule_goals.values():
        rule_counts[goal_index] = rule_counts.get(goal_index, 0) + 1

    items = []
    for _ in range(reader.count("goal")):
        index = reader.u32()
        name = reader.string()
        reader.u8()  # subgoal combination
        parents = reader.refs("parent goal")
        subgoals = reader.refs("subgoal")
        flags = reader.u8()
        init_count = reader.calls("goal init call")
        exit_count = reader.calls("goal exit call")
        items.append(
            OsirisGoal(
                index=index,
                name=name,
                parent_indices=parents,
                subgoal_indices=subgoals,
                flags=flags,
                init_call_count=init_count,
                exit_call_count=exit_count,
                rule_count=rule_counts.get(index, 0),
            )
        )
    return items


__all__ = [
    "CompiledStory",
    "FunctionType",
    "OsirisDatabase",
    "OsirisError",
    "OsirisFunction",
    "OsirisGoal",
    "OsirisType",
    "StoryHeader",
    "parse_osiris",
]
