import pytest

from errors import GameError
from states import State


def setup(mk):
    g = mk(2)
    g.tile_owner.update({1: 101, 39: 102})
    g.state = State.DICE_ROLLED
    return g


def test_trade_swaps_properties_and_cash(mk):
    g = setup(mk)
    g.propose_trade(101, 102, [1], [39], 500)
    assert g.pending_trade
    g.accept_trade(102)
    assert g.tile_owner == {1: 102, 39: 101}
    assert g.players[0].cash == 14500 and g.players[1].cash == 15500 and g.pending_trade is None


def test_trade_cash_only_and_receive_cash(mk):
    g = setup(mk)
    g.propose_trade(101, 102, [], [39], -1000)        # I take Mumbai AND 1000 from them
    g.accept_trade(102)
    assert g.tile_owner[39] == 101 and g.players[0].cash == 16000


def test_only_target_can_accept_and_reject_cancels(mk):
    g = setup(mk)
    g.propose_trade(101, 102, [1], [], 0)
    with pytest.raises(GameError):
        g.accept_trade(101)
    with pytest.raises(GameError):
        g.accept_trade(999)
    g.reject_trade(102)
    assert g.pending_trade is None and g.tile_owner[1] == 101


def test_proposer_can_cancel(mk):
    g = setup(mk)
    g.propose_trade(101, 102, [1], [], 0)
    g.reject_trade(101)
    assert g.pending_trade is None


def test_invalid_trades_rejected(mk):
    g = setup(mk)
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [39], [], 0)         # not mine
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [], [1], 0)          # not theirs
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [1], [], 999999)     # can't afford
    with pytest.raises(GameError):
        g.propose_trade(101, 101, [1], [], 0)          # self trade
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [], [], 0)           # empty
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [1, 1], [], 0)       # duplicate


def test_only_one_pending_trade(mk):
    g = setup(mk)
    g.propose_trade(101, 102, [1], [], 0)
    with pytest.raises(GameError):
        g.propose_trade(102, 101, [39], [], 0)


def test_trade_is_revalidated_and_atomic(mk):
    g = setup(mk)
    g.propose_trade(101, 102, [1], [39], 500)
    g.players[0].cash = 100                            # proposer got poor after proposing
    with pytest.raises(GameError):
        g.accept_trade(102)
    assert g.tile_owner == {1: 101, 39: 102} and g.players[0].cash == 100 and g.players[1].cash == 15000
    assert g.pending_trade is None


def test_trade_expires(mk):
    import time
    g = setup(mk)
    g.propose_trade(101, 102, [1], [], 0)
    g.deadline = time.time() + 999
    assert g.check_timeouts(now=time.time() + g.rules["trade_timeout"] + 5)
    assert g.pending_trade is None


def test_no_trade_for_properties_with_houses(mk):
    g = setup(mk)
    g.tile_owner[3] = 101
    g.houses[1] = 1
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [3], [], 0)
