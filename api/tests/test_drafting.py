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
    assert spread(drawn)["t"] == 1


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


def test_an_unplayed_question_is_preferred_over_a_played_one():
    played = {"geo-1", "geo-2", "mus-1", "mus-2", "spo-1", "spo-2"}

    drawn = draw_balanced(POOLS, 3, rng=random.Random(4), avoid=played)

    assert set(drawn) == {"geo-3", "mus-3", "spo-3"}


def test_played_questions_come_back_once_nothing_new_is_left():
    """The soft half. Dropping them outright would leave a group that has played
    everything with a three-round game they asked five rounds for."""
    everything = {slug for pool in POOLS.values() for slug in pool}

    drawn = draw_balanced(POOLS, 6, rng=random.Random(5), avoid=everything)

    assert len(drawn) == 6


def test_the_new_ones_are_still_used_first_when_topping_up():
    played = {"geo-1", "geo-2", "geo-3", "mus-1", "mus-2", "spo-1"}
    fresh = {"mus-3", "spo-2", "spo-3"}

    drawn = draw_balanced(POOLS, 5, rng=random.Random(6), avoid=played)

    assert len(drawn) == 5
    assert fresh <= set(drawn)


def test_avoiding_everything_still_spreads_across_subjects():
    """The preference is within a subject, never across. Letting one subject
    drop out because its questions are played would trade a repeat for a much
    more noticeable loss of variety."""
    everything = {slug for pool in POOLS.values() for slug in pool}

    drawn = draw_balanced(POOLS, 6, rng=random.Random(7), avoid=everything)

    assert set(spread(drawn)) == {"geo", "mus", "spo"}


def test_no_question_is_drawn_twice_even_when_avoided():
    everything = {slug for pool in POOLS.values() for slug in pool}

    drawn = draw_balanced(POOLS, 9, rng=random.Random(8), avoid=everything)

    assert len(set(drawn)) == 9


def test_an_empty_avoid_set_changes_nothing():
    seed = random.Random(9)
    plain = draw_balanced(POOLS, 5, rng=random.Random(9))

    assert draw_balanced(POOLS, 5, rng=seed, avoid=set()) == plain


def test_the_choice_among_played_questions_is_still_random():
    """Sorting to the back must not make the fallback deterministic, or a group
    that has played everything sees the same game every time."""
    everything = {slug for pool in POOLS.values() for slug in pool}

    seen = {
        tuple(draw_balanced(POOLS, 3, rng=random.Random(seed), avoid=everything))
        for seed in range(12)
    }

    assert len(seen) > 1
