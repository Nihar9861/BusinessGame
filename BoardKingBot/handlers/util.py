"""Shared helpers for all handlers: locking, saving, error handling, anti-spam."""
import html
import logging
import re

from config import MAINTENANCE
from errors import GameError
from game_manager import manager
import messages
import ui

log = logging.getLogger(__name__)

ACTIONS = {
    "roll": lambda g, u: g.roll(u), "buy": lambda g, u: g.buy(u), "skip": lambda g, u: g.skip(u),
    "end": lambda g, u: g.end_turn(u), "bail": lambda g, u: g.pay_bail(u),
    "jailcard": lambda g, u: g.use_jail_card(u), "bid100": lambda g, u: g.bid(u, 100),
    "bid500": lambda g, u: g.bid(u, 500), "bid1000": lambda g, u: g.bid(u, 1000),
    "pass": lambda g, u: g.pass_auction(u), "pay": lambda g, u: g.pay_debt(u),
    "bankrupt": lambda g, u: g.declare_bankruptcy(u), "tacc": lambda g, u: g.accept_trade(u),
    "trej": lambda g, u: g.reject_trade(u),
}


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def run(context, game, fn, expected_version: int | None = None, refresh: bool = True) -> str | None:
    """Run one engine action under the room lock. Returns an error message or None on success."""
    async with manager.lock(game.room_id):
        if manager.get(game.room_id) is not game:
            return "Ye game ab active nahi hai."
        if expected_version is not None and game.version != expected_version:
            return "⏳ Board update ho chuka hai — naye button dabao."
        try:
            fn(game)
        except GameError as e:
            return str(e)
        manager.save(game)
        await finalize(game)
    if refresh:
        await ui.refresh(context, game)
    return None


async def finalize(game) -> None:
    """If the game just ended: store stats once and free the memory."""
    if game.finished:
        manager.finish_game(game)
        manager.drop(game.room_id)


def allowed(user_id: int) -> bool:
    return manager.limiter.hit(user_id)


async def need_game(update, started: bool | None = None):
    """Find the game of this chat or tell the user there is none."""
    chat = update.effective_chat
    game = manager.by_chat(chat.id)
    if not game:
        await update.effective_message.reply_text("Koi active game nahi hai. /newgame se shuru karo 🎲")
        return None
    if started is True and not game.started:
        await update.effective_message.reply_text("Game abhi start nahi hua.")
        return None
    return game


def user_info(user) -> tuple[int, str, str]:
    return user.id, user.full_name[:40] or "Player", user.username or ""


def maintenance_blocked() -> bool:
    return MAINTENANCE["on"]
