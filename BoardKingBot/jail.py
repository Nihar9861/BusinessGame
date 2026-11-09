from board import JAIL_POS
from errors import GameError
from states import State
import economy


def send_to_jail(game, p, why: str = "") -> None:
    p.pos = JAIL_POS
    p.in_jail = True
    p.jail_turns = 0
    game.extra_roll = False
    game.doubles_count = 0
    game.emit(f"🚔 {p.name} jail gaya! {why}".strip())


def roll_for_release(game, p) -> None:
    """Jail turn: roll the dice, doubles = free."""
    d1, d2 = game.roller()
    game.dice = (d1, d2)
    game.emit(f"🎲 {p.name} (jail) roll: {d1}+{d2}")
    if d1 == d2:
        p.in_jail, p.jail_turns = False, 0
        game.extra_roll = False
        game.emit("✅ Doubles! Jail se bahar.")
        game._move(p, d1 + d2)
        return
    p.jail_turns += 1
    if p.jail_turns >= game.rules["max_jail_turns"]:
        game.emit("⛓ 3 turn ho gaye: bail dena padega.")
        p.jail_turns = 0
        if economy.charge(game, p, [(None, game.rules["bail"])], "bail", then={"move": d1 + d2}):
            p.in_jail = False
            game._move(p, d1 + d2)
        return
    game.emit("❌ Doubles nahi aaye.")
    game._advance()


def pay_bail(game, p) -> None:
    if not p.in_jail:
        raise GameError("Aap jail me nahi ho.")
    economy.debit(game, p, game.rules["bail"], "bail")
    p.in_jail, p.jail_turns = False, 0
    game.state = State.WAITING_FOR_ROLL
    game.emit(f"💵 {p.name} ne bail di aur jail se bahar.")


def use_card(game, p) -> None:
    from cards import return_jail_card
    if not p.in_jail:
        raise GameError("Aap jail me nahi ho.")
    if p.jail_cards <= 0:
        raise GameError("Aapke paas Get-Out-Of-Jail card nahi hai.")
    p.jail_cards -= 1
    return_jail_card(game)
    p.in_jail, p.jail_turns = False, 0
    game.state = State.WAITING_FOR_ROLL
    game.emit(f"🃏 {p.name} ne jail-free card use kiya.")
