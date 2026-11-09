# 👑 BoardKingBot — Telegram Business Board Game

2–4 player property-trading game for Telegram groups. Image board (Pillow), auctions, trading,
mortgages, houses/hotels, jail, cards, bankruptcy, bot players, persistent games.

## 1. Local setup (beginner)
1. Install Python 3.11+ from python.org (tick "Add to PATH"). Install VS Code.
2. Open the `BoardKingBot` folder in VS Code → Terminal → New Terminal.
3. Commands (Windows):
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Mac/Linux: `source venv/bin/activate` and `cp .env.example .env`.
4. Telegram → **@BotFather** → `/newbot` → copy the token. In BotFather also: `/setprivacy` → your bot → **Disable**
   (so the bot can see group commands), and `/setjoingroups` → Enable.
5. Edit `.env`: put `BOT_TOKEN` and your Telegram id in `ADMIN_IDS` (get it from @userinfobot).
6. Run: `python main.py`

## 2. Test it alone
In a private chat with the bot: `/newgame` → `/addbot` → `/startgame` → press 🎲 ROLL DICE.
In a group: add the bot, send `/newgame`; friends press Join.

## 3. Run automated tests
`python -m pytest -q`

## 4. GitHub
```
git init
git add .
git commit -m "BoardKingBot"
git branch -M main
git remote add origin https://github.com/YOURNAME/BoardKingBot.git
git push -u origin main
```
`.env` is in `.gitignore` — never upload your token.

## 5. 24/7 hosting (computer can be off)
**Docker on any VPS** (Oracle Cloud Always-Free, Hetzner ~€4/mo, DigitalOcean):
```
git clone <your repo> && cd BoardKingBot
cp .env.example .env   # fill BOT_TOKEN, ADMIN_IDS
docker compose up -d --build
docker compose logs -f bot
```
This starts the bot + PostgreSQL and restarts automatically after reboot (`restart: always`).
**Railway / Render / Fly.io**: connect the GitHub repo, set env vars `BOT_TOKEN`, `ADMIN_IDS`,
`DATABASE_URL` (their PostgreSQL add-on). For hosts that sleep on the free plan, set `WEBHOOK_URL`
to your public https URL (webhook mode) — but free plans may still have limits; a small VPS is the most reliable.
Polling mode needs no public URL (default).

## 6. Backup & recovery
SQLite: copy `boardking.db`. PostgreSQL: `docker compose exec db pg_dump -U boardking boardking > backup.sql`
and restore with `psql ... < backup.sql`. Unfinished games are restored automatically when the bot restarts.

## Commands
Players: /newgame [quick] /join /leave /startgame /addbot /roll /buy /skip /balance /properties /players /status
/trade /auction /mortgage /unmortgage /build /sell /jail /history /leaderboard /profile /rules /endgame
Admin: /admin /stats /activegames /stopgame BG-1234 /maintenance on|off /reloadconfig /setrule key value /errors

## Customising
`data/board.json` (tiles, prices, rents, colours) and `data/cards.json` (cards); `/reloadconfig` applies them.
Rules: `config.py` DEFAULT_RULES or `/setrule`.

## Honest notes / limitations
- Tested: game engine, persistence, handlers against a *fake* Telegram API, image rendering. Not tested against live Telegram.
- Migrations are a small built-in versioned system (not Alembic).
- "Collect from every player" cards take only what a player can afford; bankrupt players' buildings are sold to the bank at half price.
- Trades are built in the group chat (not private chat); bots never accept trades.
- Run a single bot instance per token.
