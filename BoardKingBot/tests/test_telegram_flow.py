"""End-to-end test of the Telegram handlers against a fake Telegram API."""
import itertools

import pytest

import jobs
import main
from fake_telegram import FakeRequest
from game_manager import manager
from main import _Ctx

CHAT = USER = 500
_uid = itertools.count(1)


@pytest.fixture
async def env():
    app = main.build_app("123456:TEST")
    fake = FakeRequest()
    app.bot._request = (fake, fake)
    errors = []

    async def on_error(update, context):
        errors.append(context.error)
    app.error_handlers.clear()
    app.add_error_handler(on_error)
    await app.initialize()
    yield app, fake, errors
    await app.shutdown()


def cmd(app, text, user=USER, chat=CHAT):
    from telegram import Update
    name = text.split()[0]
    return Update.de_json({"update_id": next(_uid), "message": {
        "message_id": next(_uid), "date": 1, "chat": {"id": chat, "type": "private" if chat > 0 else "group"},
        "from": {"id": user, "is_bot": False, "first_name": f"User{user}"}, "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(name)}]}}, app.bot)


def press(app, data, user=USER, chat=CHAT):
    from telegram import Update
    return Update.de_json({"update_id": next(_uid), "callback_query": {
        "id": str(next(_uid)), "chat_instance": "x", "data": data,
        "from": {"id": user, "is_bot": False, "first_name": f"User{user}"},
        "message": {"message_id": 7, "date": 1, "chat": {"id": chat, "type": "private"}}}}, app.bot)


async def start_solo_game(app):
    await app.process_update(cmd(app, "/newgame"))
    game = manager.by_chat(CHAT)
    await app.process_update(cmd(app, "/addbot"))
    await app.process_update(cmd(app, "/startgame"))
    return game


async def test_full_flow_with_bot(env):
    app, fake, errors = env
    game = await start_solo_game(app)
    assert game and game.started and len(game.players) == 2
    assert fake.of("sendPhoto"), "board image must be sent"
    ctx = _Ctx(app)
    # play 300 steps: the human acts via buttons/commands, the bot via the tick job
    for _ in range(400):
        if game.finished:
            break
        manager.limiter.hits.clear()          # (the anti-spam limiter has its own test)
        if game.current.id == USER and game.state.value in ("WAITING_FOR_ROLL", "JAIL_DECISION"):
            await app.process_update(press(app, f"g:{game.room_id}:{game.version}:roll"))
        elif game.state.value == "PROPERTY_DECISION" and game.current.id == USER:
            await app.process_update(press(app, f"g:{game.room_id}:{game.version}:skip"))
        elif game.state.value == "AUCTION":
            await app.process_update(press(app, f"g:{game.room_id}:{game.version}:pass"))
            await jobs.tick(ctx)
        elif game.state.value == "PAYMENT" and game.current.id == USER:
            await app.process_update(press(app, f"g:{game.room_id}:{game.version}:bankrupt"))
        elif game.state.value == "DICE_ROLLED" and game.current.id == USER:
            await app.process_update(press(app, f"g:{game.room_id}:{game.version}:end"))
        else:
            await jobs.tick(ctx)
    assert not errors, errors
    assert game.finished or game.turn_count > 20, "game must really progress"
    assert fake.of("editMessageMedia"), "board must be edited in place, not re-sent every move"
    assert len(fake.of("sendPhoto")) < 10


async def test_stale_and_foreign_buttons(env):
    app, fake, errors = env
    game = await start_solo_game(app)
    v = game.version
    await app.process_update(press(app, f"g:{game.room_id}:{v - 1}:roll"))          # stale version
    assert game.version == v
    await app.process_update(press(app, f"g:{game.room_id}:{v}:roll", user=999))    # stranger
    assert game.version == v
    await app.process_update(press(app, f"g:{game.room_id}:{v}:roll", chat=-5))     # wrong chat
    assert game.version == v
    me_first = game.current.id == USER
    if me_first:
        await app.process_update(press(app, f"g:{game.room_id}:{v}:roll"))
        await app.process_update(press(app, f"g:{game.room_id}:{v}:roll"))          # duplicate click
        assert game.version == v + 1 or game.version == v + 2
    assert not errors, errors


async def test_menu_buttons_belong_to_owner(env):
    app, fake, errors = env
    game = await start_solo_game(app)
    await app.process_update(press(app, f"m:{game.room_id}:12345:build"))           # not my menu
    await app.process_update(press(app, f"m:{game.room_id}:{USER}:home"))
    await app.process_update(cmd(app, "/build"))
    await app.process_update(cmd(app, "/trade"))
    await app.process_update(cmd(app, "/balance"))
    await app.process_update(cmd(app, "/properties"))
    await app.process_update(cmd(app, "/history"))
    await app.process_update(cmd(app, "/jail"))
    await app.process_update(cmd(app, "/players"))
    await app.process_update(cmd(app, "/status"))
    await app.process_update(cmd(app, "/rules"))
    await app.process_update(cmd(app, "/leaderboard"))
    assert not errors, errors


async def test_admin_restricted(env):
    app, fake, errors = env
    await app.process_update(cmd(app, "/stats"))
    assert any("sirf admin" in str(p.get("text", "")) for p in fake.of("sendMessage"))
    import config
    config.ADMIN_IDS.add(USER)
    try:
        await app.process_update(cmd(app, "/stats"))
        await app.process_update(cmd(app, "/maintenance on"))
        await app.process_update(cmd(app, "/newgame"))
        assert manager.by_chat(CHAT) is None
        await app.process_update(cmd(app, "/maintenance off"))
        await app.process_update(cmd(app, "/newgame"))
        assert manager.by_chat(CHAT) is not None
        await app.process_update(cmd(app, "/activegames"))
        await app.process_update(cmd(app, "/reloadconfig"))
        await app.process_update(cmd(app, "/errors"))
    finally:
        config.ADMIN_IDS.discard(USER)
        config.MAINTENANCE["on"] = False
    assert not errors, errors


async def test_two_groups_play_independently(env):
    app, fake, errors = env
    await app.process_update(cmd(app, "/newgame", user=1, chat=-100))
    await app.process_update(cmd(app, "/newgame", user=2, chat=-200))
    g1, g2 = manager.by_chat(-100), manager.by_chat(-200)
    assert g1 and g2 and g1.room_id != g2.room_id
    await app.process_update(cmd(app, "/newgame", user=3, chat=-100))      # second room in same chat refused
    assert len(manager.active_games()) == 2
    assert not errors, errors
