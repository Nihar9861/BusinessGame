from enum import Enum


class State(str, Enum):
    WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"   # lobby
    WAITING_FOR_ROLL = "WAITING_FOR_ROLL"         # current player must roll
    PROPERTY_DECISION = "PROPERTY_DECISION"       # buy or skip (-> auction)
    AUCTION = "AUCTION"
    PAYMENT = "PAYMENT"                           # debt: raise money or go bankrupt
    JAIL_DECISION = "JAIL_DECISION"               # roll / pay bail / use card
    DICE_ROLLED = "DICE_ROLLED"                   # turn resolved, manage assets then end turn
    GAME_OVER = "GAME_OVER"
