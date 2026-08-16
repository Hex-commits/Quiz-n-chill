"""Reading the neighbours of an article that holds too little on its own.

No network anywhere here: the finder is a stub, which is the point of it being a
parameter. What is under test is the search and what comes back from it -- the
routing, which is the part that decides whether this runs at all, lives in
`test_graph.py`.

The step cannot ruin a question, because there is no question when it runs. The
ways it can waste a run are what the tests below are about: reading a stub, and
reading the same page twice.
"""

from __future__ import annotations

from tools.ingest.pipeline.broaden import (
    MIN_USEFUL_CHARS,
    Broadening,
    broaden,
    query_for,
)
from tools.ingest.sources.protocols import Document

TEXT = "Ein hinreichend langer Artikeltext. " * 20

ARTICLE = Document(
    id="1", title="Fort Carson", url="https://example.test/fort-carson", text=TEXT
)


def other(title: str, text: str = TEXT) -> Document:
    return Document(id=title, title=title, url=f"https://example.test/{title}", text=text)


class StubFinder:
    """A `RelatedDocuments` that hands back whatever it was constructed with."""

    def __init__(self, *documents: Document):
        self.documents = list(documents)
        self.queries: list[str] = []
        self.limits: list[int] = []

    def related(self, document, *, query: str, limit: int):
        self.queries.append(query)
        self.limits.append(limit)
        return [d for d in self.documents if d.title != document.title][:limit]


# -- the search --------------------------------------------------------------


def test_it_searches_for_the_article_by_name():
    """There is no question yet, so the title is the only thing anything knows
    about what this article is about."""
    finder = StubFinder(other("Fort Bragg"))

    broaden(ARTICLE, finder)

    assert finder.queries == ["Fort Carson"]


def test_the_neighbours_come_back_in_order():
    finder = StubFinder(other("Fort Bragg"), other("Fort Hood"))

    result = broaden(ARTICLE, finder)

    assert result.found
    assert [d.title for d in result.documents] == ["Fort Bragg", "Fort Hood"]
    assert "Fort Bragg" in result.detail


def test_no_more_neighbours_than_asked_for():
    """Every one of them goes into the extract prompt on top of the article."""
    finder = StubFinder(other("A"), other("B"), other("C"), other("D"))

    result = broaden(ARTICLE, finder, max_neighbours=2)

    assert len(result.documents) == 2


def test_finding_nothing_is_a_normal_answer():
    result = broaden(ARTICLE, StubFinder())

    assert not result.found
    assert "no similar articles found" in result.detail


def test_a_stub_is_not_worth_reading():
    """A sentence and an infobox adds a title to the prompt and no facts."""
    finder = StubFinder(other("Kurz", text="x" * (MIN_USEFUL_CHARS - 1)), other("Lang"))

    result = broaden(ARTICLE, finder)

    assert [d.title for d in result.documents] == ["Lang"]


def test_an_untitled_document_costs_no_search():
    finder = StubFinder(other("Fort Bragg"))

    result = broaden(Document(id="1", title="  ", url="u", text=TEXT), finder)

    assert not result.found
    assert finder.queries == []


# -- not reading the same page twice -----------------------------------------


def test_pages_already_read_are_skipped():
    """`skip` carries what `augment` borrowed from and what an earlier pass
    read -- handing `extract` the same neighbour twice buys nothing."""
    finder = StubFinder(other("Fort Bragg"), other("Fort Hood"))

    result = broaden(ARTICLE, finder, skip={"Fort Bragg"})

    assert [d.title for d in result.documents] == ["Fort Hood"]


def test_skipping_is_case_insensitive():
    finder = StubFinder(other("Fort Bragg"))

    assert not broaden(ARTICLE, finder, skip={"fort bragg"}).found


def test_more_are_requested_to_make_up_for_the_skipped_ones():
    """Otherwise the pages already read eat the budget and the search comes back
    empty having found plenty."""
    finder = StubFinder(other("Fort Bragg"))

    broaden(ARTICLE, finder, max_neighbours=2, skip={"A", "B"})

    assert finder.limits == [4]


def test_everything_read_already_says_so():
    finder = StubFinder(other("Fort Bragg"))

    result = broaden(ARTICLE, finder, skip={"Fort Bragg"})

    assert "no unread similar articles" in result.detail


def test_an_empty_broadening_is_not_found():
    assert not Broadening().found


def test_the_query_is_the_title_stripped():
    assert query_for(Document(id="1", title=" Fort Carson ", url="u", text="t")) == "Fort Carson"
