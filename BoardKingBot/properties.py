"""Ownership, rent, houses/hotels, mortgage and selling."""
import math

from board import PROPERTY_TYPES
from errors import GameError
import economy

HOTEL = 5


def owned_by(game, uid: int) -> list[int]:
    return sorted(t for t, o in game.tile_owner.items() if o == uid)


def group_tiles(game, tile) -> list[int]:
    return game.board.groups.get(tile.group, [])


def owns_full_group(game, uid: int, tile) -> bool:
    return all(game.tile_owner.get(i) == uid for i in group_tiles(game, tile))


def group_has_buildings(game, tile) -> bool:
    return any(game.houses.get(i, 0) > 0 for i in group_tiles(game, tile))


def rent_due(game, tile, dice_total: int = 7) -> int:
    owner = game.tile_owner.get(tile.id)
    if owner is None or tile.id in game.mortgaged:
        return 0
    same = [i for i in game.board.groups[tile.group] if game.tile_owner.get(i) == owner]
    if tile.type == "railway":
        return tile.rents[len(same) - 1]
    if tile.type == "utility":
        return dice_total * tile.rents[0 if len(same) == 1 else 1]
    h = game.houses.get(tile.id, 0)
    rent = tile.rents[h]
    if h == 0 and game.rules.get("double_rent_full_set") and len(same) == len(game.board.groups[tile.group]):
        rent *= 2
    return rent


def _get_owned(game, p, tile_id: int):
    if not (0 <= tile_id < len(game.board)):
        raise GameError("Galat property.")
    t = game.board[tile_id]
    if not t.buyable:
        raise GameError("Ye property nahi hai.")
    if game.tile_owner.get(tile_id) != p.id:
        raise GameError(f"{t.name} aapki nahi hai.")
    return t


def buy(game, p, tile) -> None:
    if game.tile_owner.get(tile.id) is not None:
        raise GameError("Property already bik chuki hai.")
    economy.debit(game, p, tile.price, f"buy {tile.name}")
    game.tile_owner[tile.id] = p.id


def can_build(game, p, tile_id: int) -> str | None:
    """Return None if p can build on tile, else the reason why not."""
    try:
        t = _get_owned(game, p, tile_id)
    except GameError as e:
        return str(e)
    if t.type != "property":
        return "Yahan ghar nahi ban sakta."
    if not owns_full_group(game, p.id, t):
        return "Pura color-set chahiye."
    if any(i in game.mortgaged for i in group_tiles(game, t)):
        return "Set me koi mortgaged hai."
    h = game.houses.get(tile_id, 0)
    if h >= HOTEL:
        return "Hotel already hai."
    if h > min(game.houses.get(i, 0) for i in group_tiles(game, t)):
        return "Pehle baaki properties pe barabar ghar banao."
    if p.cash < t.house_cost:
        return f"Cash kam hai (chahiye {t.house_cost})."
    return None


def build(game, p, tile_id: int) -> None:
    reason = can_build(game, p, tile_id)
    if reason:
        raise GameError(reason)
    t = game.board[tile_id]
    economy.debit(game, p, t.house_cost, f"build on {t.name}")
    game.houses[tile_id] = game.houses.get(tile_id, 0) + 1


def sell_house(game, p, tile_id: int) -> int:
    t = _get_owned(game, p, tile_id)
    h = game.houses.get(tile_id, 0)
    if h <= 0:
        raise GameError("Is property pe ghar nahi hai.")
    if h < max(game.houses.get(i, 0) for i in group_tiles(game, t)):
        raise GameError("Pehle sabse zyada ghar wali property se becho.")
    refund = t.house_cost // 2
    economy.credit(game, p, refund, f"sell house {t.name}")
    if h == 1:
        game.houses.pop(tile_id)
    else:
        game.houses[tile_id] = h - 1
    return refund


def mortgage(game, p, tile_id: int) -> int:
    t = _get_owned(game, p, tile_id)
    if tile_id in game.mortgaged:
        raise GameError("Already mortgaged.")
    if group_has_buildings(game, t):
        raise GameError("Pehle is set ke ghar/hotel becho.")
    game.mortgaged.add(tile_id)
    economy.credit(game, p, t.mortgage_value, f"mortgage {t.name}")
    return t.mortgage_value


def unmortgage_cost(tile) -> int:
    return int(math.ceil(tile.mortgage_value * 1.1 / 10) * 10)


def unmortgage(game, p, tile_id: int) -> int:
    t = _get_owned(game, p, tile_id)
    if tile_id not in game.mortgaged:
        raise GameError("Ye mortgaged nahi hai.")
    cost = unmortgage_cost(t)
    economy.debit(game, p, cost, f"unmortgage {t.name}")
    game.mortgaged.discard(tile_id)
    return cost


def sell_property(game, p, tile_id: int) -> int:
    """Sell an unmortgaged property back to the bank for half its price."""
    t = _get_owned(game, p, tile_id)
    if tile_id in game.mortgaged:
        raise GameError("Mortgaged property bech nahi sakte (pehle unmortgage karo).")
    if group_has_buildings(game, t):
        raise GameError("Pehle is set ke ghar/hotel becho.")
    economy.credit(game, p, t.mortgage_value, f"sell {t.name}")
    del game.tile_owner[tile_id]
    return t.mortgage_value
