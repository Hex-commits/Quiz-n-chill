"""Choosing which questions a game is played with.

Pure functions: no database, no HTTP, no randomness the caller cannot control.
The `rng` parameter exists so tests can pin the shuffle down.
"""

import random


def draw_balanced(
    pools: dict[str, list[str]],
    count: int,
    *,
    rng: random.Random | None = None,
) -> list[str]:
    """Pick `count` questions spread as evenly as possible across `pools`.

    Deals round-robin from each shuffled pool, so with 5 rounds over 3 subjects
    two subjects contribute 2 questions and one contributes 1 -- rather than the
    lopsided draw a naive "shuffle everything and take 5" would give.

    A subject that runs out is simply skipped, so choosing subjects of very
    different sizes degrades gracefully instead of short-changing the count.
    Returns fewer than `count` only when the pools genuinely hold less.

    The order of the returned list is shuffled: dealing round-robin would
    otherwise make every game run A, B, C, A, B, C.
    """
    rng = rng or random.Random()

    # Shuffle each pool, and the subject order too -- otherwise the subject
    # listed first always gets the extra question when count does not divide
    # evenly.
    remaining = {}
    for slug in rng.sample(sorted(pools), len(pools)):
        shuffled = list(pools[slug])
        rng.shuffle(shuffled)
        remaining[slug] = shuffled

    drawn: list[str] = []
    while len(drawn) < count:
        took_any = False
        for queue in remaining.values():
            if len(drawn) >= count:
                break
            if queue:
                drawn.append(queue.pop())
                took_any = True
        if not took_any:
            break  # every pool is empty

    rng.shuffle(drawn)
    return drawn
