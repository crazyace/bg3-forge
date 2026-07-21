"""BG3 Forge — a toolkit for Baldur's Gate 3 assets and game data.

Library-first: everything the CLI does is available as importable,
reusable modules.

    from bg3forge import Game

    game = Game()
    for item in game.items:
        print(item.name)
"""

from .game import Game, GameNotFoundError
from .locate import find_game
from .models import GameObject, Item, NamedCollection, Passive, Spell, Status, to_record

__version__ = "0.1.0"

__all__ = [
    "Game",
    "GameNotFoundError",
    "find_game",
    "GameObject",
    "Item",
    "NamedCollection",
    "Passive",
    "Spell",
    "Status",
    "to_record",
    "__version__",
]
