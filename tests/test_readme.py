"""Every Python snippet in the README must execute as written.

The blocks run statement-by-statement against the synthetic fixture
game, so a renamed method, wrong signature, or missing symbol fails the
suite (``AttributeError``/``TypeError``/``ImportError`` propagate).
The namespace carries over from block to block — the README is a
progressive narrative, and a block that says ``game.spells[...]``
relies on the ``game = Game()`` from an earlier block.

Only *data-dependent* misses are tolerated — the README references
retail names (``WPN_Longsword`` works here, ``Shout_Rage`` doesn't),
which surface as ``KeyError``/``IconError``.  ``NameError`` is NOT
blanket-tolerated (that once silently skipped 24 of 75 statements,
including whole blocks): it is accepted only for the documented
placeholders below, or for names whose defining statement was itself
skipped for data reasons.  Any other ``NameError`` means the README
references something that never existed — a doc bug — and fails.
Syntax is always strict: every block must at least compile.
"""

import ast
import contextlib
import io
import re
from pathlib import Path

import pytest

import bg3forge
from bg3forge import Game
from bg3forge.assets.icons import IconError

README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.fixture
def game(data_dir):
    return Game(data_dir=data_dir)

#: Exceptions that mean "the fixture install lacks this retail data",
#: not "the README shows an API that doesn't exist".
DATA_DEPENDENT = (KeyError, IconError, FileNotFoundError)

#: Names the README deliberately leaves illustrative (never assigned).
PLACEHOLDERS = {"path", "table_uuid"}

#: Ceiling on tolerated skips.  Raise it consciously when the README
#: legitimately gains new retail-only examples — a silent jump here is
#: exactly the erosion this guard exists to catch.
MAX_SKIPPED = 18

_MISSING_NAME_RE = re.compile(r"name '(\w+)' is not defined")


def _python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", README.read_text("utf-8"), re.DOTALL)


def _assigned_names(node: ast.AST) -> set[str]:
    """Names a statement would have bound had it not been skipped."""
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
    }


def test_readme_python_blocks_execute(game, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # mod.build(...) etc. write here, not the repo
    # README snippets call Game() bare; route them to the fixture install.
    monkeypatch.setattr(bg3forge, "Game", lambda *args, **kwargs: game)

    blocks = _python_blocks()
    assert len(blocks) >= 5, "README python blocks went missing"

    namespace: dict = {}
    missing: set[str] = set(PLACEHOLDERS)
    skipped: list[str] = []
    total = 0
    for index, block in enumerate(blocks):
        tree = ast.parse(block)  # syntax errors fail regardless of data
        for node in tree.body:
            total += 1
            where = f"README block {index} line {node.lineno}"
            code = compile(ast.Module(body=[node], type_ignores=[]), f"<{where}>", "exec")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(code, namespace)
            except DATA_DEPENDENT as exc:
                missing |= _assigned_names(node)
                skipped.append(f"{where}: {type(exc).__name__}: {exc}")
            except NameError as exc:
                match = _MISSING_NAME_RE.search(str(exc))
                assert match and match.group(1) in missing, (
                    f"{where}: {exc} — not a documented placeholder or a "
                    "data-dependent cascade; the README references a name "
                    "that never existed"
                )
                missing |= _assigned_names(node)
                skipped.append(f"{where}: {exc}")

    detail = "\n  ".join(skipped)
    assert len(skipped) <= MAX_SKIPPED, (
        f"{len(skipped)} README statements skipped (ceiling {MAX_SKIPPED}) — "
        f"coverage is eroding:\n  {detail}"
    )
