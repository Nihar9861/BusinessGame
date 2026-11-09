"""Gameplay slash commands. Most of them just call the same engine actions as the buttons."""
from telegram.constants import ParseMode

import messages
import ui
from game_manager import manager
from handlers.util import ACTIONS, allowed, need_game, plain, run

HTML = ParseMode.HTML


def action_command(name: str):
    async def handler(update, context):
        game = await need_game(update, started=True)
        if not game:
            return
        uid = update.effective_user.id
        if not allowed(uid):
            return
        if not game.has(uid):
            await update.effective_message.reply_text("⚠️ Aap is game ke player nahi ho.")
            return
        err = await run(context, game, lambda g: ACTIONS[name](g, uid))
        if err:
            await update.effective_message.reply_text("⚠️ " + err)
    return handler


async def _info(update, text_fn):
    game = await need_game(update)
    if not game:
        return
    await update.effective_message.reply_text(text_fn(game, update.effective_user.id), parse_mode=HTML)


async def balance(update, context):
    game = await need_game(update, started=True)
    if game and game.has(update.effective_user.id):
        p = game.player(update.effective_user.id)
        await update.effective_message.reply_text(messages.balance_text(game, p))


async def properties_cmd(update, context):
    game = await need_game(update, started=True)
    if not game or not game.has(update.effective_user.id):
        return
    text = messages.properties_text(game, game.player(update.effective_user.id))
    if not await ui.send_private(context, update.effective_user.id, text):   # DM first (private)
        await update.effective_message.reply_text(text, parse_mode=HTML)


async def players(update, context):
    await _info(update, lambda g, u: messages.players_text(g) if g.started else messages.lobby_text(g))


async def status(update, context):
    """Also re-sends the board message at the bottom of the chat (handy after reconnecting)."""
    game = await need_game(update)
    if not game:
        return
    if game.started:
        async with manager.lock(game.room_id):
            await ui.send_board(context, game)
            manager.save(game)
    else:
        await update.effective_message.reply_text(messages.lobby_text(game), parse_mode=HTML)


async def auction_cmd(update, context):
    await _info(update, lambda g, u: messages.auction_text(g))


async def jail_cmd(update, context):
    game = await need_game(update, started=True)
    if game and game.has(update.effective_user.id):
        await update.effective_message.reply_text(
            messages.jail_text(game, game.player(update.effective_user.id)))


async def history(update, context):
    await _info(update, lambda g, u: messages.history_text(g))
