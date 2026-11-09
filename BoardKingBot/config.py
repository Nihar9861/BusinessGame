"""Configuration: environment variables + game rules (rules can be changed by admins)."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'boardking.db'}")
if DATABASE_URL.startswith("postgres://"):          # Railway/Heroku style URL -> SQLAlchemy style
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")          # empty -> polling mode
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8443"))
LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "boardking.log"))
RULES_FILE = Path(os.getenv("RULES_FILE", str(BASE_DIR / "rules_override.json")))


def _parse_ids(raw: str) -> set[int]:
    out = set()
    for part in raw.replace(" ", "").split(","):
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


ADMIN_IDS: set[int] = _parse_ids(os.getenv("ADMIN_IDS", ""))
MAINTENANCE = {"on": False}  # runtime flag toggled by /maintenance

DEFAULT_RULES = {
    "starting_cash": 15000,
    "salary": 2000,
    "bail": 500,
    "max_jail_turns": 3,
    "turn_timeout": 90,        # seconds a player has for each decision
    "auction_enabled": True,
    "auction_timeout": 30,
    "auction_increment": 100,
    "trade_timeout": 120,
    "free_parking_jackpot": False,
    "double_rent_full_set": True,
    "max_afk": 3,              # consecutive timeouts before a player is removed
    "max_rounds": 0,           # 0 = unlimited. Otherwise richest player wins after N rounds
    "lobby_timeout": 900,      # seconds before an unused lobby expires
}
PRESETS = {
    "classic": {},
    "quick": {"starting_cash": 10000, "max_rounds": 20, "turn_timeout": 60, "auction_timeout": 20},
}


def load_rules() -> dict:
    rules = dict(DEFAULT_RULES)
    if RULES_FILE.exists():
        try:
            rules.update(json.loads(RULES_FILE.read_text()))
        except (OSError, ValueError):
            pass
    return rules


def set_rule(key: str, value: str) -> object:
    """Change one rule permanently (admin command). Returns the new typed value."""
    if key not in DEFAULT_RULES:
        raise KeyError(key)
    default = DEFAULT_RULES[key]
    if isinstance(default, bool):
        typed = value.lower() in ("1", "true", "on", "yes")
    else:
        typed = int(value)
        if typed < 0:
            raise ValueError("negative")
    current = {}
    if RULES_FILE.exists():
        try:
            current = json.loads(RULES_FILE.read_text())
        except (OSError, ValueError):
            current = {}
    current[key] = typed
    RULES_FILE.write_text(json.dumps(current, indent=1))
    return typed
