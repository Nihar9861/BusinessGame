import pytest

import properties
from board import BOARD
from errors import GameError
from states import State


def own(g, uid, *tiles):
    for t in tiles:
        g.tile_owner[t] = uid


def test_buy_property_updates_owner_and_cash(mk):
    from conftest import force
    g = mk(2)
    force(g, (1, 2))
    g.roll(101)
    g.buy(101)
    assert g.tile_owner[3] == 101 and g.players[0].cash == 15000 - 600
    with pytest.raises(GameError):
        g.buy(101)                                  # duplicate click


def test_rent_basic_fullset_houses(mk):
    g = mk(2)
    own(g, 101, 1)
    assert properties.rent_due(g, BOARD[1]) == 20
    own(g, 101, 3)
    assert properties.rent_due(g, BOARD[1]) == 40                      # complete set doubles
    g.houses[1] = 2
    assert properties.rent_due(g, BOARD[1]) == BOARD[1].rents[2]
    g.mortgaged.add(1)
    assert properties.rent_due(g, BOARD[1]) == 0


def test_railway_and_utility_rent(mk):
    g = mk(2)
    own(g, 101, 5)
    assert properties.rent_due(g, BOARD[5]) == 250
    own(g, 101, 15, 25)
    assert properties.rent_due(g, BOARD[5]) == 1000
    own(g, 101, 12)
    assert properties.rent_due(g, BOARD[12], 8) == 32
    own(g, 101, 28)
    assert properties.rent_due(g, BOARD[12], 8) == 80


def test_landing_on_owned_property_pays_rent_to_owner(mk):
    from conftest import force
    g = mk(2)
    own(g, 102, 3)
    force(g, (1, 2))
    g.roll(101)
    assert g.players[0].cash == 15000 - 20 and g.players[1].cash == 15000 + 20


def test_build_rules(mk):
    g = mk(2)
    p = g.players[0]
    own(g, 101, 1)
    with pytest.raises(GameError):
        g.build(101, 1)                                  # no full set
    own(g, 101, 3)
    g.state = State.DICE_ROLLED
    g.build(101, 1)
    with pytest.raises(GameError):
        g.build(101, 1)                                  # must build evenly
    g.build(101, 3)
    assert g.houses == {1: 1, 3: 1} and p.cash == 15000 - 1000
    for _ in range(4):
        g.build(101, 1)
        g.build(101, 3)
    assert g.houses == {1: 5, 3: 5}                      # hotels
    with pytest.raises(GameError):
        g.build(101, 1)


def test_cannot_build_on_foreign_or_railway_or_with_mortgaged(mk):
    g = mk(2)
    own(g, 102, 1, 3)
    with pytest.raises(GameError):
        g.build(101, 1)
    own(g, 101, 5)
    with pytest.raises(GameError):
        g.build(101, 5)


def test_mortgage_unmortgage_cycle(mk):
    g = mk(2)
    p = g.players[0]
    own(g, 101, 39)
    g.state = State.DICE_ROLLED
    g.mortgage(101, 39)
    assert p.cash == 15000 + 2000 and 39 in g.mortgaged
    with pytest.raises(GameError):
        g.mortgage(101, 39)
    g.unmortgage(101, 39)
    assert p.cash == 15000 + 2000 - 2200 and 39 not in g.mortgaged
    with pytest.raises(GameError):
        g.unmortgage(101, 39)


def test_cannot_mortgage_with_houses_and_sell_house_refund(mk):
    g = mk(2)
    own(g, 101, 1, 3)
    g.houses[1] = 1
    g.state = State.DICE_ROLLED
    with pytest.raises(GameError):
        g.mortgage(101, 3)
    cash = g.players[0].cash
    g.sell_house(101, 1)
    assert g.players[0].cash == cash + 250 and 1 not in g.houses


def test_sell_property_to_bank_half_price(mk):
    g = mk(2)
    own(g, 101, 39)
    g.state = State.DICE_ROLLED
    g.sell_property(101, 39)
    assert 39 not in g.tile_owner and g.players[0].cash == 15000 + 2000


def test_cannot_manage_other_players_property(mk):
    g = mk(2)
    own(g, 102, 39)
    g.state = State.DICE_ROLLED
    for fn in (g.mortgage, g.sell_property, g.unmortgage, g.sell_house):
        with pytest.raises(GameError):
            fn(101, 39)
