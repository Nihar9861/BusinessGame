"""/trade: a step-by-step trade builder (dena / lena / cash) and offer sending."""
from telegram.constants import ParseMode

import keyboards
import messages
from errors import GameError
from game_manager import manager
from handlers.util import allowed, need_game, run

HTML = ParseMode.HTML
DRAFTS: dict[tuple[str, int], dict] = {}        # (room, uid) -> trade draft (in memory only)


async def start_trade(context, game, uid: int) -> str | None:
    others = [p for p in game.active_players if p.id != uid and not p.is_bot]
    if not game.started or game.finished:
        return "Game abhi active nahi hai."
    if not others:
        return "Trade ke liye koi human opponent nahi hai (bots trade nahi karte)."
    if game.pending_trade:
        return "Ek trade offer pehle se pending hai."
    draft = {"to": others[0].id if len(others) == 1 else None, "give": [], "get": [], "cash": 0, "view": "give"}
    DRAFTS[(game.room_id, uid)] = draft
    if draft["to"] is None:
        await context.bot.send_message(game.chat_id, "🤝 <b>Trade</b> — kiske saath?", parse_mode=HTML,
                                       reply_markup=keyboards.trade_pick_player_kb(game, uid))
    else:
        await context.bot.send_message(game.chat_id, keyboards.trade_text(game, uid, draft), parse_mode=HTML,
                                       reply_markup=keyboards.trade_builder_kb(game, uid, draft))
    return None


async def trade_command(update, context):
    game = await need_game(update, started=True)
    if not game or not allowed(update.effective_user.id):
        return
    if not game.has(update.effective_user.id):
        await update.effective_message.reply_text("⚠️ Aap is game ke player nahi ho.")
        return
    err = await start_trade(context, game, update.effective_user.id)
    if err:
        await update.effective_message.reply_text("⚠️ " + err)


async def trade_button(update, context):
    q = update.callback_query
    parts = q.data.split(":")                  # t:<room>:<uid>:<action>[:<arg>]
    room, owner, act = parts[1], int(parts[2]), parts[3]
    arg = parts[4] if len(parts) > 4 else None
    uid = q.from_user.id
    game = manager.get(room)
    if not game or game.finished:
        await q.answer("Ye game ab active nahi hai.", show_alert=True)
        return
    if uid != owner:
        await q.answer("Ye aapka trade nahi hai.", show_alert=True)
        return
    if q.message.chat_id != game.chat_id or not game.has(uid):
        await q.answer("Not allowed.", show_alert=True)
        return
    if not allowed(uid):
        await q.answer("Thoda dheere! ⏳")
        return
    draft = DRAFTS.get((room, uid))
    if act == "cancel":
        DRAFTS.pop((room, uid), None)
        await q.answer("Cancel.")
        await q.message.delete()
        return
    if not draft:
        await q.answer("Ye trade form purana hai. /trade se naya banao.", show_alert=True)
        return
    me = game.player(uid)
    if act == "to":
        draft["to"] = int(arg)
    elif act == "view":
        draft["view"] = arg
    elif act in ("tg", "tr"):
        key, tid = ("give", int(arg)) if act == "tg" else ("get", int(arg))
        draft[key] = [t for t in draft[key] if t != tid] if tid in draft[key] else draft[key] + [tid]
    elif act == "cash":
        new = 0 if arg == "0" else draft["cash"] + int(arg)
        other = game.player(draft["to"]) if draft["to"] is not None else me
        draft["cash"] = max(-other.cash, min(me.cash, new))   # +ve: I pay, -ve: I receive
    elif act == "send":
        if draft["to"] is None:
            await q.answer("Pehle player chuno.", show_alert=True)
            return
        d = dict(draft)
        err = await run(context, game, lambda g: g.propose_trade(uid, d["to"], d["give"], d["get"], d["cash"]))
        if err:
            await q.answer(err, show_alert=True)
            return
        DRAFTS.pop((room, uid), None)
        await q.answer("📤 Offer bhej diya!")
        await q.message.delete()
        return
    await q.answer()
    if draft["to"] is None:
        return
    try:
        await q.edit_message_text(keyboards.trade_text(game, uid, draft), parse_mode=HTML,
                                  reply_markup=keyboards.trade_builder_kb(game, uid, draft))
    except Exception:
        pass
