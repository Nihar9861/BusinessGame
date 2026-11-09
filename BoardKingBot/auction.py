"""Auction of an unbought property among all active players."""
from errors import GameError
from states import State
import economy


def start(game, tile_id: int) -> None:
    t = game.board[tile_id]
    inc = game.rules["auction_increment"]
    min_bid = max(inc, (t.price // 10 // inc) * inc)
    game.auction = {"tile": tile_id, "high": 0, "bidder": None, "passed": [], "min_bid": min_bid, "inc": inc}
    game.state = State.AUCTION
    game.emit(f"🔨 Auction shuru: {t.name} (min bid {min_bid})")
    check_close(game)


def remaining(game) -> list:
    a = game.auction
    return [p for p in game.active_players if p.id not in a["passed"] and p.id != a["bidder"]]


def bid(game, uid: int, step: int) -> None:
    a = game.auction
    if game.state != State.AUCTION or not a:
        raise GameError("Abhi koi auction nahi chal raha.")
    p = game.player(uid)
    if p.bankrupt:
        raise GameError("Aap game se bahar ho.")
    if uid in a["passed"]:
        raise GameError("Aap is auction se pass kar chuke ho.")
    if a["bidder"] == uid:
        raise GameError("Aap already sabse upar ho.")
    if step <= 0 or step % a["inc"]:
        raise GameError("Galat bid step.")
    amount = max(a["min_bid"], a["high"] + step)
    if amount > p.cash:
        raise GameError(f"Itna paisa nahi hai (bid {amount}, cash {p.cash}).")
    a["high"], a["bidder"] = amount, uid
    game.emit(f"💰 {p.name} ne {amount} ki bid lagayi.")
    check_close(game)


def pass_(game, uid: int) -> None:
    a = game.auction
    if game.state != State.AUCTION or not a:
        raise GameError("Abhi koi auction nahi chal raha.")
    p = game.player(uid)
    if a["bidder"] == uid:
        raise GameError("Sabse upar wala bidder pass nahi kar sakta.")
    if uid in a["passed"]:
        raise GameError("Aap already pass kar chuke ho.")
    a["passed"].append(uid)
    game.emit(f"🚫 {p.name} ne pass kiya.")
    check_close(game)


def check_close(game) -> None:
    a = game.auction
    floor = a["high"] + a["inc"] if a["bidder"] is not None else a["min_bid"]
    for p in game.active_players:       # players who can no longer outbid are out
        if p.id not in a["passed"] and p.id != a["bidder"] and p.cash < floor:
            a["passed"].append(p.id)
    if not remaining(game):
        resolve(game)


def resolve(game) -> None:
    a = game.auction
    game.auction = None
    t = game.board[a["tile"]]
    if a["bidder"] is not None:
        w = game.player(a["bidder"])
        try:
            economy.debit(game, w, a["high"], f"auction {t.name}")
            game.tile_owner[t.id] = w.id
            game.emit(f"🏆 {w.name} ne {t.name} {a['high']} me jeeta!")
        except GameError:
            game.emit(f"⚠️ {w.name} payment nahi kar paya. {t.name} bank ke paas.")
    else:
        game.emit(f"🏦 {t.name} kisi ne nahi kharida (bank ke paas).")
    game._finish()
