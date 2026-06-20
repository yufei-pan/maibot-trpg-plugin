import random

from trpg_dice import Check, Roll, check, roll


def test_roll_is_deterministic_with_seed():
    a = roll("2d6+3", rng=random.Random(42))
    b = roll("2d6+3", rng=random.Random(42))
    assert a == b
    assert a.modifier == 3
    assert a.total == sum(a.rolls) + 3
    assert len(a.rolls) == 2
    assert all(1 <= r <= 6 for r in a.rolls)


def test_roll_single_die_and_negative_modifier():
    r = roll("d20", rng=random.Random(1))
    assert len(r.rolls) == 1 and 1 <= r.rolls[0] <= 20
    r2 = roll("4d8-1", rng=random.Random(1))
    assert r2.modifier == -1 and r2.total == sum(r2.rolls) - 1


def test_check_dc_compare_and_margin():
    c = check(5, 15, rng=random.Random(7))
    assert isinstance(c, Check)
    assert c.total == c.d20 + 5
    assert c.success == (c.total >= 15)
    assert c.margin == c.total - 15


def test_advantage_keeps_higher():
    # advantage must be >= a single-roll baseline under the same seed sequence
    adv = check(0, 10, rng=random.Random(3), advantage=1)
    dis = check(0, 10, rng=random.Random(3), advantage=-1)
    assert adv.d20 >= dis.d20


def test_natural_crit_flags():
    # find a seed producing a natural 20 and natural 1
    nat20 = next(s for s in range(1000) if check(0, 99, rng=random.Random(s)).d20 == 20)
    assert check(0, 99, rng=random.Random(nat20)).crit == "success"
    nat1 = next(s for s in range(1000) if check(0, 0, rng=random.Random(s)).d20 == 1)
    assert check(0, 0, rng=random.Random(nat1)).crit == "fail"
