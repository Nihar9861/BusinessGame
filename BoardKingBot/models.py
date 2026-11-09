"""SQLAlchemy models. The live game state is stored as a JSON snapshot (game_rooms.state_json)
so a game can be restored after a restart; the other tables are queryable records for stats/admin."""
import datetime as dt

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)          # Telegram user id
    username: Mapped[str] = mapped_column(String(64), default="")
    display_name: Mapped[str] = mapped_column(String(128), default="")
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_won: Mapped[int] = mapped_column(Integer, default=0)
    games_lost: Mapped[int] = mapped_column(Integer, default=0)
    total_earnings: Mapped[int] = mapped_column(BigInteger, default=0)
    bankruptcies: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    @property
    def win_percentage(self) -> float:
        return round(100 * self.games_won / self.games_played, 1) if self.games_played else 0.0


class GameRoom(Base):
    __tablename__ = "game_rooms"
    room_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    host_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24), default="LOBBY")     # LOBBY / ACTIVE / FINISHED / CLOSED
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)


class PlayerRow(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_player_room_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("game_rooms.room_id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(128))
    cash: Mapped[int] = mapped_column(BigInteger, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    in_jail: Mapped[bool] = mapped_column(Boolean, default=False)
    bankrupt: Mapped[bool] = mapped_column(Boolean, default=False)
    rank: Mapped[int] = mapped_column(Integer, default=0)


class PropertyRow(Base):
    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("room_id", "tile_id", name="uq_property_room_tile"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("game_rooms.room_id", ondelete="CASCADE"), index=True)
    tile_id: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[int] = mapped_column(BigInteger)
    houses: Mapped[int] = mapped_column(Integer, default=0)
    mortgaged: Mapped[bool] = mapped_column(Boolean, default=False)


class BoardTile(Base):
    """Copy of data/board.json (seeded at startup) so tiles can be queried in SQL."""
    __tablename__ = "board_tiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(24))
    price: Mapped[int] = mapped_column(Integer, default=0)
    group_name: Mapped[str] = mapped_column(String(24), default="")
    rents: Mapped[str] = mapped_column(String(128), default="")


class CardRow(Base):
    __tablename__ = "cards"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    deck: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(24))


class TransactionRow(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[int] = mapped_column(BigInteger)
    from_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)   # None = bank
    to_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(128))


class AuctionRow(Base):
    __tablename__ = "auctions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(16), index=True)
    tile_id: Mapped[int] = mapped_column(Integer)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class TradeRow(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(16), index=True)
    from_id: Mapped[int] = mapped_column(BigInteger)
    to_id: Mapped[int] = mapped_column(BigInteger)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class GameEvent(Base):
    __tablename__ = "game_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(16), index=True)
    text: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class GameHistory(Base):
    __tablename__ = "game_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(16), unique=True)           # prevents duplicate history
    chat_id: Mapped[int] = mapped_column(BigInteger)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    finished_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)


class ErrorLog(Base):
    __tablename__ = "error_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    text: Mapped[str] = mapped_column(Text)
