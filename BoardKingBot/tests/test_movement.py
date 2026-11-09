import pytest

from conftest import force
from errors import GameError
from states import State

NOAUC = {"auction_enabled": False}


def test_movement_follows_board_order_and_lands_on_property(mk):
    g = mk(2, rules=NOAUC)
    force(g, (1, 2))
    g.roll(101)
    assert g.players[0].pos == 3 and g.state == State.PROPERTY_DECISION and g.pending_tile == 3


def test_passing_start_pays_salary(mk):
    g = mk(2, rules=NOAUC)
    p = g.players[0]
    p.pos = 38
    force(g, (1, 2))
    g.roll(101)
    assert p.pos == 1 and p.cash == 15000 + g.rules["salary"]


def test_landing_exactly_on_start_pays_salary(mk):
    g = mk(2, rules=NOAUC)
    p = g.players[0]
    p.pos = 36
    force(g, (2, 2))
    g.roll(101)
    assert p.pos == 0 and p.cash == 15000 + g.rules["salary"]


def test_doubles_give_extra_roll_and_three_doubles_jail(mk):
    g = mk(2, rules=NOAUC)
    p = g.players[0]
    force(g, (3, 3), (2, 2), (1, 1))
    g.roll(101)                       # Bhopal, doubles
    g.skip(101)
    assert g.state == State.WAITING_FOR_ROLL and g.current is p
    g.roll(101)                       # tile 10 (just visiting), doubles again
    assert g.state == State.WAITING_FOR_ROLL and g.current is p and p.pos == 10
    g.roll(101)                       # third double -> jail, turn passes
    assert p.in_jail and p.pos == 10 and g.current is g.players[1]


def test_non_double_ends_in_manage_phase_then_next_player(mk):
    g = mk(2, rules=NOAUC)
    force(g, (1, 2))
    g.roll(101)
    g.skip(101)
    assert g.state == State.DICE_ROLLED
    g.end_turn(101)
    assert g.current.id == 102 and g.state == State.WAITING_FOR_ROLL


def test_only_current_player_can_roll_and_only_once(mk):
    g = mk(2, rules=NOAUC)
    force(g, (1, 2))
    with pytest.raises(GameError):
        g.roll(102)                   # not their turn
    g.roll(101)
    with pytest.raises(GameError):
        g.roll(101)                   # property decision pending
    g.skip(101)
    with pytest.raises(GameError):
        g.roll(101)                   # already rolled this turn


def test_stranger_cannot_act(mk):
    g = mk(2)
    with pytest.raises(GameError):
        g.roll(999)


def test_backward_card_movement_and_card_move_collects_salary(mk):
    g = mk(2, rules=NOAUC)
    p = g.players[0]
    p.pos = 30
    g.decks["chance"] = ["c3"] + g.decks["chance"]        # "Advance to START"
    p.pos = 33
    force(g, (2, 1))                                      # -> tile 36 = Chance
    g.roll(101)
    assert p.pos == 0 and p.cash == 15000 + g.rules["salary"]
