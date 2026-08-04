"""Topping up a question that is worth keeping but came up short.

An article that yields eight clean pairs is not a bad article -- it is a good
question two pairs short of being playable. Before this step, `check` rejected
it for the pair count and `repair` asked the same model to find more in the same
text, which it cannot: the pairs are not in there. The article was dropped and
the eight good pairs went with it.

So when a question fails on the pair count *and nothing else*, the remaining
pairs are looked for in other articles instead.

**Why it is gated on difficulty.** Searching costs a search, several article
fetches and a model call each. That is worth paying for a question someone will
find interesting and not worth paying for one that was thin to begin with -- so
`easy` questions are left to fail. This is the one place in the pipeline that
spends effort in proportion to how good the thing already is.

**What it must not do** is quietly change what the question is about. A live run
offered a board of river lengths "Donau-Main-Wasserscheide -> Teile von
Süddeutschland" -- true, well-formed, and a different question.

Whether two pairs are the same kind of pairing is a judgement about meaning;
there is no string test for it that survives contact with a board of painters or
capitals. So it is not made here. It belongs to `vet`, which asks a model per
pair -- and `vet` is **off by default**, because that judgement measures at about
chance on `glm4:9b` (see the note there).

`review` does not catch it and cannot: drift is a property of the *set*, and
`review` is asked about pairs one at a time. `Donau -> Schwarzwald` on a board of
river lengths is correctly paired, unambiguous and factually true, so every check
the reviewer runs passes it. Homogeneity was tried in that prompt and the model
could not do it either; see the note in `prompts.py`.

So with `INGEST_VET` off, a borrowed pair reaching the board has been checked for
structure and for truth, and **not** for whether it belongs to this question. The
Markdown report says which questions borrowed and from where, and reading it
before `--commit` is what stands in for the judgement. The documents used are
carried out of here for that, and to put the supporting text in front of `review`
and `explain`.

Nothing in this module calls a model or the network. `find_pairs` is passed in,
which is what lets the whole decision be tested against a stub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..domain.models import GeneratedPair, GeneratedQuestion
from ..sources.protocols import Document, RelatedDocuments

# How many other articles to read at most. Each is a fetch plus a model call, so
# this is the cost ceiling for one augmentation; four is enough to top up a
# two-pair shortfall in practice and cheap enough to lose when it finds nothing.
MAX_DOCUMENTS = 4

# How much of a category label to put in the search query. Enough to be
# specific, short enough that the query is not one long phrase that matches
# nothing.
QUERY_LABELS = 3


@dataclass(frozen=True)
class Augmentation:
    """What `augment` managed to add, and where it came from."""

    pairs: tuple[GeneratedPair, ...] = ()
    # The documents the pairs were taken from. Carried so `review` can be shown
    # the text a pair is supposed to be supported by -- without this the
    # reviewer would judge every added pair against an article that does not
    # mention it, and reject the lot.
    documents: tuple[Document, ...] = ()
    detail: str = ""

    @property
    def found(self) -> bool:
        return bool(self.pairs)


def query_for(question: GeneratedQuestion) -> str:
    """What to search other articles for.

    The title says what the question is about and the category names say what
    kind of thing is being paired, which together are a better query than either
    -- "Flüsse Europas" alone finds the same article back, and bare labels find
    whatever else happens to share a name.
    """
    labels = [pair.label.strip() for pair in question.pairs[:QUERY_LABELS]]
    return " ".join([question.title.strip(), *labels]).strip()


def taken(question: GeneratedQuestion) -> set[str]:
    """Every name already on the board, folded for comparison.

    Labels and answers together, because a pairing is one-to-one in both
    directions: an added pair whose category is already an *answer* would break
    `no answer reuses a category label` just as surely as a duplicate label.
    """
    return {
        text.strip().casefold()
        for pair in question.pairs
        for text in (pair.label, pair.answer)
    }


def fresh_pairs(
    question: GeneratedQuestion,
    candidates: list[GeneratedPair],
    *,
    already: set[str] | None = None,
) -> list[GeneratedPair]:
    """The candidates that can actually be added, in order.

    Drops anything naming something already on the board, anything that repeats
    within the batch, and anything self-referential. `validate` would catch all
    of these afterwards -- but as a *rejection*, throwing away the good pairs
    alongside the bad ones.

    Only structural rules live here. Whether a pair is the same *kind* of
    pairing as the rest is a judgement about meaning, and it belongs to
    `review`, which has a model to make it with.
    """
    seen = set(already or set()) | taken(question)
    keep: list[GeneratedPair] = []
    for pair in candidates:
        label, answer = pair.label.strip(), pair.answer.strip()
        if not label or not answer:
            continue
        low_label, low_answer = label.casefold(), answer.casefold()
        if low_label == low_answer:
            continue
        if low_label in seen or low_answer in seen:
            continue
        seen.add(low_label)
        seen.add(low_answer)
        keep.append(GeneratedPair(label=label, answer=answer))
    return keep


def augment(
    question: GeneratedQuestion,
    document: Document,
    finder: RelatedDocuments,
    find_pairs: Callable[[Document, int], list[GeneratedPair]],
    *,
    needed: int,
    max_documents: int = MAX_DOCUMENTS,
    skip: set[str] | None = None,
) -> Augmentation:
    """Look for `needed` more pairs in documents other than `document`.

    Reads other articles one at a time and stops the moment it has enough, so
    the common case -- a question two pairs short, topped up from the first
    neighbour -- costs one fetch and one model call rather than four of each.

    A document that yields nothing is not an error; most will.

    `skip` holds titles a previous pass already read. It is what makes a second
    attempt look somewhere new rather than re-reading the article whose pairs
    were just rejected -- more are requested to compensate, since the skipped
    ones would otherwise eat the budget.
    """
    if needed <= 0:
        return Augmentation(detail="nothing needed")

    skip = {title.casefold() for title in (skip or set())}
    others = [
        doc
        for doc in finder.related(
            document, query=query_for(question), limit=max_documents + len(skip)
        )
        if doc.title.casefold() not in skip
    ][:max_documents]
    if not others:
        return Augmentation(
            detail="no unread related articles" if skip else "no related articles found"
        )

    gathered: list[GeneratedPair] = []
    used: list[Document] = []
    for other in others:
        if len(gathered) >= needed:
            break
        found = find_pairs(other, needed - len(gathered))
        keep = fresh_pairs(
            question, found, already={p.label.casefold() for p in gathered}
            | {p.answer.casefold() for p in gathered}
        )
        if not keep:
            continue
        gathered.extend(keep[: needed - len(gathered)])
        used.append(other)

    if not gathered:
        return Augmentation(
            detail=f"read {len(others)} article(s), no usable pairs"
        )

    where = ", ".join(doc.title for doc in used)
    return Augmentation(
        pairs=tuple(gathered),
        documents=tuple(used),
        detail=f"{len(gathered)}/{needed} pair(s) from {where}",
    )


def merge(question: GeneratedQuestion, extra: Augmentation) -> GeneratedQuestion:
    """The question with the found pairs appended.

    Appended rather than interleaved: position carries no meaning in a
    Zuordnung -- the board is dealt shuffled -- and keeping the article's own
    pairs first makes a run report readable when checking where a pair came
    from.
    """
    if not extra.found:
        return question
    return question.model_copy(update={"pairs": [*question.pairs, *extra.pairs]})
