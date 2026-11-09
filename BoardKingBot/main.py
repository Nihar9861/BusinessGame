"""BoardKingBot entry point:  python main.py"""
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import config
import database
import jobs
import ui
from game_manager import manager
from handlers import admin, gameplay, lobby, property as prop, start, trading
from handlers.callbacks import game_button

log = logging.getLogger("boardking")

COMMANDS = [
    ("newgame", "Naya room banao"), ("join", "Room join karo"), ("leave", "Room chhodo"),
    ("startgame", "Game shuru karo (host)"), ("addbot", "Bot player jodo (host)"), ("roll", "Dice roll karo"),
    ("buy", "Property kharido"), ("skip", "Property skip (auction)"), ("balance", "Wallet dekho"),
    ("properties", "Meri properties"), ("players", "Players list"), ("status", "Board dobara bhejo"),
    ("trade", "Trade shuru karo"), ("auction", "Auction status"), ("mortgage", "Mortgage karo"),
    ("unmortgage", "Unmortgage karo"), ("build", "Ghar/hotel banao"), ("sell", "Property becho"),
    ("jail", "Jail info"), ("history", "Transaction history"), ("leaderboard", "Rankings"),
    ("profile", "Meri stats"), ("rules", "Rules"), ("endgame", "Game khatam (host)"), ("help", "Help"),
]


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        fh = RotatingFileHandler(config.LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    logging.getLogger("httpx").setLevel(logging.WARNING)      # httpx logs the bot token in URLs


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    log.error("Unhandled error: %s", text)
    manager.log_error(text)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
    restored = manager.load_all()
    log.info("Restored %d unfinished game(s)", restored)
    for game in manager.active_games():
        try:
            if game.started:
                await ui.refresh(_Ctx(app), game)
        except Exception:
            log.exception("could not refresh restored game %s", game.room_id)


class _Ctx:
    """Tiny stand-in for CallbackContext (ui.* only needs `.bot`)."""
    def __init__(self, app):
        self.bot = app.bot


def build_app(token: str | None = None) -> Application:
    app = Application.builder().token(token or config.BOT_TOKEN).post_init(post_init).build()
    h = app.add_handler
    h(CommandHandler("start", start.start))
    h(CommandHandler("help", start.help_cmd))
    h(CommandHandler("rules", start.rules_cmd))
    h(CommandHandler("profile", start.profile_cmd))
    h(CommandHandler("leaderboard", start.leaderboard_cmd))
    h(CommandHandler("newgame", lobby.newgame))
    h(CommandHandler("join", lobby.join))
    h(CommandHandler("leave", lobby.leave))
    h(CommandHandler("startgame", lobby.startgame))
    h(CommandHandler("addbot", lobby.addbot))
    h(CommandHandler("endgame", lobby.endgame))
    for name in ("roll", "buy", "skip"):
        h(CommandHandler(name, gameplay.action_command(name)))
    h(CommandHandler("balance", gameplay.balance))
    h(CommandHandler("properties", gameplay.properties_cmd))
    h(CommandHandler("players", gameplay.players))
    h(CommandHandler("status", gameplay.status))
    h(CommandHandler("auction", gameplay.auction_cmd))
    h(CommandHandler("jail", gameplay.jail_cmd))
    h(CommandHandler("history", gameplay.history))
    h(CommandHandler("trade", trading.trade_command))
    h(CommandHandler("build", prop.menu_command("build")))
    h(CommandHandler("mortgage", prop.menu_command("mort")))
    h(CommandHandler("unmortgage", prop.menu_command("unmort")))
    h(CommandHandler("sell", prop.menu_command("sellp")))
    for name in ("admin", "stats", "activegames", "stopgame", "maintenance", "reloadconfig", "setrule", "errors"):
        h(CommandHandler(name, getattr(admin, name)))
    h(CallbackQueryHandler(game_button, pattern=r"^g:"))
    h(CallbackQueryHandler(lobby.lobby_button, pattern=r"^l:"))
    h(CallbackQueryHandler(prop.menu_button, pattern=r"^m:"))
    h(CallbackQueryHandler(trading.trade_button, pattern=r"^t:"))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(jobs.tick, interval=2, first=5)
    return app


def main() -> None:
    setup_logging()
    if not config.BOT_TOKEN:
        sys.exit("BOT_TOKEN missing. Copy .env.example to .env and put your BotFather token in it.")
    database.init_db()
    app = build_app()
    if config.WEBHOOK_URL:
        log.info("Starting in WEBHOOK mode on port %s", config.PORT)
        app.run_webhook(listen="0.0.0.0", port=config.PORT, url_path=config.BOT_TOKEN,
                        webhook_url=f"{config.WEBHOOK_URL.rstrip('/')}/{config.BOT_TOKEN}",
                        secret_token=config.WEBHOOK_SECRET or None, allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=False)
    else:
        log.info("Starting in POLLING mode")
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
