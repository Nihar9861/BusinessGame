from dataclasses import dataclass, asdict


@dataclass
class Player:
    id: int                      # Telegram user id (negative = bot player)
    name: str
    username: str = ""
    cash: int = 0
    pos: int = 0
    in_jail: bool = False
    jail_turns: int = 0
    jail_cards: int = 0
    bankrupt: bool = False
    rank: int = 0                # 1 = winner
    afk: int = 0                 # consecutive timeouts

    @property
    def is_bot(self) -> bool:
        return self.id < 0

    @property
    def active(self) -> bool:
        return not self.bankrupt

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(**d)
