"""All money movement goes through here. Balances can never go negative."""
import time

from errors import GameError, InsufficientFunds
from states import State

BANK = None  # payee/payer id for the bank


def record(game, frm, to, amount: int, reason: str) -> None:
    tx = {"ts": int(time.time()), "from": frm, "to": to, "amount": int(amount), "reason": reason}
    game.tx.append(tx)
    game.pending_tx.append(tx)
    del game.tx[:-300]


def credit(game, p, amount: int, reason: str, frm=BANK) -> None:
    if amount < 0:
        raise GameError("Invalid amount.")
    p.cash += amount
    record(game, frm, p.id, amount, reason)


def debit(game, p, amount: int, reason: str, to=BANK) -> None:
    if amount < 0:
        raise GameError("Invalid amount.")
    if p.cash < amount:
        raise InsufficientFunds(f"Paise kam hain: chahiye {amount}, hai {p.cash}.")
    p.cash -= amount
    record(game, p.id, to, amount, reason)


def transfer(game, src, dst, amount: int, reason: str) -> None:
    """Atomic player -> player transfer (validates first)."""
    if src.cash < amount:
        raise InsufficientFunds("Paise kam hain.")
    src.cash -= amount
    dst.cash += amount
    record(game, src.id, dst.id, amount, reason)


def net_worth(game, p) -> int:
    total = p.cash
    for tid, owner in game.tile_owner.items():
        if owner != p.id:
            continue
        t = game.board[tid]
        total += t.mortgage_value if tid in game.mortgaged else t.price
        total += game.houses.get(tid, 0) * t.house_cost
    return total


def charge(game, p, payees: list, reason: str, pot: bool = False, then: dict | None = None) -> bool:
    """Try to make player p pay [(payee_id_or_None, amount), ...].
    Pays at once if affordable. Otherwise creates a debt, switches the game to
    PAYMENT state (player must raise money or go bankrupt) and returns False."""
    total = sum(a for _, a in payees)
    if total <= 0:
        return True
    if p.cash >= total:
        settle(game, p, payees, reason, pot)
        return True
    game.debt = {"debtor": p.id, "payees": [list(x) for x in payees], "reason": reason,
                 "total": total, "pot": pot, "then": then}
    game.state = State.PAYMENT
    game.emit(f"⚠️ {p.name} ko {total} dena hai ({reason}) par cash {p.cash} hai. Asset becho/mortgage karo.")
    return False


def settle(game, p, payees, reason, pot=False) -> None:
    total = sum(a for _, a in payees)
    if p.cash < total:
        raise InsufficientFunds("Paise kam hain.")
    for payee_id, amt in payees:
        if amt <= 0:
            continue
        if payee_id is None:
            debit(game, p, amt, reason)
        else:
            transfer(game, p, game.player(payee_id), amt, reason)
    if pot:
        game.pot += total
