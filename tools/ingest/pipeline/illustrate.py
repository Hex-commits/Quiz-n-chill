"""Deciding whether a question can be a picture question, and which way round.

Runs after both gates, on a question that is already correct. It never rejects
anything: the answer is "yes, this way" or "no, leave it as text", and a "no"
costs the question nothing.

**Why it cannot run earlier.** The pictures a picture question needs are
pictures *of the things being asked about*, not pictures in the article. The
`Kaffee` article is full of coffee photographs and not one of them shows a
variety or a growing region, which is what the pairing is made of. Nothing can
be looked up until extraction has said what the pairs *are*.

**Where the pictures have to end up.** On the categories. A category is the
board -- the thing a player looks at and assigns something to -- so a
photographic category asks "what is this?", which is the question this feature
exists to pose. The answers stay words.

**Why it checks both sides anyway.** Measured across the existing question set,
image coverage sits on whichever side happens to be a concrete thing:

    chemische-elemente    Eisen -> Fe            pictures on the categories
    automarken-laender    Audi  -> Deutschland   pictures on the answers

So both are measured, and when the pictures turn out to be on the answer side
the pairing is flipped to bring them round to the categories. That is sound
because a Zuordnung is symmetric -- `Audi -> Deutschland` and
`Deutschland -> Audi` are the same fact. What is *not* symmetric is the title
and description the model wrote, so a flipped question needs those rewritten;
see `reframe_step` in `chains.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import GeneratedPair, GeneratedQuestion
from ..sources.protocols import Document, Image, ImageProvider

from ..domain.rules import MIN_PAIRS


@dataclass(frozen=True)
class Illustration:
    """What `illustrate` decided about one question."""

    images: dict[str, Image]
    flipped: bool = False
    dropped: tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_picture(self) -> bool:
        return bool(self.images)


def illustrate(
    question: GeneratedQuestion,
    document: Document,
    provider: ImageProvider,
    *,
    min_pairs: int = MIN_PAIRS,
) -> Illustration:
    """Decide whether `question` becomes a picture question.

    Looks up the category side first and stops if that is enough -- it is where
    the pictures have to end up, so finding them already there saves both a
    second round of API calls and the model call that renames a flipped
    question.
    """
    labels = question.labels
    answers = question.answers
    total = len(labels)
    if not total:
        return Illustration({}, detail="no pairs")

    on_labels = provider.images_for(labels, document=document)
    if len(on_labels) >= min_pairs:
        missing = tuple(label for label in labels if label not in on_labels)
        return Illustration(
            images=on_labels,
            flipped=False,
            dropped=missing,
            detail=_detail(len(on_labels), total, "categories", missing),
        )

    on_answers = provider.images_for(answers, document=document)
    if len(on_answers) >= min_pairs:
        missing = tuple(answer for answer in answers if answer not in on_answers)
        return Illustration(
            images=on_answers,
            flipped=True,
            dropped=missing,
            detail=_detail(len(on_answers), total, "answers", missing) + ", flipped",
        )

    best = max(len(on_labels), len(on_answers))
    return Illustration(
        {}, detail=f"stays text -- best side {best}/{total}, needs {min_pairs}"
    )


def _detail(found: int, total: int, side: str, missing: tuple) -> str:
    trimmed = f", {len(missing)} dropped" if missing else ""
    return f"{found}/{total} {side} illustrated{trimmed}"


def keep_illustrated(
    question: GeneratedQuestion, illustration: Illustration
) -> GeneratedQuestion:
    """Drop the pairs whose category has no picture, after any flip.

    Called on the already-flipped question, so `illustration.images` is keyed by
    what is now the category. A question that keeps every pair comes back
    unchanged rather than copied.
    """
    if not illustration.is_picture:
        return question
    keep = [pair for pair in question.pairs if pair.label in illustration.images]
    if len(keep) == len(question.pairs):
        return question
    return question.model_copy(update={"pairs": keep})


def flip(question: GeneratedQuestion) -> GeneratedQuestion:
    """Turn the pairing round: answers become categories and vice versa.

    Sound because a Zuordnung is symmetric -- every category has exactly one
    answer and every answer exactly one category, so reversing the arrow leaves
    a valid question. The bounds and uniqueness rules `validate.py` enforces are
    symmetric too, which is why a flipped question does not need re-checking.

    Explanations are dropped rather than carried: they were written for the old
    direction ("Hauptstadt Deutschlands seit 1990" under `Berlin` explains why
    Berlin belongs to Germany, not why Germany belongs to Berlin), and `explain`
    runs after this.
    """
    return question.model_copy(
        update={
            "pairs": [
                GeneratedPair(label=pair.answer, answer=pair.label)
                for pair in question.pairs
            ],
            "explanations": {},
        }
    )
