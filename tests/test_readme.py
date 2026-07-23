"""Every Python snippet in the README must execute as written.

The blocks run statement-by-statement against the synthetic fixture
game, so a renamed method, wrong signature, or missing symbol fails the
suite (`AttributeError`/`TypeError`/`ImportError` propagate).  Only
*data-dependent* misses are tolerated — the README references retail
names (``WPN_Longsword`` works here, ``Shout_Rage`` doesn't) and
deliberately illustrative placeholders (``path``, ``table_uuid``), which
surface as ``KeyError``/``NameError``/``IconError``.  Syntax is always
strict: every block must at least compile.
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
DATA_DEPENDENT = (KeyError, NameError, IconError, FileNotFoundError)


def _python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", README.read_text("utf-8"), re.DOTALL)


def test_readme_python_blocks_execute(game, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # mod.build(...) etc. write here, not the repo
    # README snippets call Game() bare; route them to the fixture install.
    monkeypatch.setattr(bg3forge, "Game", lambda *args, **kwargs: game)

    blocks = _python_blocks()
    assert len(blocks) >= 5, "README python blocks went missing"

    for index, block in enumerate(blocks):
        tree = ast.parse(block)  # syntax errors fail regardless of data
        namespace: dict = {}
        for node in tree.body:
            code = compile(
                ast.Module(body=[node], type_ignores=[]),
                f"<README block {index} line {node.lineno}>",
                "exec",
            )
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(code, namespace)
            except DATA_DEPENDENT:
                continue
