"""Telegram I/O for the shared game message (board image + caption + buttons)."""
import asyncio
import logging

from telegram import InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter, TelegramError

import keyboards
import messages
from board_image import render_board

log = logging.getLogger(__name__)
HTML = ParseMode.HTML


async def _png(game) -> bytes:
    return await asyncio.to_thread(render_board, game)       # keep the event loop free


async def send_board(context, game) -> None:
    """Send a NEW board message and remember its id."""
    old = game.message_id
    msg = await context.bot.send_photo(chat_id=game.chat_id, photo=await _png(game),
                                       caption=messages.board_caption(game), parse_mode=HTML,
                                       reply_markup=keyboards.game_kb(game))
    game.message_id = msg.message_id
    if old:
        try:
            await context.bot.delete_message(game.chat_id, old)
        except TelegramError:
            pass


async def refresh(context, game) -> None:
    """Edit the board message in place; send a fresh one if editing is impossible."""
    if not game.message_id:
        await send_board(context, game)
        return
    try:
        media = InputMediaPhoto(media=await _png(game), caption=messages.board_caption(game), parse_mode=HTML)
        await context.bot.edit_message_media(chat_id=game.chat_id, message_id=game.message_id, media=media,
                                             reply_markup=keyboards.game_kb(game))
    except RetryAfter as e:
        log.warning("Telegram flood limit, skipping one edit (%s s)", e.retry_after)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        log.warning("edit failed (%s) -> sending a new board message", e)
        await send_board(context, game)
    except TelegramError as e:
        log.warning("edit failed: %s", e)


async def refresh_lobby(context, game) -> None:
    try:
        await context.bot.edit_message_text(chat_id=game.chat_id, message_id=game.message_id,
                                            text=messages.lobby_text(game), parse_mode=HTML,
                                            reply_markup=keyboards.lobby_kb(game))
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("lobby edit failed: %s", e)
    except TelegramError as e:
        log.warning("lobby edit failed: %s", e)


async def send_lobby(context, game) -> None:
    msg = await context.bot.send_message(chat_id=game.chat_id, text=messages.lobby_text(game),
                                         parse_mode=HTML, reply_markup=keyboards.lobby_kb(game))
    game.message_id = msg.message_id


async def send_private(context, uid: int, text: str) -> bool:
    """DM a user (works only if they pressed /start in private chat once)."""
    try:
        await context.bot.send_message(uid, text, parse_mode=HTML)
        return True
    except TelegramError:
        return False
