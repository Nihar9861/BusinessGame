"""Board definition loaded from data/board.json (edit the JSON to change the board)."""
import json
from dataclasses import dataclass, field

from config import DATA_DIR

BOARD_SIZE = 40
JAIL_POS = 10
PROPERTY_TYPES = ("property", "railway", "utility")


@dataclass(frozen=True)
class Tile:
    id: int
    name: str
    type: str
    price: int = 0
    group: str = ""
    rents: tuple = ()
    amount: int = 0
    color: str = "#CCCCCC"
    house_cost: int = 0

    @property
    def buyable(self) -> bool:
        return self.type in PROPERTY_TYPES

    @property
    def mortgage_value(self) -> int:
        return self.price // 2


@dataclass
class Board:
    tiles: list = field(default_factory=list)
    groups: dict = field(default_factory=dict)      # group name -> [tile ids]
    group_info: dict = field(default_factory=dict)
    currency: str = "₹"
    revision: int = 0

    def __getitem__(self, i: int) -> Tile:
        return self.tiles[i]

    def __len__(self):
        return len(self.tiles)

    def load(self, path=None) -> None:
        raw = json.loads((path or DATA_DIR / "board.json").read_text(encoding="utf-8"))
        self.currency = raw.get("currency", "₹")
        self.group_info = raw["groups"]
        tiles, groups = [], {}
        for t in raw["tiles"]:
            info = self.group_info.get(t.get("group", ""), {})
            tile = Tile(id=t["id"], name=t["name"], type=t["type"], price=t.get("price", 0),
                        group=t.get("group", ""), rents=tuple(t.get("rents", ())),
                        amount=t.get("amount", 0), color=info.get("color", "#CCCCCC"),
                        house_cost=info.get("house_cost", 0))
            tiles.append(tile)
            if tile.buyable:
                groups.setdefault(tile.group, []).append(tile.id)
        if [t.id for t in tiles] != list(range(len(tiles))) or len(tiles) != BOARD_SIZE:
            raise ValueError("board.json must have tiles with ids 0..39 in order")
        self.tiles, self.groups = tiles, groups
        self.revision += 1


BOARD = Board()
BOARD.load()


def reload_board() -> None:
    BOARD.load()
