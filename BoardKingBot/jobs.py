"""Background tick (every 2 s): turn timeouts, bot players, trade expiry, lobby expiry."""
import logging
import time

import ui
from game_manager import manager
from handlers.util import finalize

log = logging.getLogger(__name__)


async def tick(context) -> None:
    for game in list(manager.games.values()):
        try:
            changed = False
            async with manager.lock(game.room_id):
                if manager.get(game.room_id) is not game:
                    continue
                if not game.started:
                    if time.time() - game.created_at > game.rules["lobby_timeout"]:
                        game.stop("Lobby expire ho gayi.")
                        manager.save(game)
                        manager.drop(game.room_id)
                        try:
                            await context.bot.edit_message_text(
                                chat_id=game.chat_id, message_id=game.message_id,
                                text=f"⌛ Room {game.room_id} expire ho gaya (koi start nahi hua).")
                        except Exception:
                            pass
                    continue
                changed = game.check_timeouts()
                if not changed:
                    changed = game.bot_step()           # one bot action per tick
                if changed:
                    manager.save(game)
                    await finalize(game)
            if changed:
                await ui.refresh(context, game)
        except Exception:
            log.exception("tick failed for %s", game.room_id)
            manager.log_error(f"tick {game.room_id}")
