"""The house style, as worked examples rather than adjectives.

`supabase/seed.sql` holds the questions this project started with: written by
hand, read back, played. They are the only statement of what a good
Zuordnungsfrage looks like here that is not an opinion, so the prompts teach
style by *showing* them instead of describing them -- a rule like "make the
title snappy" is unactionable for a 9B model, while four real titles are not.

Everything below is copied verbatim from that file. `tests/test_examples.py`
reads the seed back and fails if a word drifts, because an exemplar that no
longer matches the pool teaches a style nothing else in the project uses.

Two things the examples are deliberately *not* allowed to teach:

* **How many pairs.** The seed's boards hold seven or eight; this pipeline's
  floor is `MIN_PAIRS`. So the pairs are shown abbreviated and the block says so
  -- an example may not appear to endorse a count the validator would reject.
* **Content.** The prompts say so in as many words. A model shown "Berlin" and
  asked about coffee will offer Berlin if it is not told otherwise.

What the four are chosen to demonstrate, between them: all three difficulties,
four subjects, both title shapes (`X & Y` and a plain plural), and four
different question openings -- because the failure this addresses is a pipeline
that writes every question the same way, whatever the article.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.rules import MAX_PAIRS, MIN_PAIRS


@dataclass(frozen=True)
class Example:
    """One seed question, in the fields the extract step has to fill."""

    subject_slug: str
    difficulty: str
    slug: str
    title: str
    description: str
    pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExplainedPair:
    """One pairing and the line shown under its answer after the round."""

    label: str
    answer: str
    why: str


EXAMPLES: tuple[Example, ...] = (
    Example(
        subject_slug="geografie",
        difficulty="easy",
        slug="hauptstaedte-europas",
        title="Hauptstädte Europas",
        description="Welche Stadt ist die Hauptstadt des Landes?",
        pairs=(
            ("Deutschland", "Berlin"),
            ("Frankreich", "Paris"),
            ("Italien", "Rom"),
            ("Spanien", "Madrid"),
        ),
    ),
    Example(
        subject_slug="naturwissenschaft",
        difficulty="medium",
        slug="chemische-elemente",
        title="Chemische Elemente",
        description="Welches Symbol steht für das Element?",
        pairs=(
            ("Sauerstoff", "O"),
            ("Eisen", "Fe"),
            ("Gold", "Au"),
            ("Kupfer", "Cu"),
        ),
    ),
    Example(
        subject_slug="kunst-kultur",
        difficulty="medium",
        slug="gemaelde-maler",
        title="Gemälde & Maler",
        description="Wer hat das Gemälde gemalt?",
        pairs=(
            ("Mona Lisa", "Leonardo da Vinci"),
            ("Guernica", "Pablo Picasso"),
            ("Der Schrei", "Edvard Munch"),
            ("Der Kuss", "Gustav Klimt"),
        ),
    ),
    Example(
        subject_slug="musik",
        difficulty="hard",
        slug="komponisten-epochen",
        title="Komponisten & Epochen",
        description="In welcher Epoche komponierte er?",
        pairs=(
            ("Johann Sebastian Bach", "Barock"),
            ("Frédéric Chopin", "Romantik"),
            ("Claude Debussy", "Impressionismus"),
            ("Arnold Schönberg", "Moderne"),
        ),
    ),
)


EXPLANATION_EXAMPLES: tuple[ExplainedPair, ...] = (
    ExplainedPair("Deutschland", "Berlin", "Hauptstadt seit 1990, Regierungssitz seit 1999."),
    ExplainedPair("Gold", "Au", "Vom lateinischen aurum."),
    ExplainedPair("Saturn", "Titan", "Einziger Mond mit dichter Atmosphäre."),
    ExplainedPair("Guernica", "Pablo Picasso", "1937 gegen die Bombardierung der Stadt gemalt."),
    ExplainedPair(
        "Frankreich", "Ludwig XIV.", "Der Sonnenkönig regierte 72 Jahre von Versailles aus."
    ),
    ExplainedPair(
        "Pizza Margherita", "Italien", "1889 in Neapel nach Königin Margherita benannt."
    ),
)


PAIRS_SHOWN = 4

ABBREVIATED = f"... (hier gekürzt -- deine Frage braucht {MIN_PAIRS} bis {MAX_PAIRS} Paare)"


def render_questions(examples: tuple[Example, ...] = EXAMPLES, *, shown: int = PAIRS_SHOWN) -> str:
    """The exemplars as the extract prompt shows them.

    Laid out as the fields of the reply rather than as JSON: the grammar already
    forces the JSON, so spending tokens on braces buys nothing, and a field list
    is harder to copy wholesale than a finished object.
    """
    blocks = []
    for number, example in enumerate(examples, start=1):
        lines = [
            f"Beispiel {number}  (subject_slug: {example.subject_slug}, "
            f"difficulty: {example.difficulty})",
            f"  slug:        {example.slug}",
            f"  title:       {example.title}",
            f"  description: {example.description}",
        ]
        for index, (label, answer) in enumerate(example.pairs[:shown]):
            lead = "  pairs:       " if index == 0 else "               "
            lines.append(f"{lead}{label} -> {answer}")
        lines.append(f"               {ABBREVIATED}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_explanations(pairs: tuple[ExplainedPair, ...] = EXPLANATION_EXAMPLES) -> str:
    """The exemplars as the explain prompt shows them.

    The pair is written the way `_render_pairs` writes the real ones, so the
    model is mapping between the two shapes it will actually be given rather
    than translating an example format into the live one.
    """
    return "\n\n".join(
        f"  {pair.label} -> {pair.answer}\n      {pair.answer}: {pair.why}" for pair in pairs
    )
