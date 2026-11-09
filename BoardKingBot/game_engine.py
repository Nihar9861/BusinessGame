"""Core game: a pure-Python state machine (no Telegram code here, so it is easy to test).

Every public action validates the caller, mutates the state and bumps `version`.
Rule violations raise GameError (the message is shown to the player).
"""
import functools
import random
import time

import auction
import bankruptcy
import cards
import economy
import jail
import properties
import trading
from board import BOARD, BOARD_SIZE
from config import load_rules
from dice import roll_dice
from errors import GameError
from player import Player
from states import State

MIN_PLAYERS, MAX_PLAYERS = 2, 4
BLOCKED = (State.WAITING_FOR_PLAYERS, State.GAME_OVER)


def action(fn):
    """Mark a public method as a state-changing action (bumps version + resets the timer)."""
    @functools.wraps(fn)
    def wrapper(self, *a, **kw):
        result = fn(self, *a, **kw)
        self._touch()
        return result
    return wrapper


class Game:
    board = BOARD

    def __init__(self, room_id: str, chat_id: int, host_id: int, rules: dict | None = None,
                 rng: random.Random | None = None):
        self.room_id, self.chat_id, self.host_id = room_id, chat_id, host_id
        self.rules = dict(rules or load_rules())
        self.rng = rng or random.SystemRandom()
        self.roller = lambda: roll_dice(self.rng)
        self.players: list[Player] = []
        self.state = State.WAITING_FOR_PLAYERS
        self.turn = 0
        self.round = 1
        self.turn_count = 0
        self.tile_owner: dict[int, int] = {}
        self.houses: dict[int, int] = {}
        self.mortgaged: set[int] = set()
        self.dice: tuple | None = None
        self.doubles_count = 0
        self.extra_roll = False
        self.pending_tile: int | None = None
        self.debt: dict | None = None
        self.auction: dict | None = None
        self.pending_trade: dict | None = None
        self.decks: dict = {}
        self.card_history: list[str] = []
        self.pot = 0
        self.log: list[str] = []
        self.tx: list[dict] = []
        self.pending_tx: list[dict] = []     # not yet written to the database
        self.deadline = 0.0
        self.version = 0
        self.message_id: int | None = None
        self.created_at = time.time()
        self.winner_id: int | None = None
        self.mode = "classic"
        self.played = False                  # True once the game really started

    # ------------------------------------------------------------ helpers
    @property
    def current(self) -> Player:
        return self.players[self.turn]

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self.players if not p.bankrupt]

    def has(self, uid: int) -> bool:
        return any(p.id == uid for p in self.players)

    def player(self, uid: int) -> Player:
        for p in self.players:
            if p.id == uid:
                return p
        raise GameError("Aap is game me nahi ho.")

    def emit(self, text: str) -> None:
        self.log.append(text)
        del self.log[:-40]

    @property
    def started(self) -> bool:
        return self.state != State.WAITING_FOR_PLAYERS

    @property
    def finished(self) -> bool:
        return self.state == State.GAME_OVER

    def _touch(self) -> None:
        self.version += 1
        if self.state in BLOCKED:
            self.deadline = 0.0
        else:
            t = self.rules["auction_timeout"] if self.state == State.AUCTION else self.rules["turn_timeout"]
            self.deadline = time.time() + t

    # ------------------------------------------------------------ lobby
    @action
    def add_player(self, uid: int, name: str, username: str = "") -> Player:
        if self.started:
            raise GameError("Game shuru ho chuka hai, ab join nahi kar sakte.")
        if self.has(uid):
            raise GameError("Aap already join ho chuke ho.")
        if len(self.players) >= MAX_PLAYERS:
            raise GameError("Room full hai (max 4 players).")
        p = Player(id=uid, name=name, username=username, cash=self.rules["starting_cash"])
        self.players.append(p)
        self.emit(f"👋 {name} join hua.")
        return p

    @action
    def add_bot(self, uid: int) -> Player:
        if uid != self.host_id:
            raise GameError("Sirf host bot add kar sakta hai.")
        n = sum(1 for p in self.players if p.is_bot) + 1
        bot_id = -n
        while self.has(bot_id):
            n += 1
            bot_id = -n
        return self.add_player_raw(bot_id, f"🤖 Bot{n}")

    def add_player_raw(self, uid, name):
        if self.started:
            raise GameError("Game shuru ho chuka hai.")
        if len(self.players) >= MAX_PLAYERS:
            raise GameError("Room full hai (max 4 players).")
        p = Player(id=uid, name=name, cash=self.rules["starting_cash"])
        self.players.append(p)
        self.emit(f"🤖 {name} join hua.")
        return p

    @action
    def leave(self, uid: int) -> None:
        p = self.player(uid)
        if not self.started:
            self.players.remove(p)
            if uid == self.host_id:
                humans = [x for x in self.players if not x.is_bot]
                if humans:
                    self.host_id = humans[0].id
                    self.emit(f"👑 Naya host: {humans[0].name}")
            self.emit(f"🚪 {p.name} ne lobby chhodi.")
            return
        if self.finished or p.bankrupt:
            raise GameError("Aap already game se bahar ho.")
        self._eliminate(p, "ne game chhod diya")

    @action
    def start(self, uid: int) -> None:
        if self.started:
            raise GameError("Game pehle se chal raha hai.")
        if uid != self.host_id:
            raise GameError("Sirf host game start kar sakta hai.")
        if len(self.players) < MIN_PLAYERS:
            raise GameError("Kam se kam 2 players chahiye.")
        self.played = True
        self.rng.shuffle(self.players)
        cards.init_decks(self)
        self.turn, self.round, self.turn_count = 0, 1, 0
        self.state = State.WAITING_FOR_ROLL
        self.emit("🎮 Game shuru! Players ka order tay ho gaya.")
        self.emit(f"▶️ {self.current.name} ki turn")

    @action
    def stop(self, reason: str = "Game stopped") -> None:
        self.state = State.GAME_OVER
        self.winner_id = None
        self.auction = self.debt = self.pending_trade = None
        self.emit(f"🛑 {reason}")

    # ------------------------------------------------------------ guards
    def _require_current(self, uid: int) -> Player:
        if self.state in BLOCKED:
            raise GameError("Abhi koi game active nahi hai.")
        p = self.player(uid)
        if p.bankrupt:
            raise GameError("Aap game se bahar ho.")
        if self.current.id != uid:
            raise GameError("Ye aapki turn nahi hai.")
        p.afk = 0
        return p

    def _manager(self, uid: int) -> Player:
        if self.state in BLOCKED or self.state == State.AUCTION:
            raise GameError("Abhi ye action allowed nahi hai.")
        p = self.player(uid)
        if p.bankrupt:
            raise GameError("Aap game se bahar ho.")
        if self.state == State.PAYMENT and self.debt["debtor"] != uid:
            raise GameError("Abhi payment pending hai.")
        return p

    # ------------------------------------------------------------ dice + movement
    @action
    def roll(self, uid: int) -> None:
        p = self._require_current(uid)
        self._roll(p)

    def _roll(self, p: Player) -> None:
        if self.state == State.JAIL_DECISION:
            jail.roll_for_release(self, p)
            return
        if self.state != State.WAITING_FOR_ROLL:
            raise GameError("Abhi dice roll nahi kar sakte.")
        d1, d2 = self.roller()
        self.dice = (d1, d2)
        double = d1 == d2
        self.doubles_count = self.doubles_count + 1 if double else 0
        self.emit(f"🎲 {p.name} ne {d1}+{d2} roll kiya" + (" (doubles!)" if double else ""))
        if double and self.doubles_count >= 3:
            jail.send_to_jail(self, p, "(3 doubles)")
            self._advance()
            return
        self.extra_roll = double
        self._move(p, d1 + d2)

    def _move(self, p: Player, steps: int) -> None:
        dest = (p.pos + steps) % BOARD_SIZE
        self._place(p, dest, p.pos + steps >= BOARD_SIZE)

    def _place(self, p: Player, dest: int, passed_start: bool, depth: int = 0) -> None:
        p.pos = dest
        if passed_start:
            economy.credit(self, p, self.rules["salary"], "salary")
            self.emit(f"💵 {p.name} ko START salary {self.rules['salary']} mili.")
        if depth > 3:
            self._after_land()
        else:
            self._land(p, depth)

    def _land(self, p: Player, depth: int = 0) -> None:
        t = self.board[p.pos]
        if t.buyable:
            self._land_property(p, t)
        elif t.type == "tax":
            economy.charge(self, p, [(None, t.amount)], t.name, pot=self.rules["free_parking_jackpot"])
        elif t.type in ("chance", "community"):
            card = cards.draw(self, t.type)
            self.emit(f"🃏 {card['text']}")
            if cards.apply(self, p, card, depth):
                return
        elif t.type == "go_to_jail":
            jail.send_to_jail(self, p)
        elif t.type == "free_parking" and self.rules["free_parking_jackpot"] and self.pot:
            economy.credit(self, p, self.pot, "free parking jackpot")
            self.emit(f"🎁 {p.name} ne Free Parking jackpot {self.pot} jeeta!")
            self.pot = 0
        self._after_land()

    def _land_property(self, p: Player, t) -> None:
        owner = self.tile_owner.get(t.id)
        if owner is None:
            if p.cash >= t.price:
                self.state = State.PROPERTY_DECISION
                self.pending_tile = t.id
                return
            self.emit(f"💸 {p.name} {t.name} afford nahi kar sakta.")
            self._decline(t.id)
        elif owner != p.id:
            if t.id in self.mortgaged:
                self.emit(f"🏦 {t.name} mortgaged hai, rent nahi.")
                return
            rent = properties.rent_due(self, t, sum(self.dice or (3, 4)))
            economy.charge(self, p, [(owner, rent)], f"rent {t.name}")
            if self.state != State.PAYMENT:
                self.emit(f"🏠 {p.name} ne {self.player(owner).name} ko rent {rent} diya.")

    def _decline(self, tile_id: int) -> None:
        self.pending_tile = None
        if self.rules["auction_enabled"]:
            auction.start(self, tile_id)
        # else: property stays with the bank; _after_land continues the turn

    def _after_land(self) -> None:
        if self.state in (State.PAYMENT, State.PROPERTY_DECISION, State.AUCTION):
            return
        self._finish()

    def _finish(self) -> None:
        """Landing fully resolved: extra roll, manage phase, or next player."""
        if self.state == State.GAME_OVER:
            return
        self.pending_tile = None
        p = self.current
        if p.bankrupt or p.in_jail:
            self._advance()
        elif self.extra_roll:
            self.state = State.WAITING_FOR_ROLL
            self.emit(f"🔁 {p.name} ko doubles ke liye dobara roll milta hai.")
        else:
            self.state = State.DICE_ROLLED

    # ------------------------------------------------------------ turn management
    def _advance(self) -> None:
        self.doubles_count, self.extra_roll, self.pending_tile = 0, False, None
        if self._check_winner():
            return
        n, old, idx = len(self.players), self.turn, self.turn
        while True:
            idx = (idx + 1) % n
            if not self.players[idx].bankrupt:
                break
        if idx <= old:
            self.round += 1
        self.turn = idx
        self.turn_count += 1
        limit = self.rules["max_rounds"]
        if limit and self.round > limit:
            self._time_up()
            return
        p = self.current
        self.state = State.JAIL_DECISION if p.in_jail else State.WAITING_FOR_ROLL
        self.emit(f"▶️ {p.name} ki turn" + (" (jail me)" if p.in_jail else ""))

    def _rank_active(self) -> None:
        ranked = sorted(self.active_players, key=lambda p: -economy.net_worth(self, p))
        for i, p in enumerate(ranked, 1):
            p.rank = i

    def _game_over(self) -> None:
        self._rank_active()
        winner = min(self.active_players, key=lambda p: p.rank)
        self.winner_id = winner.id
        self.state = State.GAME_OVER
        self.auction = self.debt = self.pending_trade = None
        self.emit(f"🏆 {winner.name} jeet gaya!")

    def _check_winner(self) -> bool:
        if len(self.active_players) <= 1 and self.started:
            self._game_over()
            return True
        return False

    def _time_up(self) -> None:
        self.emit("⏱ Round limit khatam! Sabse ameer player jeetega.")
        self._game_over()

    @action
    def end_turn(self, uid: int) -> None:
        self._require_current(uid)
        if self.state != State.DICE_ROLLED:
            raise GameError("Pehle dice roll karke turn poori karo.")
        self._advance()

    # ------------------------------------------------------------ buy / skip / auction
    @action
    def buy(self, uid: int) -> None:
        p = self._require_current(uid)
        if self.state != State.PROPERTY_DECISION or self.pending_tile is None:
            raise GameError("Abhi kharidne ke liye koi property nahi hai.")
        t = self.board[self.pending_tile]
        properties.buy(self, p, t)
        self.emit(f"🛒 {p.name} ne {t.name} {t.price} me kharidi.")
        self._finish()

    @action
    def skip(self, uid: int) -> None:
        p = self._require_current(uid)
        if self.state != State.PROPERTY_DECISION or self.pending_tile is None:
            raise GameError("Abhi skip karne ke liye koi property nahi hai.")
        self._skip(p)

    def _skip(self, p: Player) -> None:
        tid = self.pending_tile
        self.emit(f"⏭ {p.name} ne {self.board[tid].name} skip ki.")
        self._decline(tid)
        if self.state != State.AUCTION:
            self._finish()

    @action
    def bid(self, uid: int, step: int) -> None:
        auction.bid(self, uid, step)

    @action
    def pass_auction(self, uid: int) -> None:
        auction.pass_(self, uid)

    # ------------------------------------------------------------ jail
    @action
    def pay_bail(self, uid: int) -> None:
        p = self._require_current(uid)
        if self.state != State.JAIL_DECISION:
            raise GameError("Abhi bail nahi de sakte.")
        jail.pay_bail(self, p)

    @action
    def use_jail_card(self, uid: int) -> None:
        p = self._require_current(uid)
        if self.state != State.JAIL_DECISION:
            raise GameError("Abhi card use nahi kar sakte.")
        jail.use_card(self, p)

    # ------------------------------------------------------------ property management
    def _after_manage(self, p: Player) -> None:
        if self.state == State.PAYMENT and self.debt and self.debt["debtor"] == p.id \
                and p.cash >= self.debt["total"]:
            self._pay_debt(p)

    @action
    def build(self, uid: int, tile_id: int) -> None:
        p = self._manager(uid)
        properties.build(self, p, tile_id)
        self.emit(f"🏗 {p.name} ne {self.board[tile_id].name} pe ghar banaya.")

    @action
    def sell_house(self, uid: int, tile_id: int) -> None:
        p = self._manager(uid)
        r = properties.sell_house(self, p, tile_id)
        self.emit(f"🏚 {p.name} ne {self.board[tile_id].name} ka ghar becha (+{r}).")
        self._after_manage(p)

    @action
    def mortgage(self, uid: int, tile_id: int) -> None:
        p = self._manager(uid)
        r = properties.mortgage(self, p, tile_id)
        self.emit(f"🏦 {p.name} ne {self.board[tile_id].name} mortgage ki (+{r}).")
        self._after_manage(p)

    @action
    def unmortgage(self, uid: int, tile_id: int) -> None:
        p = self._manager(uid)
        properties.unmortgage(self, p, tile_id)
        self.emit(f"💳 {p.name} ne {self.board[tile_id].name} unmortgage ki.")

    @action
    def sell_property(self, uid: int, tile_id: int) -> None:
        p = self._manager(uid)
        r = properties.sell_property(self, p, tile_id)
        self.emit(f"💸 {p.name} ne {self.board[tile_id].name} bank ko becha (+{r}).")
        self._after_manage(p)

    # ------------------------------------------------------------ debt / bankruptcy
    @action
    def pay_debt(self, uid: int) -> None:
        if self.state != State.PAYMENT or not self.debt:
            raise GameError("Koi payment pending nahi hai.")
        if self.debt["debtor"] != uid:
            raise GameError("Ye payment aapki nahi hai.")
        p = self.player(uid)
        p.afk = 0
        if p.cash < self.debt["total"]:
            raise GameError(f"Abhi bhi paise kam hain: {self.debt['total'] - p.cash} aur chahiye.")
        self._pay_debt(p)

    def _pay_debt(self, p: Player) -> None:
        d, self.debt = self.debt, None
        economy.settle(self, p, [tuple(x) for x in d["payees"]], d["reason"], d["pot"])
        self.emit(f"✅ {p.name} ne {d['total']} chuka diya ({d['reason']}).")
        then = d.get("then")
        if then and "move" in then:
            p.in_jail = False
            self._move(p, then["move"])
        else:
            self._finish()

    @action
    def declare_bankruptcy(self, uid: int) -> None:
        if self.state != State.PAYMENT or not self.debt or self.debt["debtor"] != uid:
            raise GameError("Bankruptcy sirf pending payment ke time declare ho sakti hai.")
        self._bankrupt_from_debt(self.player(uid))

    def _bankrupt_from_debt(self, p: Player) -> None:
        payees = self.debt["payees"]
        creditors = {x[0] for x in payees}
        creditor = creditors.pop() if len(creditors) == 1 and None not in creditors else None
        bankruptcy.declare(self, p, creditor)
        self._after_elimination(p)

    def _eliminate(self, p: Player, why: str) -> None:
        self.emit(f"🚪 {p.name} {why}.")
        creditor = None
        bankruptcy.declare(self, p, creditor)
        self._after_elimination(p)

    def _after_elimination(self, p: Player) -> None:
        if self._check_winner():
            return
        a = self.auction
        if a:
            if a["bidder"] == p.id:
                a["bidder"], a["high"] = None, 0
            auction.check_close(self)
        if self.state not in BLOCKED and self.state != State.AUCTION and self.current.bankrupt:
            self._advance()

    # ------------------------------------------------------------ trading
    @action
    def propose_trade(self, uid: int, to_uid: int, give: list, get: list, cash: int) -> None:
        self._manager(uid)
        self.player(to_uid)
        trading.propose(self, uid, to_uid, give, get, cash)

    @action
    def accept_trade(self, uid: int) -> None:
        trading.accept(self, uid)

    @action
    def reject_trade(self, uid: int) -> None:
        trading.reject(self, uid)

    # ------------------------------------------------------------ timeouts
    def check_timeouts(self, now: float | None = None) -> bool:
        """Called every few seconds by the bot. Returns True if the game changed."""
        now = now or time.time()
        if self.state in BLOCKED:
            return False
        changed = False
        pt = self.pending_trade
        if pt and now >= pt["expires"]:
            self.pending_trade = None
            self.emit("⌛ Trade offer expire ho gaya.")
            changed = True
        if now < self.deadline:
            if changed:
                self.version += 1
            return changed
        if self.state == State.AUCTION:
            auction.resolve(self)
            self._touch()
            return True
        actor = self.player(self.debt["debtor"]) if self.state == State.PAYMENT else self.current
        if not actor.is_bot:
            actor.afk += 1
            if actor.afk >= self.rules["max_afk"]:
                self._eliminate(actor, "inactive tha, game se hata diya gaya")
                self._touch()
                return True
        self.emit(f"⏰ {actor.name} ka time khatam — auto action.")
        if self.state in (State.WAITING_FOR_ROLL, State.JAIL_DECISION):
            self._roll(actor)
        elif self.state == State.PROPERTY_DECISION:
            self._skip(actor)
        elif self.state == State.PAYMENT:
            self._bankrupt_from_debt(actor)
        elif self.state == State.DICE_ROLLED:
            self._advance()
        self._touch()
        return True

    # ------------------------------------------------------------ bot players
    def bot_actor(self) -> Player | None:
        if self.state in BLOCKED:
            return None
        pt = self.pending_trade
        if pt and self.player(pt["to"]).is_bot:
            return self.player(pt["to"])
        if self.state == State.AUCTION:
            a = self.auction
            for p in auction.remaining(self):
                if p.is_bot:
                    return p
            return None
        if self.state == State.PAYMENT:
            d = self.player(self.debt["debtor"])
            return d if d.is_bot else None
        return self.current if self.current.is_bot else None

    def bot_step(self) -> bool:
        p = self.bot_actor()
        if not p:
            return False
        try:
            self._bot_act(p)
        except GameError:
            self._bot_fallback(p)
        self._touch()
        return True

    def _bot_act(self, p: Player) -> None:
        pt = self.pending_trade
        if pt and pt["to"] == p.id:
            trading.reject(self, p.id)
        elif self.state == State.AUCTION:
            a = self.auction
            t = self.board[a["tile"]]
            nxt = max(a["min_bid"], a["high"] + a["inc"])
            if a["bidder"] != p.id and nxt <= min(t.price * 0.8, p.cash * 0.4):
                auction.bid(self, p.id, a["inc"])
            else:
                auction.pass_(self, p.id)
        elif self.state == State.PAYMENT:
            self._bot_raise_money(p)
        elif self.state == State.JAIL_DECISION:
            if p.jail_cards:
                jail.use_card(self, p)
            elif p.cash > 4000:
                jail.pay_bail(self, p)
            else:
                self._roll(p)
        elif self.state == State.WAITING_FOR_ROLL:
            self._roll(p)
        elif self.state == State.PROPERTY_DECISION:
            t = self.board[self.pending_tile]
            if p.cash - t.price >= 1000:
                properties.buy(self, p, t)
                self.emit(f"🛒 {p.name} ne {t.name} {t.price} me kharidi.")
                self._finish()
            else:
                self._skip(p)
        elif self.state == State.DICE_ROLLED:
            for tid in properties.owned_by(self, p.id):
                if p.cash >= 3000 and properties.can_build(self, p, tid) is None:
                    properties.build(self, p, tid)
                    self.emit(f"🏗 {p.name} ne {self.board[tid].name} pe ghar banaya.")
                    return
            self._advance()

    def _bot_raise_money(self, p: Player) -> None:
        if p.cash >= self.debt["total"]:
            self._pay_debt(p)
            return
        owned = properties.owned_by(self, p.id)
        for tid in sorted(owned, key=lambda i: -self.houses.get(i, 0)):
            try:
                if self.houses.get(tid, 0):
                    properties.sell_house(self, p, tid)
                    return
            except GameError:
                continue
        for tid in owned:
            if tid not in self.mortgaged:
                try:
                    properties.mortgage(self, p, tid)
                    self.emit(f"🏦 {p.name} ne {self.board[tid].name} mortgage ki.")
                    return
                except GameError:
                    continue
        self._bankrupt_from_debt(p)

    def _bot_fallback(self, p: Player) -> None:
        """If a bot's plan raised a rule error, do the safest legal thing so the game never stalls."""
        try:
            if self.state == State.AUCTION:
                auction.pass_(self, p.id)
            elif self.state == State.PAYMENT:
                self._bankrupt_from_debt(p)
            elif self.state == State.PROPERTY_DECISION:
                self._skip(p)
            elif self.state == State.DICE_ROLLED:
                self._advance()
            elif self.pending_trade:
                self.pending_trade = None
            else:
                self._roll(p)
        except GameError:
            self._advance()

    # ------------------------------------------------------------ save / load
    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id, "chat_id": self.chat_id, "host_id": self.host_id,
            "rules": self.rules, "players": [p.to_dict() for p in self.players],
            "state": self.state.value, "turn": self.turn, "round": self.round,
            "turn_count": self.turn_count,
            "tile_owner": {str(k): v for k, v in self.tile_owner.items()},
            "houses": {str(k): v for k, v in self.houses.items()},
            "mortgaged": sorted(self.mortgaged), "dice": list(self.dice) if self.dice else None,
            "doubles_count": self.doubles_count, "extra_roll": self.extra_roll,
            "pending_tile": self.pending_tile, "debt": self.debt, "auction": self.auction,
            "pending_trade": self.pending_trade, "decks": self.decks,
            "card_history": self.card_history, "pot": self.pot, "log": self.log, "tx": self.tx,
            "deadline": self.deadline, "version": self.version, "message_id": self.message_id,
            "created_at": self.created_at, "winner_id": self.winner_id, "mode": self.mode, "played": self.played,
        }

    @classmethod
    def from_dict(cls, d: dict, rng=None) -> "Game":
        g = cls(d["room_id"], d["chat_id"], d["host_id"], d["rules"], rng)
        g.players = [Player.from_dict(x) for x in d["players"]]
        g.state = State(d["state"])
        g.turn, g.round, g.turn_count = d["turn"], d["round"], d["turn_count"]
        g.tile_owner = {int(k): v for k, v in d["tile_owner"].items()}
        g.houses = {int(k): v for k, v in d["houses"].items()}
        g.mortgaged = set(d["mortgaged"])
        g.dice = tuple(d["dice"]) if d["dice"] else None
        g.doubles_count, g.extra_roll = d["doubles_count"], d["extra_roll"]
        g.pending_tile, g.debt, g.auction = d["pending_tile"], d["debt"], d["auction"]
        g.pending_trade, g.decks = d["pending_trade"], d["decks"]
        g.card_history, g.pot, g.log, g.tx = d["card_history"], d["pot"], d["log"], d["tx"]
        g.deadline, g.version, g.message_id = d["deadline"], d["version"], d["message_id"]
        g.created_at, g.winner_id, g.mode = d["created_at"], d["winner_id"], d.get("mode", "classic")
        g.played = d.get("played", g.started)
        if g.started and not g.finished:
            g.deadline = time.time() + g.rules["turn_timeout"]   # fresh timer after a restart
        return g
