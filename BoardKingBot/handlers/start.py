from telegram.constants import ParseMode

import messages
from game_manager import manager
from handlers.util import user_info


async def start(update, context):
    uid, name, username = user_info(update.effective_user)
    manager.upsert_user(uid, username, name)
    await update.effective_message.reply_text(
        "👑 <b>BoardKingBot me swagat hai!</b>\nGroup me /newgame bhejo aur 2-4 dost jodo. "
        "Akele test karne ke liye yahin /newgame karke /addbot dabao.\n\n" + messages.HELP,
        parse_mode=ParseMode.HTML)


async def help_cmd(update, context):
    await update.effective_message.reply_text(messages.HELP, parse_mode=ParseMode.HTML)


async def rules_cmd(update, context):
    from config import load_rules
    game = manager.by_chat(update.effective_chat.id)
    await update.effective_message.reply_text(messages.rules_text(game.rules if game else load_rules()),
                                              parse_mode=ParseMode.HTML)


async def profile_cmd(update, context):
    await update.effective_message.reply_text(
        messages.profile_text(manager.profile(update.effective_user.id)), parse_mode=ParseMode.HTML)


async def leaderboard_cmd(update, context):
    await update.effective_message.reply_text(messages.leaderboard_text(manager.leaderboard()),
                                              parse_mode=ParseMode.HTML)
