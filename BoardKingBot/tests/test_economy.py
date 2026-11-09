import pytest

import economy
from errors import GameError, InsufficientFunds
from states import State


def test_credit_debit_transfer_and_history(mk):
    g = mk(2)
    a, b = g.players
    economy.credit(g, a, 500, "gift")
    economy.debit(g, a, 200, "fee")
    economy.transfer(g, a, b, 300, "pay")
    assert a.cash == 15000 and b.cash == 15300
    assert [t["reason"] for t in g.tx[-3:]] == ["gift", "fee", "pay"]
    assert g.pending_tx and all(t["amount"] > 0 for t in g.tx)


def test_never_negative_balance(mk):
    g = mk(2)
    a, b = g.players
    with pytest.raises(InsufficientFunds):
        economy.debit(g, a, 15001, "too much")
    with pytest.raises(InsufficientFunds):
        economy.transfer(g, a, b, 99999, "too much")
    assert a.cash == 15000 and b.cash == 15000          # nothing changed
    with pytest.raises(GameError):
        economy.credit(g, a, -5, "negative")


def test_income_tax_is_paid_to_bank(mk):
    g = mk(2, rules={"auction_enabled": False})
    from conftest import force
    force(g, (1, 3))                                     # tile 4 = Income Tax 2000
    g.roll(101)
    assert g.players[0].cash == 13000


def test_cannot_afford_creates_debt_and_blocks_turn(mk):
    from conftest import force
    g = mk(2)
    p = g.players[0]
    p.cash = 100
    force(g, (1, 3))
    g.roll(101)
    assert g.state == State.PAYMENT and g.debt["total"] == 2000 and p.cash == 100
    with pytest.raises(GameError):
        g.end_turn(101)
    with pytest.raises(GameError):
        g.pay_debt(101)                                  # still too poor
    g.players[0].cash = 2500
    g.pay_debt(101)
    assert p.cash == 500 and g.state == State.DICE_ROLLED


def test_net_worth_counts_assets(mk):
    g = mk(2)
    p = g.players[0]
    g.tile_owner[39] = p.id
    g.houses[39] = 2
    g.mortgaged.add(37) if False else None
    assert economy.net_worth(g, p) == 15000 + 4000 + 2 * 2000


def test_free_parking_jackpot_rule(mk):
    from conftest import force
    g = mk(2, rules={"free_parking_jackpot": True})
    force(g, (1, 3), (5, 5))
    g.roll(101)                       # pays 2000 tax -> pot
    assert g.pot == 2000
    g.end_turn(101)
    g.players[1].pos = 10
    g.roll(102)                       # 10 + 10 = tile 20 free parking
    assert g.players[1].cash == 15000 + 2000 and g.pot == 0
