"""The shape a Zuordnungsfrage has to have.

Lives on its own because both ends need it and they cannot import each other:
`models.py` bakes these bounds into the JSON Schema handed to the model, and
`validate.py` checks them again on the way out. One definition, so the grammar
and the checks can never drift apart.

**A question is a one-to-one pairing.** Every answer belongs to exactly one
category, every category holds exactly one answer, and there is nothing else on
the board -- no extra answers that fit nowhere. So the number of categories and
the number of answers are the same number, and that is what `MIN_PAIRS` and
`MAX_PAIRS` bound.

One consequence is worth knowing rather than discovering: with a strict pairing
the final placement is forced. Once every answer but one is placed, the last has
exactly one home left.
"""

MIN_PAIRS = 10
MAX_PAIRS = 14

MIN_CATEGORIES = MIN_PAIRS
MAX_CATEGORIES = MAX_PAIRS
MIN_ITEMS = MIN_PAIRS
MAX_ITEMS = MAX_PAIRS

MAX_ITEM_WORDS = 4

DIFFICULTIES = ("easy", "medium", "hard")
