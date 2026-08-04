"""The seams between the pipeline and where its material comes from.

Everything below `pipeline/` used to import Wikipedia directly. That was fine
while Wikipedia was the only source and stopped being fine the moment a second
one was wanted, so the pipeline now talks to two protocols and nothing else.

**`Source`** is where documents come from -- what to try, how to fetch one, and
whether to bother. The "whether to bother" part belongs here rather than in the
run loop because it is entirely source-specific: skipping biographies is a
judgement about Wikipedia's category system, and a different source would have
different reasons and no `Kategorie:Mann` to test against.

**`ImageProvider`** answers one question: given these labels, which of
them can be illustrated, and under what licence? It is separate from `Source`
because the two are genuinely independent -- pictures for a Wikipedia article's
answers come from Wikidata and Commons, not from Wikipedia, and a future source
might have text from one place and pictures from another.

These are `Protocol`s rather than base classes on purpose: an implementation
does not import this module, it just has the right shape. That keeps the
dependency pointing one way -- the pipeline depends on the shape, the sources
depend on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Image:
    """A picture and everything needed to show it legally.

    The credit travels with the file because it is a licence obligation, not a
    caption: most Commons images are CC BY-SA and cannot be displayed without
    attribution. An `Image` that lost its licence somewhere is one that cannot
    be used, so they are one object rather than four fields that might get
    separated.

    `file` is a provider-specific identifier, not a URL -- Commons thumbnails
    live at a hash-derived path that cannot be computed from the name, so the
    name is what survives storage and the URL is built where it is rendered.
    """

    file: str
    licence: str
    credit: str | None = None
    licence_url: str | None = None


@dataclass(frozen=True)
class Document:
    """One piece of source material, as the pipeline sees it.

    Deliberately thin. The pipeline reads `title`, `text` and `url`; everything
    a particular source knows beyond that goes in `metadata` and is never read
    above the source layer. Wikipedia puts its categories there, which is how
    `skip_reason` can identify a biography without the pipeline ever learning
    that Wikipedia has categories.
    """

    id: str
    title: str
    url: str
    text: str
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class Source(Protocol):
    """Where documents come from, and which ones are worth trying."""

    def candidates(self, *, limit: int, **options) -> list[str]:
        """References to try, best first. A reference means something only to
        this source -- a title, an id, a URL."""
        ...

    def fetch(self, ref: str) -> Document:
        """Retrieve one document. Raises on a reference that cannot be read."""
        ...

    def skip_reason(self, document: Document) -> str | None:
        """Why this document is not worth a model call, or None to proceed.

        Runs before anything expensive. The reasons are the source's own --
        Wikipedia skips biographies and adult topics; another source would have
        its own list and none of this one's.
        """
        ...


@runtime_checkable
class RelatedDocuments(Protocol):
    """Where to look when one document does not hold enough pairs.

    Separate from `Source` on purpose. `Source` answers "what should we try
    next", which is a question about a whole run; this answers "what else is
    about *this*", which is a question about one document and needs a query.
    A source that can enumerate candidates cannot necessarily search, and a
    search index could implement this without being a `Source` at all.
    """

    def related(self, document: Document, *, query: str, limit: int) -> list[Document]:
        """Documents likely to hold more pairs of the same kind as `document`.

        Best first, `document` itself excluded, at most `limit` of them. An
        empty list is a normal answer -- most articles have no useful neighbour,
        and the caller treats that as "leave the question as it is".
        """
        ...


@runtime_checkable
class ImageProvider(Protocol):
    """Which answers can be illustrated, and under what licence."""

    def images_for(self, labels: list[str], *, document: Document) -> dict[str, Image]:
        """Map labels to pictures. A label with no usable picture is absent.

        `document` is passed so a provider can use it to disambiguate: "Titan"
        means different things in an article about Saturn and one about metals,
        and the document is the only context that distinguishes them.

        Absent rather than None-valued, so `len(result)` is the coverage and a
        caller cannot accidentally treat "no picture" as a picture.
        """
        ...
