import random
import time

import pytest

import economy
from conftest import force, make_game
from errors import GameError
from game_engine import Game
from game_manager import RateLimiter, manager
from states import State


# ------------------------------------------------------------------ lobby
def test_lobby_rules():
    g = Game("BG-1", 1, 1, rng=random.Random(1))
    g.add_player(1, "Host")
    with pytest.raises(GameError):
        g.add_player(1, "Host")                       # duplicate join
    with pytest.raises(GameError):
        g.start(1)                                    # needs 2 players
    for i in (2, 3, 4):
        g.add_player(i, f"P{i}")
    with pytest.raises(GameError):
        g.add_player(5, "P5")                         # room full
    with pytest.raises(GameError):
        g.start(2)                                    # only host starts
    g.start(1)
    assert g.state == State.WAITING_FOR_ROLL and len(g.players) == 4
    with pytest.raises(GameError):
        g.add_player(6, "Late")                       # no joining after start
    with pytest.raises(GameError):
        g.start(1)


def test_leave_lobby_transfers_host():
    g = Game("BG-1", 1, 1, rng=random.Random(1))
    g.add_player(1, "Host")
    g.add_player(2, "B")
    g.leave(1)
    assert g.host_id == 2 and [p.id for p in g.players] == [2]


def test_bot_players_count_and_only_host_adds():
    g = Game("BG-1", 1, 1, rng=random.Random(1))
    g.add_player(1, "Host")
    with pytest.raises(GameError):
        g.add_bot(2)
    g.add_bot(1)
    g.add_bot(1)
    g.add_bot(1)
    with pytest.raises(GameError):
        g.add_bot(1)
    assert len(g.players) == 4


# ------------------------------------------------------------------ auction
def to_auction(mk, **kw):
    g = mk(2, **kw)
    force(g, (1, 2))
    g.roll(101)
    g.skip(101)                                       # declines Ranchi (600)
    assert g.state == State.AUCTION
    return g


def test_auction_winner_pays_and_gets_property(mk):
    g = to_auction(mk)
    g.bid(102, 100)
    with pytest.raises(GameError):
        g.bid(102, 100)                               # already highest
    g.bid(101, 500)                                   # 600
    g.bid(102, 1000)                                  # 1600
    g.pass_auction(101)
    assert g.tile_owner[3] == 102 and g.players[1].cash == 15000 - 1600
    assert g.state == State.DICE_ROLLED and g.auction is None


def test_auction_all_pass_leaves_bank_owner(mk):
    g = to_auction(mk)
    g.pass_auction(101)
    g.pass_auction(102)
    assert 3 not in g.tile_owner and g.state == State.DICE_ROLLED


def test_auction_invalid_bids(mk):
    g = to_auction(mk)
    g.players[1].cash = 300
    with pytest.raises(GameError):
        g.bid(102, 500)                               # more than cash
    with pytest.raises(GameError):
        g.bid(102, 150)                               # not a valid step
    with pytest.raises(GameError):
        g.bid(102, -100)
    g.bid(102, 100)
    with pytest.raises(GameError):
        g.pass_auction(102)                           # highest bidder cannot pass
    g.pass_auction(101)
    with pytest.raises(GameError):
        g.bid(101, 100)                               # no auction anymore


def test_auction_timer_closes_it(mk):
    g = to_auction(mk)
    g.bid(102, 100)
    g.deadline = 0
    assert g.check_timeouts()
    assert g.tile_owner[3] == 102


def test_auction_disabled_keeps_property_with_bank(mk):
    g = mk(2, rules={"auction_enabled": False})
    force(g, (1, 2))
    g.roll(101)
    g.skip(101)
    assert g.state == State.DICE_ROLLED and 3 not in g.tile_owner


def test_cannot_afford_goes_straight_to_auction(mk):
    g = mk(2)
    g.players[0].cash = 100
    force(g, (1, 2))
    g.roll(101)
    assert g.state == State.AUCTION


# ------------------------------------------------------------------ jail
def test_go_to_jail_tile_and_turn_passes(mk):
    g = mk(2)
    g.players[0].pos = 20
    force(g, (5, 5))
    g.roll(101)
    p = g.players[0]
    assert p.in_jail and p.pos == 10 and g.current.id == 102


def jailed(mk, **kw):
    g = mk(2, **kw)
    p = g.players[0]
    p.in_jail, p.pos = True, 10
    g.state = State.JAIL_DECISION
    return g, p


def test_jail_doubles_escape_moves_without_extra_turn(mk):
    g, p = jailed(mk, rules={"auction_enabled": False})
    force(g, (1, 1))
    g.roll(101)                                       # tile 12 utility
    assert not p.in_jail and p.pos == 12 and g.state == State.PROPERTY_DECISION
    g.skip(101)
    assert g.state == State.DICE_ROLLED               # doubles in jail give no extra roll


def test_jail_failed_roll_passes_turn_and_counts(mk):
    g, p = jailed(mk)
    force(g, (1, 2))
    g.roll(101)
    assert p.in_jail and p.jail_turns == 1 and g.current.id == 102


def test_jail_third_failure_forces_bail(mk):
    g, p = jailed(mk, rules={"auction_enabled": False})
    p.jail_turns = 2
    force(g, (1, 2))
    g.roll(101)
    assert not p.in_jail and p.cash == 15000 - 500 and p.pos == 13 and g.state == State.PROPERTY_DECISION


def test_pay_bail_and_jail_card(mk):
    g, p = jailed(mk)
    g.pay_bail(101)
    assert not p.in_jail and p.cash == 14500 and g.state == State.WAITING_FOR_ROLL
    g2, p2 = jailed(mk)
    with pytest.raises(GameError):
        g2.use_jail_card(101)                         # no card
    p2.jail_cards = 1
    g2.use_jail_card(101)
    assert not p2.in_jail and p2.jail_cards == 0


def test_cannot_pay_bail_when_not_in_jail(mk):
    g = mk(2)
    with pytest.raises(GameError):
        g.pay_bail(101)


def test_jail_card_from_deck_goes_back(mk):
    g = mk(2)
    g.decks["chance"] = ["c8"] + [c for c in g.decks["chance"] if c != "c8"]
    g.players[0].pos = 0
    force(g, (3, 4))                                  # tile 7 = chance -> draws c8
    g.roll(101)
    assert g.players[0].jail_cards == 1 and "c8" not in g.decks["chance"]
    g.players[0].in_jail = True
    g.state = State.JAIL_DECISION
    g.current  # still p1
    g.use_jail_card(101)
    assert "c8" in g.decks["chance"]


# ------------------------------------------------------------------ cards
@pytest.mark.parametrize("card,check", [
    ("c1", lambda g, p: p.cash == 15000 + 1500),
    ("c2", lambda g, p: p.cash == 15000 - 500),
    ("c10", lambda g, p: p.cash == 15000 + 300 and g.players[1].cash == 15000 - 300),
    ("c13", lambda g, p: p.cash == 15000 - 200 and g.players[1].cash == 15000 + 200),
    ("c7", lambda g, p: p.in_jail and p.pos == 10),
    ("c5", lambda g, p: p.pos == 4),                  # back 3 from 7 -> Income Tax
])
def test_cards(mk, card, check):
    g = mk(2, rules={"auction_enabled": False})
    g.decks["chance"] = [card] + g.decks["chance"]
    force(g, (3, 4))
    g.roll(101)
    p = g.players[0]
    if card == "c5":
        assert p.pos == 4 and p.cash == 15000 - 2000
    else:
        assert check(g, p)
    assert g.card_history


def test_repair_card_charges_per_house_and_hotel(mk):
    g = mk(2)
    g.tile_owner.update({1: 101, 3: 101})
    g.houses.update({1: 2, 3: 5})
    g.decks["chance"] = ["c9"] + g.decks["chance"]
    force(g, (3, 4))
    g.roll(101)
    assert g.players[0].cash == 15000 - (2 * 250 + 1000)


# ------------------------------------------------------------------ bankruptcy
def rent_trap(mk, n=2):
    g = mk(n)
    g.tile_owner[39] = 102
    g.houses[39] = 5                                  # Mumbai hotel: rent 55,000
    p = g.players[0]
    p.pos = 36
    force(g, (1, 2))
    g.roll(101)
    return g, p


def test_bankruptcy_two_players_winner_detected(mk):
    g, p = rent_trap(mk)
    assert g.state == State.PAYMENT and g.debt["total"] == 55000
    with pytest.raises(GameError):
        g.mortgage(102, 39)                           # not the debtor
    g.declare_bankruptcy(101)
    assert p.bankrupt and g.state == State.GAME_OVER and g.winner_id == 102
    assert g.players[1].cash == 30000 and g.players[1].rank == 1 and p.rank == 2


def test_bankruptcy_transfers_assets_and_game_continues(mk):
    g, p = rent_trap(mk, 3)
    g.tile_owner[1] = 101
    g.declare_bankruptcy(101)
    assert g.tile_owner[1] == 102 and p.bankrupt
    assert g.state == State.WAITING_FOR_ROLL and g.current.id == 102
    assert not g.finished


def test_raising_money_by_mortgage_pays_debt_automatically(mk):
    g = mk(2)
    p = g.players[0]
    p.cash = 1500
    g.tile_owner[39] = 101
    p.pos = 0
    force(g, (1, 3))                                  # income tax 2000
    g.roll(101)
    assert g.state == State.PAYMENT
    g.mortgage(101, 39)                               # +2000 -> 3500 >= 2000 -> auto-pay
    assert g.state == State.DICE_ROLLED and p.cash == 1500


def test_bankrupt_to_bank_releases_properties(mk):
    g = mk(2)
    p = g.players[0]
    p.cash = 0
    g.tile_owner[1] = 101
    g.mortgaged.add(1)
    p.pos = 0
    force(g, (1, 3))
    g.roll(101)
    g.declare_bankruptcy(101)
    assert 1 not in g.tile_owner and 1 not in g.mortgaged and g.finished


def test_bankrupt_player_is_skipped_in_turn_order(mk):
    g = mk(3)
    g.players[1].bankrupt = True
    g.players[1].rank = 3
    g.state = State.DICE_ROLLED
    g.end_turn(101)
    assert g.current.id == 103
    assert len(g.active_players) == 2
    with pytest.raises(GameError):
        g.roll(102)                                   # bankrupt player cannot act


def test_leaving_running_game_forfeits(mk):
    g = mk(3)
    g.tile_owner[1] = 102
    g.leave(102)
    assert g.players[1].bankrupt and 1 not in g.tile_owner and not g.finished
    g.leave(103)
    assert g.finished and g.winner_id == 101


# ------------------------------------------------------------------ timeouts / afk
def test_turn_timeout_auto_rolls_and_afk_kicks(mk):
    g = mk(3, rules={"auction_enabled": False})
    force(g, (1, 2), (1, 2), (1, 2))
    p = g.players[0]
    g.deadline = 0
    assert g.check_timeouts()
    assert p.afk == 1 and g.state == State.PROPERTY_DECISION
    g.deadline = 0
    g.check_timeouts()                                # auto-skip
    assert g.state == State.DICE_ROLLED
    g.deadline = 0
    g.check_timeouts()                                # auto end turn
    assert g.current.id == 102
    p.afk = 2
    g.current_idx = None
    g.turn = 0
    g.state = State.WAITING_FOR_ROLL
    g.deadline = 0
    g.check_timeouts()
    assert p.bankrupt                                 # 3rd consecutive timeout -> removed


def test_no_timeout_before_deadline(mk):
    g = mk(2)
    g.deadline = time.time() + 100
    assert not g.check_timeouts()


def test_round_limit_declares_richest_winner(mk):
    g = mk(2, rules={"max_rounds": 1})
    g.players[1].cash = 20000
    g.state = State.DICE_ROLLED
    g.end_turn(101)
    g.state = State.DICE_ROLLED
    g.end_turn(102)
    assert g.finished and g.winner_id == 102


# ------------------------------------------------------------------ full games
@pytest.mark.parametrize("n", [2, 4])
def test_full_bot_games_finish_with_consistent_state(n):
    for seed in range(8):
        g = make_game(n, seed=seed, bots=True, rules={"max_rounds": 50})
        steps = 0
        while not g.finished:
            steps += 1
            assert steps < 20000
            assert g.bot_step()
            assert all(p.cash >= 0 for p in g.players)
            assert all(o in {p.id for p in g.active_players} for o in g.tile_owner.values())
        assert g.winner_id is not None
        assert sorted(p.rank for p in g.players) == list(range(1, n + 1))


def test_simultaneous_games_are_independent():
    a = make_game(2, seed=1)
    b = make_game(2, seed=2)
    force(a, (1, 2))
    a.roll(101)
    assert a.players[0].pos == 3 and b.players[0].pos == 0
    assert a.version != b.version


# ------------------------------------------------------------------ restart / persistence
def test_snapshot_roundtrip_mid_auction(mk):
    g = to_auction(mk)
    g.bid(102, 100)
    g2 = Game.from_dict(__import__("json").loads(__import__("json").dumps(g.to_dict())))
    assert g2.state == State.AUCTION and g2.auction == g.auction
    g2.pass_auction(101)
    assert g2.tile_owner[3] == 102


def test_database_save_and_restore_after_restart(mk):
    g = make_game(2, seed=3)
    manager.games[g.room_id] = g
    force(g, (1, 2))
    g.roll(101)
    g.buy(101)
    manager.save(g)
    manager.games.clear()                              # "bot restart"
    assert manager.load_all() == 1
    r = manager.get("BG-TEST")
    assert r.tile_owner == {3: 101} and r.state == State.DICE_ROLLED
    r.end_turn(101)
    assert r.current.id == 102
    from sqlalchemy import func
    import database, models
    with database.session_scope() as s:
        assert s.query(models.TransactionRow).count() >= 1
        assert s.query(models.PropertyRow).filter_by(room_id="BG-TEST").count() == 1


def test_save_twice_creates_no_duplicates(mk):
    import database, models
    g = make_game(2)
    manager.games[g.room_id] = g
    manager.save(g)
    manager.save(g)
    with database.session_scope() as s:
        assert s.query(models.GameRoom).count() == 1
        assert s.query(models.PlayerRow).count() == 2


def test_stats_recorded_once_and_leaderboard():
    g = make_game(2, seed=4)
    manager.games[g.room_id] = g
    manager.upsert_user(101, "a", "P1")
    manager.upsert_user(102, "b", "P2")
    g.state = State.DICE_ROLLED
    g.players[1].bankrupt = True
    g.players[1].rank = 2
    g._check_winner()
    manager.finish_game(g)
    manager.finish_game(g)                             # second call must not double count
    u = manager.profile(101)
    assert (u.games_played, u.games_won) == (1, 1) and u.win_percentage == 100.0
    assert manager.profile(102).games_lost == 1 and manager.profile(102).bankruptcies == 1
    assert manager.leaderboard()[0][0] == "P1"


def test_rate_limiter():
    r = RateLimiter(limit=3, window=10)
    assert [r.hit(1, now=100) for _ in range(4)] == [True, True, True, False]
    assert r.hit(2, now=100)                           # other users unaffected
    assert r.hit(1, now=111)                           # window passed


# ------------------------------------------------------------------ security
def test_actions_require_the_right_state_and_player(mk):
    g = mk(2)
    for fn, args in [(g.buy, (101,)), (g.skip, (101,)), (g.end_turn, (101,)), (g.pay_bail, (101,)),
                     (g.pay_debt, (101,)), (g.declare_bankruptcy, (101,)), (g.bid, (101, 100)),
                     (g.accept_trade, (101,))]:
        with pytest.raises(GameError):
            fn(*args)
    with pytest.raises(GameError):
        g.buy(102)
    with pytest.raises(GameError):
        g.build(999, 1)


def test_management_blocked_during_auction(mk):
    g = to_auction(mk)
    g.tile_owner[39] = 101
    with pytest.raises(GameError):
        g.mortgage(101, 39)
    with pytest.raises(GameError):
        g.propose_trade(101, 102, [39], [], 0)


def test_failed_action_does_not_change_version(mk):
    g = mk(2)
    v = g.version
    with pytest.raises(GameError):
        g.roll(102)
    assert g.version == v
