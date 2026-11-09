"""/newgame, /join, /leave, /startgame, /addbot, /endgame and the lobby buttons."""
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.constants import ParseMode

import messages
import ui
from config import MAINTENANCE, PRESETS, load_rules
from errors import GameError
from game_manager import manager
from handlers.util import allowed, finalize, need_game, plain, run, user_info


async def newgame(update, context):
    chat, user = update.effective_chat, update.effective_user
    if MAINTENANCE["on"]:
        await update.effective_message.reply_text(messages.maintenance_text())
        return
    existing = manager.by_chat(chat.id)
    if existing:
        await update.effective_message.reply_text(f"Is chat me pehle se room chal raha hai: {existing.room_id}")
        return
    mode = (context.args[0].lower() if context.args else "classic")
    if mode not in PRESETS:
        mode = "classic"
    uid, name, username = user_info(user)
    manager.upsert_user(uid, username, name)
    game = manager.create(chat.id, uid, {**load_rules(), **PRESETS[mode]})
    game.mode = mode
    async with manager.lock(game.room_id):
        game.add_player(uid, name, username)
        await ui.send_lobby(context, game)
        manager.save(game)


async def _lobby_action(context, game, fn, uid):
    async with manager.lock(game.room_id):
        if manager.get(game.room_id) is not game:
            return "Ye room ab active nahi hai."
        try:
            fn(game)
        except GameError as e:
            return str(e)
        manager.save(game)
    if not game.started:
        await ui.refresh_lobby(context, game)
    return None


async def join(update, context):
    game = await need_game(update)
    if not game:
        return
    uid, name, username = user_info(update.effective_user)
    if not allowed(uid):
        return
    manager.upsert_user(uid, username, name)
    err = await _lobby_action(context, game, lambda g: g.add_player(uid, name, username), uid)
    if err:
        await update.effective_message.reply_text("⚠️ " + err)


async def leave(update, context):
    game = await need_game(update)
    if not game:
        return
    uid = update.effective_user.id
    if game.started:
        err = await run(context, game, lambda g: g.leave(uid))
    else:
        err = await _lobby_action(context, game, lambda g: g.leave(uid), uid)
        async with manager.lock(game.room_id):
            if not game.players:                    # last player left: close the room
                game.stop("Lobby band (koi player nahi bacha)")
                manager.save(game)
                manager.drop(game.room_id)
    if err:
        await update.effective_message.reply_text("⚠️ " + err)


async def addbot(update, context):
    game = await need_game(update)
    if not game:
        return
    uid = update.effective_user.id
    err = await _lobby_action(context, game, lambda g: g.add_bot(uid), uid)
    if err:
        await update.effective_message.reply_text("⚠️ " + err)


async def _start(context, game, uid):
    old_message = game.message_id
    err = await _lobby_action(context, game, lambda g: g.start(uid), uid)
    if err:
        return err
    async with manager.lock(game.room_id):
        game.message_id = None
        await ui.send_board(context, game)
        manager.save(game)
    try:
        await context.bot.delete_message(game.chat_id, old_message)
    except Exception:
        pass
    return None


async def startgame(update, context):
    game = await need_game(update)
    if not game:
        return
    err = await _start(context, game, update.effective_user.id)
    if err:
        await update.effective_message.reply_text("⚠️ " + err)


async def endgame(update, context):
    game = await need_game(update)
    if not game:
        return
    if update.effective_user.id != game.host_id:
        await update.effective_message.reply_text("⚠️ Sirf host game khatam kar sakta hai.")
        return
    await update.effective_message.reply_text(
        f"Room {game.room_id} khatam karna hai? Ye wapas nahi hoga.",
        reply_markup=M([[B("⚠️ Haan, end karo", callback_data=f"l:{game.room_id}:endyes"),
                         B("Nahi", callback_data=f"l:{game.room_id}:endno")]]))


async def lobby_button(update, context):
    q = update.callback_query
    _, room, act = q.data.split(":")
    uid, name, username = user_info(q.from_user)
    game = manager.get(room)
    if not game or game.finished:
        await q.answer("Ye room ab active nahi hai.", show_alert=True)
        return
    if q.message and q.message.chat_id != game.chat_id:
        await q.answer("Galat chat.", show_alert=True)
        return
    if not allowed(uid):
        await q.answer("Thoda dheere! ⏳")
        return
    if act == "list":
        text = plain(messages.lobby_text(game))
        await q.answer(text[:190], show_alert=True)
        return
    if act == "endno":
        await q.answer("Theek hai.")
        await q.message.delete()
        return
    if act == "endyes":
        if uid != game.host_id:
            await q.answer("Sirf host.", show_alert=True)
            return
        async with manager.lock(room):
            game.stop("Host ne game khatam kar diya.")
            manager.save(game)
            await finalize(game)
        if game.started:
            await ui.refresh(context, game)
        await q.answer("Game khatam.")
        try:
            await q.message.delete()
        except Exception:
            pass
        return
    if game.started and act != "start":
        await q.answer("Game shuru ho chuka hai.", show_alert=True)
        return
    manager.upsert_user(uid, username, name)
    if act == "join":
        err = await _lobby_action(context, game, lambda g: g.add_player(uid, name, username), uid)
    elif act == "leave":
        err = await _lobby_action(context, game, lambda g: g.leave(uid), uid)
        if not err and not game.players:
            async with manager.lock(room):
                game.stop("Lobby band")
                manager.save(game)
                manager.drop(room)
            await q.edit_message_text("🚪 Lobby band ho gayi (sab player chale gaye).")
    elif act == "bot":
        err = await _lobby_action(context, game, lambda g: g.add_bot(uid), uid)
    elif act == "start":
        if game.started:
            err = "Game pehle se chal raha hai."
        else:
            err = await _start(context, game, uid)
    else:
        err = "Unknown button."
    await q.answer(err or "✅", show_alert=bool(err))
