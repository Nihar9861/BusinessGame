"""Player-to-player trades: properties + cash, validated and executed atomically."""
import time

from errors import GameError
from states import State
import economy
import properties


def _validate(game, t: dict) -> tuple:
    a, b = game.player(t["from"]), game.player(t["to"])
    if a.bankrupt or b.bankrupt:
        raise GameError("Trade me bankrupt player nahi ho sakta.")
    if t["from"] == t["to"]:
        raise GameError("Khud se trade nahi kar sakte.")
    if not (t["give"] or t["get"] or t["cash"]):
        raise GameError("Trade khali hai.")
    for tid in list(t["give"]) + list(t["get"]):
        if not (0 <= tid < len(game.board)) or not game.board[tid].buyable:
            raise GameError("Galat property.")
    if len(set(t["give"])) != len(t["give"]) or len(set(t["get"])) != len(t["get"]):
        raise GameError("Duplicate property.")
    for tid in t["give"]:
        if game.tile_owner.get(tid) != a.id:
            raise GameError(f"{game.board[tid].name} aapki nahi hai.")
    for tid in t["get"]:
        if game.tile_owner.get(tid) != b.id:
            raise GameError(f"{game.board[tid].name} samne wale ki nahi hai.")
    for tid in list(t["give"]) + list(t["get"]):
        if properties.group_has_buildings(game, game.board[tid]):
            raise GameError("Ghar/hotel wale set ki property trade nahi hoti. Pehle ghar becho.")
    if t["cash"] > 0 and a.cash < t["cash"]:
        raise GameError("Proposer ke paas itna cash nahi hai.")
    if t["cash"] < 0 and b.cash < -t["cash"]:
        raise GameError("Samne wale ke paas itna cash nahi hai.")
    return a, b


def propose(game, uid: int, to_uid: int, give: list, get: list, cash: int) -> None:
    if game.state in (State.WAITING_FOR_PLAYERS, State.GAME_OVER, State.AUCTION, State.PAYMENT):
        raise GameError("Abhi trade nahi ho sakta.")
    if game.pending_trade:
        raise GameError("Ek trade offer pehle se pending hai.")
    trade = {"from": uid, "to": to_uid, "give": list(give), "get": list(get), "cash": int(cash),
             "expires": time.time() + game.rules["trade_timeout"]}
    a, b = _validate(game, trade)
    game.pending_trade = trade
    game.emit(f"🤝 {a.name} ne {b.name} ko trade offer bheja.")


def accept(game, uid: int) -> None:
    t = game.pending_trade
    if not t:
        raise GameError("Koi trade pending nahi hai.")
    if uid != t["to"]:
        raise GameError("Ye offer aapke liye nahi hai.")
    if game.state in (State.AUCTION, State.PAYMENT):
        raise GameError("Abhi trade accept nahi ho sakta.")
    try:
        a, b = _validate(game, t)          # re-check everything at execution time
    except GameError as e:
        game.pending_trade = None
        raise GameError(f"Trade cancel: {e}")
    for tid in t["give"]:
        game.tile_owner[tid] = b.id
    for tid in t["get"]:
        game.tile_owner[tid] = a.id
    if t["cash"] > 0:
        economy.transfer(game, a, b, t["cash"], "trade")
    elif t["cash"] < 0:
        economy.transfer(game, b, a, -t["cash"], "trade")
    game.pending_trade = None
    game.emit(f"✅ Trade complete: {a.name} ↔ {b.name}")


def reject(game, uid: int) -> None:
    t = game.pending_trade
    if not t:
        raise GameError("Koi trade pending nahi hai.")
    if uid == t["to"]:
        game.emit("❌ Trade reject hua.")
    elif uid == t["from"]:
        game.emit("🚫 Trade cancel kiya gaya.")
    else:
        raise GameError("Aap is trade me shamil nahi ho.")
    game.pending_trade = None
