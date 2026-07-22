"""BG3 Forge — a toolkit for Baldur's Gate 3 assets and game data.

Library-first: everything the CLI does is available as importable,
reusable modules.

    from bg3forge import Game

    game = Game()
    for item in game.items:
        print(item.name)
"""

from .authoring import Mod
from .game import Game, GameNotFoundError, LoadIssue
from .locate import find_game
from .models import (
    Character,
    GameObject,
    Item,
    NamedCollection,
    Passive,
    Spell,
    Status,
    to_record,
)

__version__ = "0.2.0.dev0"

__all__ = [
    "Game",
    "GameNotFoundError",
    "LoadIssue",
    "Mod",
    "find_game",
    "Character",
    "GameObject",
    "Item",
    "NamedCollection",
    "Passive",
    "Spell",
    "Status",
    "to_record",
    "__version__",
]
