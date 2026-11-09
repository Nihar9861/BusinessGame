class GameError(Exception):
    """A user-visible rule violation (shown to the player as a short message)."""


class InsufficientFunds(GameError):
    pass
