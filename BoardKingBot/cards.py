"""Chance / Event cards, loaded from data/cards.json."""
import json

from board import JAIL_POS, BOARD_SIZE
from config import DATA_DIR
import economy
import jail

CARDS: dict = {}
INDEX: dict = {}


def load_cards() -> None:
    CARDS.clear()
    INDEX.clear()
    CARDS.update(json.loads((DATA_DIR / "cards.json").read_text(encoding="utf-8")))
    for deck in CARDS.values():
        for c in deck:
            INDEX[c["id"]] = c


load_cards()


def init_decks(game) -> None:
    game.decks = {}
    for name, deck in CARDS.items():
        ids = [c["id"] for c in deck]
        game.rng.shuffle(ids)
        game.decks[name] = ids


def draw(game, deck: str) -> dict:
    ids = game.decks[deck]
    cid = ids.pop(0)
    card = INDEX[cid]
    if card["type"] != "jail_free":       # jail card stays with the player until used
        ids.append(cid)
    game.card_history.append(f"{game.current.name}: {card['text']}")
    del game.card_history[:-20]
    return card


def return_jail_card(game) -> None:
    for name, deck in CARDS.items():
        for c in deck:
            if c["type"] == "jail_free" and c["id"] not in game.decks[name]:
                game.decks[name].append(c["id"])
                return


def apply(game, p, card: dict, depth: int = 0) -> bool:
    """Apply card effect. Returns True if the card moved the player (landing already handled)."""
    t = card["type"]
    others = [o for o in game.active_players if o.id != p.id]
    if t == "cash":
        amt = card["amount"]
        if amt >= 0:
            economy.credit(game, p, amt, "card")
        else:
            economy.charge(game, p, [(None, -amt)], "card fine")
    elif t == "collect_all":
        for o in others:
            pay = min(o.cash, card["amount"])
            if pay:
                economy.transfer(game, o, p, pay, "card collect")
    elif t == "pay_all":
        economy.charge(game, p, [(o.id, card["amount"]) for o in others], "card pay players")
    elif t == "move_to":
        dest = card["tile"]
        passed = card.get("salary", True) and dest < p.pos
        game._place(p, dest, passed, depth + 1)
        return True
    elif t == "move_by":
        old = p.pos
        dest = (old + card["steps"]) % BOARD_SIZE
        game._place(p, dest, card["steps"] > 0 and old + card["steps"] >= BOARD_SIZE, depth + 1)
        return True
    elif t == "goto_jail":
        jail.send_to_jail(game, p, "(card)")
    elif t == "jail_free":
        p.jail_cards += 1
        game.emit(f"🃏 {p.name} ko jail-free card mila.")
    elif t == "repair":
        cost = 0
        for tid in [i for i, o in game.tile_owner.items() if o == p.id]:
            h = game.houses.get(tid, 0)
            cost += card["hotel"] if h == 5 else h * card["house"]
        if cost:
            economy.charge(game, p, [(None, cost)], "repairs")
    return False
