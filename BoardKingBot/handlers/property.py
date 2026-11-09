"""Property management menu: /build /mortgage /unmortgage /sell (+ the Manage button)."""
from telegram.constants import ParseMode

import keyboards
import ui
from errors import GameError
from game_manager import manager
from handlers.util import allowed, need_game, run

HTML = ParseMode.HTML
KIND_ACTION = {
    "build": lambda g, u, t: g.build(u, t), "sellh": lambda g, u, t: g.sell_house(u, t),
    "mort": lambda g, u, t: g.mortgage(u, t), "unmort": lambda g, u, t: g.unmortgage(u, t),
    "sellp": lambda g, u, t: g.sell_property(u, t),
}


async def open_menu(context, game, uid: int, kind: str = "home") -> None:
    if kind == "home":
        await context.bot.send_message(game.chat_id, "🔧 <b>Property Manager</b> (sirf aap use kar sakte ho)",
                                       parse_mode=HTML, reply_markup=keyboards.manage_home_kb(game, uid))
    else:
        p = game.player(uid)
        await context.bot.send_message(game.chat_id, f"<b>{keyboards.MENU_TITLES[kind]}</b>", parse_mode=HTML,
                                       reply_markup=keyboards.menu_list_kb(game, p, kind))


def menu_command(kind: str):
    async def handler(update, context):
        game = await need_game(update, started=True)
        if not game or not allowed(update.effective_user.id):
            return
        if not game.has(update.effective_user.id):
            await update.effective_message.reply_text("⚠️ Aap is game ke player nahi ho.")
            return
        await open_menu(context, game, update.effective_user.id, kind)
    return handler


async def menu_button(update, context):
    q = update.callback_query
    parts = q.data.split(":")                 # m:<room>:<uid>:<kind>[:<tile>]
    room, owner, kind = parts[1], int(parts[2]), parts[3]
    uid = q.from_user.id
    game = manager.get(room)
    if not game or game.finished:
        await q.answer("Ye game ab active nahi hai.", show_alert=True)
        return
    if uid != owner:
        await q.answer("Ye menu kisi aur ka hai. /build ya Manage dabao.", show_alert=True)
        return
    if q.message.chat_id != game.chat_id or not game.has(uid):
        await q.answer("Not allowed.", show_alert=True)
        return
    if not allowed(uid):
        await q.answer("Thoda dheere! ⏳")
        return
    if kind == "close":
        await q.answer()
        await q.message.delete()
        return
    if kind == "home":
        await q.edit_message_text("🔧 <b>Property Manager</b>", parse_mode=HTML,
                                  reply_markup=keyboards.manage_home_kb(game, uid))
        await q.answer()
        return
    if len(parts) == 5:                       # a tile was picked -> perform the action
        tile = int(parts[4])
        err = await run(context, game, lambda g: KIND_ACTION[kind](g, uid, tile))
        await q.answer(err or "✅ Done", show_alert=bool(err))
        if manager.get(room) is not game:     # game ended
            return
    else:
        await q.answer()
    p = game.player(uid)
    try:
        await q.edit_message_text(f"<b>{keyboards.MENU_TITLES[kind]}</b>", parse_mode=HTML,
                                  reply_markup=keyboards.menu_list_kb(game, p, kind))
    except Exception:
        pass                                   # "message not modified" is harmless
