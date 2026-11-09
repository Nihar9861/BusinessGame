"""Main game buttons: callback_data = g:<room>:<version>:<action>"""
import logging

import messages
import ui
from game_manager import manager
from handlers import property as property_handlers
from handlers import trading as trade_handlers
from handlers.util import ACTIONS, allowed, plain, run

log = logging.getLogger(__name__)


async def game_button(update, context):
    q = update.callback_query
    try:
        _, room, ver, act = q.data.split(":", 3)
        ver = int(ver)
    except ValueError:
        await q.answer("Galat button.")
        return
    uid = q.from_user.id
    game = manager.get(room)
    if not game or game.finished:
        await q.answer("Ye game ab active nahi hai.", show_alert=True)
        return
    if not q.message or q.message.chat_id != game.chat_id:            # group-id verification
        await q.answer("Ye button is chat ke liye nahi hai.", show_alert=True)
        return
    if not game.has(uid):                                              # user-id verification
        await q.answer("Aap is game ke player nahi ho. Agla game join karo!", show_alert=True)
        return
    if not allowed(uid):                                               # anti-spam
        await q.answer("Thoda dheere! ⏳")
        return
    if act == "bal":
        await q.answer(plain(messages.balance_text(game, game.player(uid))), show_alert=True)
        return
    if act == "props":
        text = messages.properties_text(game, game.player(uid))
        if await ui.send_private(context, uid, text):
            await q.answer("📩 Properties DM me bhej di.")
        else:
            await q.answer(plain(text)[:190], show_alert=True)
        return
    if act == "manage":
        await q.answer()
        await property_handlers.open_menu(context, game, uid, "home")
        return
    if act == "trade":
        err = await trade_handlers.start_trade(context, game, uid)
        await q.answer(err or "", show_alert=bool(err))
        return
    fn = ACTIONS.get(act)
    if not fn:
        await q.answer("Unknown action.")
        return
    err = await run(context, game, lambda g: fn(g, uid), expected_version=ver)
    await q.answer(err or "", show_alert=False)
