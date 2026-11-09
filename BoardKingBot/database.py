"""Database engine, sessions and simple versioned migrations."""
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import config
import models

_engine = None
_Session = None


def init_db(url: str | None = None):
    """Create the engine, run migrations and seed board/card tables."""
    global _engine, _Session
    url = url or config.DATABASE_URL
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    _engine = create_engine(url, **kwargs)
    _Session = sessionmaker(_engine, expire_on_commit=False)
    migrate()
    seed_static_tables()
    return _engine


@contextmanager
def session_scope():
    """Transaction: commit on success, rollback on any error."""
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# ---- migrations: add a function to MIGRATIONS to change the schema in the future
def _m1(conn):
    models.Base.metadata.create_all(conn)


MIGRATIONS = [(1, _m1)]


def migrate() -> None:
    with _engine.begin() as conn:
        models.Base.metadata.create_all(conn, tables=[models.SchemaVersion.__table__])
        row = conn.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
        current = row or 0
        for version, fn in MIGRATIONS:
            if version > current:
                fn(conn)
                conn.execute(text("INSERT INTO schema_version (version) VALUES (:v)"), {"v": version})


def seed_static_tables() -> None:
    from board import BOARD
    from cards import CARDS
    with session_scope() as s:
        s.query(models.BoardTile).delete()
        s.query(models.CardRow).delete()
        for t in BOARD.tiles:
            s.add(models.BoardTile(id=t.id, name=t.name, type=t.type, price=t.price,
                                   group_name=t.group, rents=",".join(map(str, t.rents))))
        for deck, lst in CARDS.items():
            for c in lst:
                s.add(models.CardRow(id=c["id"], deck=deck, text=c["text"], type=c["type"]))


def tables_exist() -> bool:
    return "users" in inspect(_engine).get_table_names()
