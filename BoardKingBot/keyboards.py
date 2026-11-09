"""Inline keyboards. callback_data formats (max 64 bytes):
   g:<room>:<version>:<action>   main game buttons (version blocks stale/duplicate clicks)
   m:<room>:<uid>:<kind>[:<tile>]   property management menu (only <uid> may press)
   t:<room>:<uid>:<action>[:<arg>]  trade builder (only <uid> may press)
   l:<room>:<action>             lobby"""
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import properties
from board import BOARD
from messages import esc, money
from states import State


def lobby_kb(game) -> M:
    r = game.room_id
    return M([[B("✅ Join Game", callback_data=f"l:{r}:join"), B("🚪 Leave Game", callback_data=f"l:{r}:leave")],
              [B("👥 Player List", callback_data=f"l:{r}:list"), B("🤖 Add Bot", callback_data=f"l:{r}:bot")],
              [B("▶️ Start Game", callback_data=f"l:{r}:start")]])


def game_kb(game) -> M | None:
    if game.finished:
        return None
    r, v = game.room_id, game.version

    def g(label, act):
        return B(label, callback_data=f"g:{r}:{v}:{act}")

    rows = []
    st = game.state
    if st == State.WAITING_FOR_ROLL:
        rows.append([g("🎲 ROLL DICE", "roll")])
    elif st == State.JAIL_DECISION:
        rows.append([g("🎲 Roll (doubles)", "roll"), g(f"💵 Bail {money(game.rules['bail'])}", "bail")])
        if game.current.jail_cards:
            rows.append([g("🃏 Use Jail Card", "jailcard")])
    elif st == State.PROPERTY_DECISION:
        rows.append([g("🛒 BUY PROPERTY", "buy"), g("⏭ SKIP", "skip")])
    elif st == State.AUCTION:
        rows.append([g("+100", "bid100"), g("+500", "bid500"), g("+1000", "bid1000")])
        rows.append([g("🚫 Pass", "pass")])
    elif st == State.PAYMENT:
        rows.append([g("💵 Pay Now", "pay"), g("☠️ Declare Bankruptcy", "bankrupt")])
        rows.append([g("🔧 Mortgage / Sell", "manage")])
    elif st == State.DICE_ROLLED:
        rows.append([g("⏹ END TURN", "end")])
    if game.pending_trade:
        rows.append([g("✅ Accept Trade", "tacc"), g("❌ Reject", "trej")])
    if st != State.PAYMENT:
        rows.append([g("💰 Balance", "bal"), g("🏠 My Properties", "props")])
        if st != State.AUCTION:
            rows.append([g("🔧 Manage", "manage"), g("🤝 Trade", "trade")])
    return M(rows)


def manage_home_kb(game, uid: int) -> M:
    r = f"{game.room_id}:{uid}"
    return M([[B("🏗 Build", callback_data=f"m:{r}:build"), B("🏚 Sell house", callback_data=f"m:{r}:sellh")],
              [B("🏦 Mortgage", callback_data=f"m:{r}:mort"), B("💳 Unmortgage", callback_data=f"m:{r}:unmort")],
              [B("💸 Sell property", callback_data=f"m:{r}:sellp"), B("✖ Close", callback_data=f"m:{r}:close")]])


MENU_TITLES = {"build": "🏗 Ghar/hotel banao", "sellh": "🏚 Ghar becho (50% refund)",
               "mort": "🏦 Mortgage (50% price)", "unmort": "💳 Unmortgage (+10%)", "sellp": "💸 Bank ko becho (50%)"}


def eligible_tiles(game, p, kind: str) -> list[tuple[int, str]]:
    out = []
    for tid in properties.owned_by(game, p.id):
        t = BOARD[tid]
        mort = tid in game.mortgaged
        h = game.houses.get(tid, 0)
        if kind == "build" and properties.can_build(game, p, tid) is None:
            out.append((tid, f"{t.name} ({h}→{h + 1}) -{money(t.house_cost)}"))
        elif kind == "sellh" and h > 0:
            out.append((tid, f"{t.name} (h{h}) +{money(t.house_cost // 2)}"))
        elif kind == "mort" and not mort and not properties.group_has_buildings(game, t):
            out.append((tid, f"{t.name} +{money(t.mortgage_value)}"))
        elif kind == "unmort" and mort:
            out.append((tid, f"{t.name} -{money(properties.unmortgage_cost(t))}"))
        elif kind == "sellp" and not mort and not properties.group_has_buildings(game, t):
            out.append((tid, f"{t.name} +{money(t.mortgage_value)}"))
    return out


def menu_list_kb(game, p, kind: str) -> M:
    r = f"{game.room_id}:{p.id}"
    rows = [[B(label[:40], callback_data=f"m:{r}:{kind}:{tid}")] for tid, label in eligible_tiles(game, p, kind)]
    rows.append([B("⬅ Back", callback_data=f"m:{r}:home"), B("✖ Close", callback_data=f"m:{r}:close")])
    return M(rows)


# ------------------------------------------------------------------ trade builder
CASH_STEPS = (100, 500, 1000)


def trade_pick_player_kb(game, uid: int) -> M:
    r = f"{game.room_id}:{uid}"
    rows = [[B(p.name[:30], callback_data=f"t:{r}:to:{p.id}")] for p in game.active_players
            if p.id != uid and not p.is_bot]
    rows.append([B("✖ Cancel", callback_data=f"t:{r}:cancel")])
    return M(rows)


def trade_builder_kb(game, uid: int, draft: dict) -> M:
    r, view = f"{game.room_id}:{uid}", draft["view"]
    tabs = [B(("• " if view == v else "") + label, callback_data=f"t:{r}:view:{v}")
            for v, label in (("give", "Dena"), ("get", "Lena"), ("cash", "Cash"))]
    rows = [tabs]
    if view in ("give", "get"):
        owner = uid if view == "give" else draft["to"]
        chosen = draft[view]
        for tid in properties.owned_by(game, owner):
            if properties.group_has_buildings(game, BOARD[tid]):
                continue
            mark = "✅ " if tid in chosen else ""
            rows.append([B(f"{mark}{BOARD[tid].name}", callback_data=f"t:{r}:{'tg' if view == 'give' else 'tr'}:{tid}")])
    else:
        rows.append([B(f"-{s}", callback_data=f"t:{r}:cash:{-s}") for s in CASH_STEPS])
        rows.append([B(f"+{s}", callback_data=f"t:{r}:cash:{s}") for s in CASH_STEPS])
        rows.append([B("Reset 0", callback_data=f"t:{r}:cash:0")])
    rows.append([B("📤 Send Offer", callback_data=f"t:{r}:send"), B("✖ Cancel", callback_data=f"t:{r}:cancel")])
    return M(rows)


def trade_text(game, uid: int, draft: dict) -> str:
    me, other = game.player(uid), game.player(draft["to"])
    give = ", ".join(BOARD[t].name for t in draft["give"]) or "—"
    get = ", ".join(BOARD[t].name for t in draft["get"]) or "—"
    c = draft["cash"]
    cash = f"Aap {money(c)} doge" if c > 0 else (f"Aap {money(-c)} loge" if c < 0 else "Cash nahi")
    return (f"🤝 <b>Trade: {esc(me.name)} ↔ {esc(other.name)}</b>\n\n"
            f"📤 Aap doge: {esc(give)}\n📥 Aap loge: {esc(get)}\n💵 {cash}\n\n"
            f"Tabs se properties/cash chuno, phir Send Offer dabao.")
