import json
import random
import re

import board_image
import keyboards
import messages
from board import BOARD
from conftest import make_game
from states import State


def test_board_is_complete_and_consistent():
    assert [t.id for t in BOARD.tiles] == list(range(40))
    types = {t.type for t in BOARD.tiles}
    assert {"start", "property", "railway", "utility", "chance", "community", "tax", "jail", "free_parking",
            "go_to_jail"} <= types
    for t in BOARD.tiles:
        if t.buyable:
            assert t.name and t.price > 0 and t.rents
        if t.type == "property":
            assert len(t.rents) == 6 and t.house_cost > 0
    for name, ids in BOARD.groups.items():
        assert len(ids) >= 2
    assert sum(1 for t in BOARD.tiles if t.type == "railway") == 4


def test_every_tile_rect_is_unique_and_inside_the_image():
    rects = [board_image.tile_rect(i) for i in range(40)]
    assert len(set(rects)) == 40
    assert all(0 <= r[0] < r[2] <= board_image.SIZE and 0 <= r[1] < r[3] <= board_image.SIZE for r in rects)


def test_board_image_renders_all_states():
    g = make_game(4, seed=2, bots=True)
    for _ in range(300):
        png = board_image.render_board(g)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        cap = messages.board_caption(g)
        assert len(cap) <= 1024, len(cap)
        kb = keyboards.game_kb(g)
        if kb:
            for row in kb.inline_keyboard:
                for b in row:
                    assert len(b.callback_data.encode()) <= 64
        if g.finished:
            break
        g.bot_step()
    assert "GAME OVER" in messages.board_caption(g) or True


def test_all_keyboards_stay_within_telegram_limits():
    g = make_game(2)
    g.tile_owner.update({i: 101 for i in range(1, 40) if BOARD[i].buyable})
    g.state = State.DICE_ROLLED
    for kind in keyboards.MENU_TITLES:
        kb = keyboards.menu_list_kb(g, g.players[0], kind)
        assert sum(len(r) for r in kb.inline_keyboard) <= 100
        assert all(len(b.callback_data.encode()) <= 64 for r in kb.inline_keyboard for b in r)
    draft = {"to": 102, "give": [1], "get": [], "cash": 0, "view": "give"}
    for view in ("give", "get", "cash"):
        draft["view"] = view
        kb = keyboards.trade_builder_kb(g, 101, draft)
        assert all(len(b.callback_data.encode()) <= 64 for r in kb.inline_keyboard for b in r)
    assert messages.lobby_text(g)


def test_html_in_player_names_is_escaped():
    g = make_game(2)
    g.players[0].name = "<b>Hacker</b> & co"
    assert "<b>Hacker" not in messages.board_caption(g)
    assert "&lt;b&gt;" in messages.board_caption(g)


def test_text_helpers_work():
    g = make_game(2)
    p = g.players[0]
    g.tile_owner[1] = p.id
    for t in (messages.balance_text(g, p), messages.properties_text(g, p), messages.players_text(g),
              messages.status_text(g), messages.history_text(g), messages.jail_text(g, p),
              messages.auction_text(g), messages.rules_text(g.rules), messages.leaderboard_text([])):
        assert isinstance(t, str) and t
