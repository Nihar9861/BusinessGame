import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123456:TEST")

import pytest

import database
from config import load_rules
from game_engine import Game
from game_manager import manager


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    database.init_db(f"sqlite:///{tmp_path / 'test.db'}")
    manager.games.clear()
    manager._locks.clear()
    manager.limiter.hits.clear()
    yield


def make_game(n=2, seed=1, rules=None, bots=False):
    """Helper: a started game with n players (ids 101..). Dice can be forced with g.roller."""
    r = {**load_rules(), **(rules or {})}
    g = Game("BG-TEST", 1, 101, r, rng=random.Random(seed))
    for i in range(n):
        if bots:
            g.add_player_raw(-(i + 1), f"Bot{i + 1}")
        else:
            g.add_player(101 + i, f"P{i + 1}")
    if bots:
        g.host_id = -1
    g.start(g.host_id)
    # make the order deterministic: lowest id first
    g.players.sort(key=lambda p: p.id if p.id > 0 else -p.id)
    g.turn = 0
    return g


def force(g, *rolls):
    """Force the next dice rolls, e.g. force(g, (3, 4), (1, 1))."""
    it = iter(rolls)
    g.roller = lambda: next(it)


@pytest.fixture
def mk():
    return make_game
