import random
from collections import Counter

from app.services.drafting import draw_balanced

POOLS = {
    "geografie": ["geo-1", "geo-2", "geo-3"],
    "musik": ["mus-1", "mus-2", "mus-3"],
    "sport": ["spo-1", "spo-2", "spo-3"],
}


def subject_of(slug: str) -> str:
    return slug.split("-")[0]


def spread(drawn: list[str]) -> Counter:
    return Counter(subject_of(slug) for slug in drawn)


def test_draws_the_requested_number():
    assert len(draw_balanced(POOLS, 5, rng=random.Random(1))) == 5


def test_an_exact_multiple_is_split_evenly():
    drawn = draw_balanced(POOLS, 6, rng=random.Random(1))
    assert spread(drawn) == Counter({"geo": 2, "mus": 2, "spo": 2})


def test_a_remainder_differs_by_at_most_one():
    for seed in range(20):
        drawn = draw_balanced(POOLS, 5, rng=random.Random(seed))
        counts = sorted(spread(drawn).values())
        assert counts == [1, 2, 2], f"seed {seed} gave {counts}"


def test_no_question_is_drawn_twice():
    drawn = draw_balanced(POOLS, 9, rng=random.Random(3))
    assert len(set(drawn)) == 9


def test_asking_for_more_than_exists_returns_everything_once():
    drawn = draw_balanced(POOLS, 50, rng=random.Random(4))
    assert sorted(drawn) == sorted(s for pool in POOLS.values() for s in pool)


def test_a_small_subject_does_not_short_change_the_count():
    """Choosing a big and a tiny subject should still fill the round count."""
    pools = {"big": [f"b-{i}" for i in range(10)], "tiny": ["t-1"]}

    drawn = draw_balanced(pools, 6, rng=random.Random(5))

    assert len(drawn) == 6
    assert spread(drawn)["t"] == 1  # tiny contributed all it had


def test_a_single_subject_works():
    drawn = draw_balanced({"solo": ["a", "b", "c"]}, 2, rng=random.Random(6))
    assert len(drawn) == 2
    assert set(drawn) <= {"a", "b", "c"}


def test_empty_pools_yield_nothing_rather_than_looping():
    assert draw_balanced({}, 5, rng=random.Random(7)) == []
    assert draw_balanced({"a": []}, 5, rng=random.Random(7)) == []


def test_the_running_order_is_not_grouped_by_subject():
    """Round-robin alone would produce geo, mus, spo, geo, mus, spo."""
    orders = {
        tuple(subject_of(s) for s in draw_balanced(POOLS, 6, rng=random.Random(seed)))
        for seed in range(15)
    }
    assert len(orders) > 1, "draw order looks deterministic"


def test_which_subject_gets_the_extra_question_varies():
    """The first-listed subject must not always win the remainder."""
    extras = set()
    for seed in range(30):
        counts = spread(draw_balanced(POOLS, 4, rng=random.Random(seed)))
        extras.update(name for name, n in counts.items() if n == 2)
    assert len(extras) > 1, f"only {extras} ever got the extra question"


def test_the_same_seed_reproduces_the_same_draw():
    a = draw_balanced(POOLS, 5, rng=random.Random(42))
    b = draw_balanced(POOLS, 5, rng=random.Random(42))
    assert a == b
