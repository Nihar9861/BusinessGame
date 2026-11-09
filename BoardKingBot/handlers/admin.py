"""Owner/admin commands. Every handler is restricted to ADMIN_IDS."""
import functools
from pathlib import Path

import config
import database
import models
from board import reload_board
from cards import load_cards
from game_manager import manager
from handlers.util import finalize
import ui


def admin_only(fn):
    @functools.wraps(fn)
    async def wrapper(update, context):
        if update.effective_user.id not in config.ADMIN_IDS:
            await update.effective_message.reply_text("⛔ Ye command sirf admin ke liye hai.")
            return
        await fn(update, context)
    return wrapper


@admin_only
async def admin(update, context):
    await update.effective_message.reply_text(
        "🛠 Admin commands\n/stats\n/activegames\n/stopgame BG-1234\n/maintenance on|off\n"
        "/reloadconfig\n/setrule <key> <value> (keys: " + ", ".join(config.DEFAULT_RULES) + ")\n/errors\n"
        f"\nAbhi rules: {config.load_rules()}")


@admin_only
async def stats(update, context):
    s = manager.stats()
    await update.effective_message.reply_text(
        f"📊 Users: {s['users']}\nFinished games: {s['finished']}\nActive games: {s['active']}\n"
        f"Maintenance: {'ON' if config.MAINTENANCE['on'] else 'OFF'}")


@admin_only
async def activegames(update, context):
    games = manager.active_games()
    if not games:
        await update.effective_message.reply_text("Koi active game nahi.")
        return
    lines = [f"{g.room_id} | chat {g.chat_id} | {g.state.value} | round {g.round} | "
             + ", ".join(p.name for p in g.players) for g in games]
    await update.effective_message.reply_text("\n".join(lines)[:4000])


@admin_only
async def stopgame(update, context):
    if not context.args:
        await update.effective_message.reply_text("Use: /stopgame BG-1234")
        return
    game = manager.get(context.args[0].upper())
    if not game:
        await update.effective_message.reply_text("Room nahi mila.")
        return
    async with manager.lock(game.room_id):
        game.stop("Admin ne game roka.")
        manager.save(game)
        await finalize(game)
    if game.started:
        await ui.refresh(context, game)
    await update.effective_message.reply_text(f"🛑 {game.room_id} band kiya.")


@admin_only
async def maintenance(update, context):
    if not context.args or context.args[0] not in ("on", "off"):
        await update.effective_message.reply_text("Use: /maintenance on|off")
        return
    config.MAINTENANCE["on"] = context.args[0] == "on"
    await update.effective_message.reply_text(f"Maintenance: {context.args[0].upper()}")


@admin_only
async def reloadconfig(update, context):
    try:
        reload_board()
        load_cards()
        await update.effective_message.reply_text(
            "✅ board.json, cards.json aur rules reload ho gaye. (Chalte hue games purane rules pe chalenge.)")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Reload fail: {e}")


@admin_only
async def setrule(update, context):
    if len(context.args) != 2:
        await update.effective_message.reply_text("Use: /setrule starting_cash 20000")
        return
    try:
        v = config.set_rule(context.args[0], context.args[1])
    except (KeyError, ValueError):
        await update.effective_message.reply_text("❌ Galat rule ya value. /admin me keys dekho.")
        return
    await update.effective_message.reply_text(f"✅ {context.args[0]} = {v} (naye games se lagu)")


@admin_only
async def errors(update, context):
    with database.session_scope() as s:
        rows = s.query(models.ErrorLog).order_by(models.ErrorLog.id.desc()).limit(5).all()
        text = "\n\n".join(f"{r.created_at:%d-%b %H:%M}\n{r.text[:500]}" for r in rows)
    await update.effective_message.reply_text(text or "Koi error log nahi 🎉")
