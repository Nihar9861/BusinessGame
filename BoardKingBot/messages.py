"""All player-facing text. HTML parse mode: every name goes through esc()."""
import html

from board import BOARD
from board_image import PLAYER_EMOJI
from config import MAINTENANCE
from economy import net_worth
from properties import owned_by, rent_due, unmortgage_cost
from states import State


def esc(s) -> str:
    return html.escape(str(s))


def money(n: int) -> str:
    return f"₹{n:,}"


def tag(game, p) -> str:
    return PLAYER_EMOJI[game.players.index(p) % 4]


HELP = """👑 <b>BoardKingBot — Business Board Game</b>

<b>Game shuru karo</b>
/newgame — room banao (group me, ya akele test ke liye private chat me)
/join /leave /startgame — lobby
/addbot — bot player jodo (host)

<b>Game me</b>
/roll /buy /skip — dice, kharidna, skip (skip = auction)
/balance /properties /players /status
/build /mortgage /unmortgage /sell — property management
/trade — player se trade
/auction /jail /history /leaderboard
/rules — rules, /endgame — game khatam (host)

Zyada tar kaam inline buttons se ho jata hai 🎮"""


def rules_text(rules: dict) -> str:
    return (f"📜 <b>Rules</b>\n"
            f"• Players: 2–4\n• Starting cash: {money(rules['starting_cash'])}\n"
            f"• START salary: {money(rules['salary'])}\n"
            f"• Doubles = extra turn, 3 doubles = jail\n"
            f"• Jail: doubles roll, bail {money(rules['bail'])} ya card; {rules['max_jail_turns']} fail = bail zaroori\n"
            f"• Property skip karo to auction hota hai\n"
            f"• Pura color-set = double rent; ghar barabar banate hain (max hotel)\n"
            f"• Mortgage = price ka 50%, unmortgage = +10%\n"
            f"• Cash kam pade to asset becho/mortgage karo, warna bankrupt\n"
            f"• Turn timer: {rules['turn_timeout']}s (3 baar miss = game se bahar)\n"
            + (f"• Round limit: {rules['max_rounds']} (phir sabse ameer jeetega)\n" if rules["max_rounds"] else "")
            + ("• Free Parking jackpot ON\n" if rules["free_parking_jackpot"] else ""))


def lobby_text(game) -> str:
    lines = [f"👑 <b>BOARDKING BUSINESS GAME</b>", f"Room ID: <code>{game.room_id}</code>"
             + (" ⚡ Quick" if game.mode == "quick" else ""), "", "<b>Players:</b>"]
    for i in range(4):
        if i < len(game.players):
            p = game.players[i]
            star = " 👑" if p.id == game.host_id else ""
            at = f" (@{esc(p.username)})" if p.username else ""
            lines.append(f"{i + 1}. {esc(p.name)}{at}{star}")
        else:
            lines.append(f"{i + 1}. Waiting...")
    lines += ["", f"💰 Starting cash: {money(game.rules['starting_cash'])}",
              "Kam se kam 2 players chahiye. Sirf host Start dabaa sakta hai."]
    return "\n".join(lines)


def prop_line(game, tid: int) -> str:
    t = BOARD[tid]
    h = game.houses.get(tid, 0)
    extra = " 🏨" if h == 5 else (" " + "🏠" * h if h else "")
    mort = " 🏦(mortgaged)" if tid in game.mortgaged else ""
    return f"• {esc(t.name)} [{t.group}]{extra}{mort}"


def board_caption(game) -> str:
    """Text under the board image (Telegram caption limit is 1024 characters)."""
    if game.finished:
        return final_text(game)
    cur = game.current
    t = BOARD[cur.pos]
    lines = [f"👑 <b>BOARDKINGBOT</b>  🎮 <code>{game.room_id}</code>",
             f"🎲 <b>Turn:</b> {tag(game, cur)} {esc(cur.name)}  (Round {game.round})",
             f"💰 {money(cur.cash)}   📍 {esc(t.name)}"
             + (f"   🎲 {game.dice[0]} + {game.dice[1]}" if game.dice else "")]
    st = game.state
    if st == State.PROPERTY_DECISION:
        pt = BOARD[game.pending_tile]
        lines.append(f"🏠 <b>{esc(pt.name)}</b> available — 💵 {money(pt.price)}")
    elif st == State.AUCTION:
        a = game.auction
        at = BOARD[a["tile"]]
        who = esc(game.player(a["bidder"]).name) if a["bidder"] is not None else "—"
        lines.append(f"🔨 <b>AUCTION: {esc(at.name)}</b> (price {money(at.price)})\n"
                     f"Highest: {money(a['high'])} by {who}   Min bid: {money(a['min_bid'])}")
    elif st == State.PAYMENT:
        d = game.debt
        lines.append(f"⚠️ <b>{esc(game.player(d['debtor']).name)}</b> ko {money(d['total'])} dena hai ({esc(d['reason'])}). "
                     f"Asset becho / mortgage karo ya bankrupt.")
    elif st == State.JAIL_DECISION:
        lines.append(f"🚔 {esc(cur.name)} jail me hai (turn {cur.jail_turns + 1}/{game.rules['max_jail_turns']}): roll, bail ya card.")
    if game.pending_trade:
        pt = game.pending_trade
        lines.append(f"🤝 Trade: {esc(game.player(pt['from']).name)} → {esc(game.player(pt['to']).name)} "
                     f"({len(pt['give'])} de, {len(pt['get'])} maange, cash {money(pt['cash'])})")
    lines.append("")
    for p in game.players:
        mark = "▶️" if p is cur else "  "
        lines.append(f"{mark}{tag(game, p)} {esc(p.name)} — " + ("💀 OUT" if p.bankrupt else money(p.cash)))
    if game.log:
        lines.append("")
        lines += [esc(x) for x in game.log[-3:]]
    text = "\n".join(lines)
    return text if len(text) <= 1000 else text[:996] + "…"


def final_text(game) -> str:
    lines = ["🏁 <b>GAME OVER</b>", f"Room <code>{game.room_id}</code> — {game.round} rounds", ""]
    for p in sorted(game.players, key=lambda x: x.rank or 99):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(p.rank, "▫️")
        lines.append(f"{medal} {esc(p.name)} — net worth {money(net_worth(game, p))}" + (" 💀" if p.bankrupt else ""))
    if game.winner_id is None:
        lines.append("\n(Game admin/host ne roka)")
    lines += [""] + [esc(x) for x in game.log[-2:]]
    return "\n".join(lines)[:1000]


def balance_text(game, p) -> str:
    return f"💰 {p.name}: {money(p.cash)} | Net worth {money(net_worth(game, p))}"


def properties_text(game, p) -> str:
    owned = owned_by(game, p.id)
    if not owned:
        return "🏠 Aapke paas abhi koi property nahi hai."
    lines = [f"🏠 <b>{esc(p.name)} ki properties</b> ({len(owned)})"]
    lines += [prop_line(game, t) + f" — rent {money(rent_due(game, BOARD[t], 7)) if t not in game.mortgaged else '0'}"
              for t in owned]
    return "\n".join(lines)


def players_text(game) -> str:
    lines = ["👥 <b>Players</b>"]
    for p in game.players:
        s = "💀 out" if p.bankrupt else f"{money(p.cash)} | 📍 {esc(BOARD[p.pos].name)}" + (" 🚔" if p.in_jail else "")
        lines.append(f"{tag(game, p)} {esc(p.name)} — {s} | 🏠 {len(owned_by(game, p.id))}")
    return "\n".join(lines)


def status_text(game) -> str:
    if not game.started:
        return lobby_text(game)
    return players_text(game) + f"\n\n⏱ State: {game.state.value}\n🎮 Round {game.round}\n▶️ Turn: {esc(game.current.name)}"


def history_text(game, limit: int = 12) -> str:
    if not game.tx:
        return "📒 Abhi koi transaction nahi hui."
    names = {p.id: p.name for p in game.players}
    lines = ["📒 <b>Last transactions</b>"]
    for tx in game.tx[-limit:]:
        a = esc(names.get(tx["from"], "Bank")) if tx["from"] is not None else "Bank"
        b = esc(names.get(tx["to"], "Bank")) if tx["to"] is not None else "Bank"
        lines.append(f"{a} → {b}: {money(tx['amount'])} ({esc(tx['reason'])})")
    return "\n".join(lines)


def jail_text(game, p) -> str:
    if not p.in_jail:
        return "🚔 Aap jail me nahi ho. Jail tile #10 (Jail), Go-To-Jail tile #30."
    return (f"🚔 Aap jail me ho (fail {p.jail_turns}/{game.rules['max_jail_turns']}).\n"
            f"Options: doubles roll karo, bail {money(game.rules['bail'])} do, ya card use karo (cards: {p.jail_cards}).")


def auction_text(game) -> str:
    a = game.auction
    if not a:
        return "🔨 Abhi koi auction nahi chal raha."
    t = BOARD[a["tile"]]
    who = esc(game.player(a["bidder"]).name) if a["bidder"] is not None else "koi nahi"
    passed = ", ".join(esc(game.player(i).name) for i in a["passed"]) or "—"
    return (f"🔨 <b>Auction: {esc(t.name)}</b>\nPrice {money(t.price)} | Min bid {money(a['min_bid'])}\n"
            f"Highest: {money(a['high'])} ({who})\nPass: {passed}")


def leaderboard_text(rows: list) -> str:
    if not rows:
        return "🏆 Abhi leaderboard khali hai. Pehla game jeeto!"
    lines = ["🏆 <b>Leaderboard</b>"]
    for i, (name, played, won, pct, earn) in enumerate(rows, 1):
        lines.append(f"{i}. {esc(name)} — {won}W/{played}G ({pct}%) | earnings {money(earn)}")
    return "\n".join(lines)


def profile_text(u) -> str:
    if not u:
        return "Abhi aapka koi game record nahi hai."
    return (f"👤 <b>{esc(u.display_name)}</b>\nGames: {u.games_played} | Won: {u.games_won} | Lost: {u.games_lost}\n"
            f"Win%: {u.win_percentage} | Bankruptcies: {u.bankruptcies}\nTotal earnings: {money(u.total_earnings)}")


def maintenance_text() -> str:
    return "🛠 Bot maintenance me hai. Thodi der baad try karo."
