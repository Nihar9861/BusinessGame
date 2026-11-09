import random

from dice import is_double, roll_dice


def test_dice_range_and_both_values_used():
    seen = set()
    for _ in range(2000):
        a, b = roll_dice()
        assert 1 <= a <= 6 and 1 <= b <= 6
        seen.update((a, b))
    assert seen == {1, 2, 3, 4, 5, 6}


def test_seeded_rng_is_reproducible():
    assert [roll_dice(random.Random(5)) for _ in range(3)] == [roll_dice(random.Random(5)) for _ in range(3)]


def test_double_detection():
    assert is_double((3, 3)) and not is_double((3, 4))


def test_doubles_happen_about_one_in_six():
    n = sum(is_double(roll_dice()) for _ in range(6000))
    assert 700 < n < 1300
