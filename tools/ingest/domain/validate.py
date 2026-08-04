"""Checking generated questions before they reach the database.

The model is told the rules in the prompt; this enforces them. Prompt rules are
a request, not a guarantee, and a malformed question is much cheaper to reject
here than to notice mid-game.

Pure functions over the generated payload -- no network, no database -- so the
rules are cheap to test.

Everything a complaint says is fed straight back to the model as its repair
instruction, so each one names the offending value and states the way out.
"""

from __future__ import annotations

import re
import unicodedata

from .models import GeneratedQuestion
from .rules import DIFFICULTIES, MAX_ITEM_WORDS, MAX_PAIRS, MIN_PAIRS

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(value: str) -> str:
    """ASCII slug, with the German umlauts spelled out rather than stripped.

    Plain NFKD would turn 'Flüsse' into 'Flusse'; German convention is 'Fluesse'
    and that is what a reader expects to see in a URL.
    """
    lowered = value.strip().lower()
    for source, replacement in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        lowered = lowered.replace(source, replacement)
    ascii_only = (
        unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_only)).strip("-")


def validate(question: GeneratedQuestion, *, subject_slugs: set[str]) -> list[str]:
    """Return a list of problems. Empty means the question is good to insert."""
    problems: list[str] = []

    if not question.usable:
        return [f"model declined: {question.reason or 'no reason given'}"]

    if question.subject_slug not in subject_slugs:
        problems.append(f"unknown subject_slug {question.subject_slug!r}")

    if question.difficulty not in DIFFICULTIES:
        problems.append(f"difficulty {question.difficulty!r} not in {list(DIFFICULTIES)}")

    if not SLUG_RE.match(question.slug or ""):
        problems.append(f"slug {question.slug!r} is not url-safe")

    if not question.title.strip():
        problems.append("title is empty")

    pairs = question.pairs
    if not MIN_PAIRS <= len(pairs) <= MAX_PAIRS:
        problems.append(
            f"{len(pairs)} pairs, playable range is {MIN_PAIRS}-{MAX_PAIRS} -- "
            "a pair is one category and the single answer belonging to it; if the "
            f"article does not support {MIN_PAIRS} clean pairs, set usable to false"
        )

    labels = [pair.label.strip() for pair in pairs]
    answers = [pair.answer.strip() for pair in pairs]

    if any(not label for label in labels):
        problems.append("a category has no name")
    if any(not answer for answer in answers):
        problems.append("a category has no answer")

    repeated_labels = _repeated(labels)
    if repeated_labels:
        problems.append(
            f"these categories appear more than once: {repeated_labels} -- each "
            "category may appear only once, so merge or drop the duplicate"
        )

    repeated_answers = _repeated(answers)
    if repeated_answers:
        problems.append(
            f"these answers appear more than once: {repeated_answers} -- every "
            "answer belongs to exactly one category, so replace the duplicate "
            "with a different answer or drop that pair entirely"
        )

    clash = _folded(answers) & _folded(labels)
    if clash:
        problems.append(
            f"these are used as both a category and an answer: {sorted(clash)} -- "
            "rename one of the two"
        )

    long_answers = [answer for answer in answers if len(answer.split()) > MAX_ITEM_WORDS]
    if long_answers:
        problems.append(
            f"these answers are longer than {MAX_ITEM_WORDS} words: {long_answers} -- "
            f"replace each with a short term of at most {MAX_ITEM_WORDS} words, or "
            "drop that pair"
        )

    return problems


def _folded(values: list[str]) -> set[str]:
    return {value.casefold() for value in values}


def _repeated(values: list[str]) -> list[str]:
    """The values that occur more than once, in their original spelling.

    Case-insensitive, because 'Wasser' and 'wasser' are the same answer to a
    player, but reported as written so the model can find them in its own reply.
    """
    seen: dict[str, str] = {}
    repeated: dict[str, str] = {}
    for value in values:
        key = value.casefold()
        if key in seen:
            repeated[key] = seen[key]
        else:
            seen[key] = value
    return sorted(repeated.values())


def only_needs_more_pairs(question, problems: list[str]) -> bool:
    """True when the single thing wrong with `question` is that it is short.

    Used to decide whether looking for pairs in other articles could possibly
    help. Adding pairs cannot fix a duplicate answer or a bad slug, so anything
    with a second complaint is not a candidate however few pairs it has.

    Asked of the question rather than parsed out of the complaint text: the
    wording of that message is tuned for the model to act on and has been
    rewritten twice, and a router that breaks when a sentence is reworded is a
    router that breaks silently.
    """
    return (
        question is not None
        and len(problems) == 1
        and len(question.pairs) < MIN_PAIRS
    )
