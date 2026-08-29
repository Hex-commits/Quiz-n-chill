"""Cutting a stored question down to the board one hand or round plays.

Its own module because both modes deal one: Classic lays the whole board out at
once, Poker asks about a single category off it. Neither owns the rule, so it
lives beside them rather than inside either.
"""

import random
from dataclasses import replace

from app.services.lobby_state import Round

BOARD_PAIRS = 10

BOARD_FAKES = 2
"""How many fakes a dealt board carries, when the question has that many.

Fixed rather than "whatever the question holds" so that trimming a thirty-pair
question down to ten does not also make it the board with the highest share of
fakes in the game. A question written without fakes deals none, and plays
exactly as it did before they existed."""


def deal_board(round_: Round, rng: random.Random | None = None) -> Round:
    """Cut a stored question down to the pairs this round will play.

    Returns a new `Round` rather than mutating: the loaded question is reused
    every time the quiz comes up, so trimming it in place would make the second
    game a subset of the first, and the third a subset of that.

    Which pairs are dropped is random, which is the point -- a thirty-pair
    picture question is a different board every game. Categories keep their
    written order, because `position` is how the question was meant to read and
    sampling returns them shuffled.

    Fakes are dealt separately and to their own count: they have no category to
    be sampled along with, and filtering items by the surviving categories --
    which is how the pairs are cut -- would drop every one of them.
    """
    rng = rng or random.Random()
    fakes = round_.fakes()
    kept_fakes = (
        fakes if len(fakes) <= BOARD_FAKES else rng.sample(fakes, BOARD_FAKES)
    )

    if len(round_.categories) <= BOARD_PAIRS:
        if len(kept_fakes) == len(fakes):
            return round_
        return replace(round_, items=round_.pairs() + kept_fakes)

    keep = {c.id for c in rng.sample(round_.categories, BOARD_PAIRS)}
    return replace(
        round_,
        categories=[c for c in round_.categories if c.id in keep],
        items=[i for i in round_.pairs() if i.category_id in keep] + kept_fakes,
    )
