"""Keeps all live games in memory, saves them to the database, restores them after a restart,
and provides per-room locks (no two actions can touch the same game at the same time)."""
import asyncio
import json
import logging
import random
import string
import time
from collections import defaultdict, deque

import database
import models
from game_engine import Game
from states import State

log = logging.getLogger(__name__)


class RateLimiter:
    """Anti-spam: at most `limit` actions per `window` seconds per user."""
    def __init__(self, limit: int = 6, window: float = 4.0):
        self.limit, self.window = limit, window
        self.hits: dict[int, deque] = defaultdict(deque)

    def hit(self, uid: int, now: float | None = None) -> bool:
        """Return True if the action is allowed."""
        now = now or time.time()
        q = self.hits[uid]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


class GameManager:
    def __init__(self):
        self.games: dict[str, Game] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.limiter = RateLimiter()

    # ---- lookup
    def by_chat(self, chat_id: int) -> Game | None:
        for g in self.games.values():
            if g.chat_id == chat_id and not g.finished:
                return g
        return None

    def get(self, room_id: str) -> Game | None:
        return self.games.get(room_id)

    def lock(self, room_id: str) -> asyncio.Lock:
        return self._locks.setdefault(room_id, asyncio.Lock())

    def active_games(self) -> list[Game]:
        return [g for g in self.games.values() if not g.finished]

    def new_room_id(self) -> str:
        while True:
            rid = "BG-" + "".join(random.choices(string.digits, k=4))
            if rid not in self.games:
                return rid

    # ---- create / remove
    def create(self, chat_id: int, host_id: int, rules: dict | None = None) -> Game:
        g = Game(self.new_room_id(), chat_id, host_id, rules)
        self.games[g.room_id] = g
        return g

    def drop(self, room_id: str) -> None:
        self.games.pop(room_id, None)
        self._locks.pop(room_id, None)

    # ---- persistence
    def save(self, g: Game) -> None:
        """Write the whole game (snapshot + player/property rows + new transactions) in ONE transaction."""
        status = "LOBBY" if g.state == State.WAITING_FOR_PLAYERS else ("FINISHED" if g.finished else "ACTIVE")
        with database.session_scope() as s:
            row = s.get(models.GameRoom, g.room_id)
            if row is None:
                row = models.GameRoom(room_id=g.room_id, chat_id=g.chat_id, host_id=g.host_id)
                s.add(row)
                s.flush()
            row.host_id, row.status, row.version = g.host_id, status, g.version
            row.state_json = json.dumps(g.to_dict())
            s.query(models.PlayerRow).filter_by(room_id=g.room_id).delete()
            s.query(models.PropertyRow).filter_by(room_id=g.room_id).delete()
            for p in g.players:
                s.add(models.PlayerRow(room_id=g.room_id, user_id=p.id, name=p.name, cash=p.cash,
                                       position=p.pos, in_jail=p.in_jail, bankrupt=p.bankrupt, rank=p.rank))
            for tid, owner in g.tile_owner.items():
                s.add(models.PropertyRow(room_id=g.room_id, tile_id=tid, owner_id=owner,
                                         houses=g.houses.get(tid, 0), mortgaged=tid in g.mortgaged))
            for tx in g.pending_tx:
                s.add(models.TransactionRow(room_id=g.room_id, ts=tx["ts"], from_id=tx["from"],
                                            to_id=tx["to"], amount=tx["amount"], reason=tx["reason"][:128]))
            g.pending_tx.clear()

    def load_all(self) -> int:
        """Restore unfinished games after a restart."""
        n = 0
        with database.session_scope() as s:
            rows = s.query(models.GameRoom).filter(models.GameRoom.status.in_(["LOBBY", "ACTIVE"])).all()
            for row in rows:
                try:
                    g = Game.from_dict(json.loads(row.state_json))
                    self.games[g.room_id] = g
                    n += 1
                except Exception:
                    log.exception("Could not restore game %s", row.room_id)
        return n

    # ---- users and stats
    def upsert_user(self, uid: int, username: str, name: str) -> None:
        if uid < 0:
            return
        with database.session_scope() as s:
            u = s.get(models.User, uid)
            if u is None:
                s.add(models.User(id=uid, username=username or "", display_name=name))
            else:
                u.username, u.display_name = username or "", name

    def finish_game(self, g: Game) -> None:
        """Record stats exactly once per game (GameHistory.room_id is unique)."""
        if not g.played:                     # lobby that never started: nothing to record
            return
        with database.session_scope() as s:
            if s.query(models.GameHistory).filter_by(room_id=g.room_id).first():
                return
            from economy import net_worth
            ranking = sorted(g.players, key=lambda p: (p.rank or 99))
            summary = "; ".join(f"{p.rank or '-'}. {p.name} ({net_worth(g, p)})" for p in ranking)
            s.add(models.GameHistory(room_id=g.room_id, chat_id=g.chat_id, winner_id=g.winner_id,
                                     rounds=g.round, summary=summary))
            for p in g.players:
                if p.is_bot or g.winner_id is None:      # games stopped by an admin/host give no stats
                    continue
                u = s.get(models.User, p.id)
                if u is None:
                    u = models.User(id=p.id, username=p.username, display_name=p.name)
                    s.add(u)
                    s.flush()
                u.games_played = (u.games_played or 0) + 1
                if p.id == g.winner_id:
                    u.games_won = (u.games_won or 0) + 1
                    u.total_earnings = (u.total_earnings or 0) + max(0, net_worth(g, p) - g.rules["starting_cash"])
                else:
                    u.games_lost = (u.games_lost or 0) + 1
                if p.bankrupt:
                    u.bankruptcies = (u.bankruptcies or 0) + 1

    def leaderboard(self, limit: int = 10) -> list:
        with database.session_scope() as s:
            rows = s.query(models.User).filter(models.User.games_played > 0) \
                .order_by(models.User.games_won.desc(), models.User.total_earnings.desc()).limit(limit).all()
            return [(u.display_name, u.games_played, u.games_won, u.win_percentage, u.total_earnings) for u in rows]

    def profile(self, uid: int):
        with database.session_scope() as s:
            return s.get(models.User, uid)

    def stats(self) -> dict:
        with database.session_scope() as s:
            return {"users": s.query(models.User).count(),
                    "finished": s.query(models.GameHistory).count(),
                    "active": len(self.active_games())}

    def log_error(self, text: str) -> None:
        try:
            with database.session_scope() as s:
                s.add(models.ErrorLog(text=text[:3000]))
        except Exception:
            log.exception("could not store error log")


manager = GameManager()
