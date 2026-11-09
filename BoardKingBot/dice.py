"""Server-side dice. Uses the OS secure random generator."""
import random
import secrets

_rng = secrets.SystemRandom()


def roll_dice(rng: random.Random | None = None) -> tuple[int, int]:
    r = rng or _rng
    return r.randint(1, 6), r.randint(1, 6)


def is_double(dice: tuple[int, int]) -> bool:
    return dice[0] == dice[1]
