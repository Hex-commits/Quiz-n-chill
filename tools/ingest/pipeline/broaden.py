"""Reading the neighbours before an article is given up as too thin.

`extract` is allowed to decline an article, and it is *right* to: told to invent
nothing, a model handed four facts about one thing has no honest answer other
than `usable: false`. The prompt says so in as many words, and the decline stops
the graph immediately -- there is nothing a repair prompt could say, because the
material genuinely is not in the text.

But "not in *this* text" is not the same as "not there". The articles that
decline are overwhelmingly ones about a *single* member of an obvious class: one
army post, one lighthouse, one battle. A Zuordnungsfrage needs several members of
that class, and Wikipedia has an article about each of them.

So before the decline is taken as final, this step reads a couple of articles
Wikipedia considers similar and hands them to `extract` alongside the original.
The second pass is the same call with more to read.

**Why it is not `augment`.** That step tops up a question that already exists and
is short a pair or two; the question decides what to search for and every found
pair is judged against the board. Here there is no question yet -- the judgement
this step makes is only "what else is about this?", and whether anything usable
comes out of it is decided by `extract` in the ordinary way, against the same
rules and the same gates as any other article. Nothing here can put a pair on a
board.

**What it costs.** One search, `MAX_NEIGHBOURS` fetches and one more extract
call -- the most expensive call in the pipeline -- per declined article, and it
is bounded to a single round: an article that declines twice, once with its
neighbours in front of it, is an article about nothing worth pairing.

Nothing in this module calls a model or the network. The finder is passed in,
which is what lets the decision be tested against a stub.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..sources.protocols import Document, RelatedDocuments

# How many neighbours to read. Two, and the binding constraint is not the fetches
# -- it is that every one of them goes into the extract prompt on top of 6000
# characters of article, the four worked examples and room for five drafts. A
# third neighbour buys a little more material by spending the attention that has
# to write the questions.
MAX_NEIGHBOURS = 2

# Shorter than this and an article is a stub: a sentence and an infobox, which
# adds a title to the prompt and no facts to pair with.
MIN_USEFUL_CHARS = 300

# How many times one article may be widened. Once. The step exists to give a
# thin article the *class* it belongs to, and reading a second batch of
# neighbours after the first produced nothing is looking for a different article
# rather than a better reading of this one -- and there is another article.
MAX_ROUNDS = 1


@dataclass(frozen=True)
class Broadening:
    """The similar articles this step found, and what it did."""

    documents: tuple[Document, ...] = ()
    detail: str = ""

    @property
    def found(self) -> bool:
        return bool(self.documents)


def query_for(document: Document) -> str:
    """What to search for: the article's own title.

    Deliberately the plainest possible query. `augment` builds a richer one out
    of the question's title and category labels, because there it is looking for
    pairs of a *known* kind -- here there is no question yet and nothing has said
    what kind of thing this article is about, so anything more elaborate would be
    a guess about the class dressed up as a query. The title is what the search
    index already knows the article by, and "what else does this name turn up" is
    exactly the question being asked.
    """
    return document.title.strip()


def broaden(
    document: Document,
    finder: RelatedDocuments,
    *,
    max_neighbours: int = MAX_NEIGHBOURS,
    skip: set[str] | None = None,
    min_chars: int = MIN_USEFUL_CHARS,
) -> Broadening:
    """Find up to `max_neighbours` articles similar to `document`.

    Finding nothing is a normal answer and the common one for the articles that
    reach here -- the caller drops the article exactly as it would have without
    this step, one search poorer.

    `skip` holds titles already read, so a run that has been here before does not
    hand `extract` the same neighbour twice. More are requested to compensate,
    since the skipped ones would otherwise eat the budget.
    """
    query = query_for(document)
    if not query:
        return Broadening(detail="nothing to search for")

    skip = {title.casefold() for title in (skip or set())}
    neighbours = [
        doc
        for doc in finder.related(
            document, query=query, limit=max_neighbours + len(skip)
        )
        if doc.title.casefold() not in skip and len(doc.text.strip()) >= min_chars
    ][:max_neighbours]

    if not neighbours:
        return Broadening(
            detail="no unread similar articles" if skip else "no similar articles found"
        )

    return Broadening(
        documents=tuple(neighbours),
        detail=f"read {', '.join(doc.title for doc in neighbours)}",
    )
