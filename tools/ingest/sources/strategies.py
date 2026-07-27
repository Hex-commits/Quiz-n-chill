"""Choosing which articles to try, and in what order.

`wikipedia.py` knows how to talk to the API; this module knows what to ask it
for. The two are separate because the transport is stable and the policy is not
-- which articles make good Zuordnungs material is a question we are still
learning the answer to.

A Zuordnungsfrage needs several categories, each holding two or more members of
the same kind. That single requirement is what separates a good source from a
bad one, and each strategy below attacks it differently:

* `subjects` -- a Wikipedia category *is* the grouping. Nothing else gives the
  structure this directly, and it is the only strategy that can balance across
  the quiz's own subjects.
* `lists`    -- a list article is already a table of pairings.
* `vetted`   -- peer-reviewed for accuracy, so the facts can be trusted.
* `evergreen`-- read every month for years, so the topic is worth knowing.
* `recent`   -- what is being read today. Mostly people in the news.
* `mixed`    -- round-robin over the first four (the default).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .wikipedia import WikipediaClient, WikipediaError

# Categories that hold articles *directly* -- verified against the live API, not
# guessed. German Wikipedia uses many pure container categories whose members
# are all subcategories; those come back empty from a namespace-0 query and are
# useless here, which is why the obvious names (`Kategorie:Epoche`,
# `Kategorie:Speise`, `Kategorie:Säugetier`) are absent.
SUBJECT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "geografie": ("Staat in Europa", "Hauptstadt in Europa", "Staat in Afrika"),
    "geschichte": ("Friedensvertrag", "Historisches Territorium (Europa)", "Zeitalter"),
    "naturwissenschaft": ("Chemisches Element", "Planet des Sonnensystems", "Physikalische Größe"),
    "kunst-kultur": ("Kunststil", "Baustil"),
    "sport": ("Olympische Sportart", "Ballsportart", "Sportart"),
    "technik": ("Programmiersprache", "Werkstoff", "Kraftfahrzeugtechnik"),
    "musik": ("Musikgenre", "Tonart", "Musikinstrument"),
    "film-fernsehen": ("Filmgenre", "Filmpreis"),
    "essen-trinken": ("Käsesorte", "Backware", "Getränk"),
}

# Peer-reviewed on German Wikipedia: checked by other editors for accuracy and
# completeness. The best sources available, at the cost of skewing obscure.
VETTED_CATEGORIES = ("Wikipedia:Exzellent", "Wikipedia:Lesenswert")

# German list articles are titled "Liste der ...", "Liste von ...".
LIST_PREFIXES = ("Liste_", "Liste ")


def is_list_article(title: str) -> bool:
    return title.startswith(LIST_PREFIXES)


# -- the strategies ------------------------------------------------------


def recent(wiki: WikipediaClient, *, limit: int, **_: object) -> list[str]:
    """Most-read two days ago. Topical, but half of it is people in the news."""
    return wiki.top_titles(limit=limit)


def evergreen(wiki: WikipediaClient, *, limit: int, months: int = 24, **_: object) -> list[str]:
    """Read every month for years -- general knowledge rather than news."""
    return wiki.popular_titles(months=months, limit=limit)


def lists(wiki: WikipediaClient, *, limit: int, months: int = 24, **_: object) -> list[str]:
    """Evergreen ranking, narrowed to list articles.

    The intersection is what makes this good. Raw prefix search over every
    "Liste der ..." page is dominated by the hyper-specific (`Liste der
    .NET-Sprachen`); ranking those same articles by staying power leaves
    `Liste der Staaten der Erde` and `Liste der Präsidenten der Vereinigten
    Staaten` on top -- popular *and* already tabulated into pairings.
    """
    return wiki.popular_titles(months=months, limit=limit, keep=is_list_article)


def vetted(wiki: WikipediaClient, *, limit: int, **_: object) -> list[str]:
    """Articles German Wikipedia has peer-reviewed as Exzellent or Lesenswert."""
    return _round_robin(
        (_members(wiki, category) for category in VETTED_CATEGORIES), limit=limit
    )


def subjects(
    wiki: WikipediaClient,
    *,
    limit: int,
    subject_slugs: Iterable[str] = (),
    **_: object,
) -> list[str]:
    """Category members, drawn evenly across the quiz's own subjects.

    The only strategy that controls the *balance* of the pool. Popularity
    sampling gives no say in it at all, and the game deals rounds evenly across
    subjects -- so a pool that is four-fifths geography makes for a poor game
    however good the individual questions are.

    Subjects are interleaved rather than concatenated, so a short run still
    touches all nine instead of exhausting the first.
    """
    wanted = [slug for slug in subject_slugs if slug in SUBJECT_CATEGORIES]
    if not wanted:
        wanted = list(SUBJECT_CATEGORIES)

    per_subject = [
        _round_robin(
            (_members(wiki, category) for category in SUBJECT_CATEGORIES[slug]),
            limit=limit,
        )
        for slug in wanted
    ]
    return _round_robin(per_subject, limit=limit)


def mixed(wiki: WikipediaClient, *, limit: int, **kwargs: object) -> list[str]:
    """One from each strategy in turn: structure, tables, accuracy, popularity.

    No single source is best. Categories give structure but no sense of what is
    worth knowing; popularity gives the opposite. Interleaving means a run that
    stops early still saw all four kinds.
    """
    pools = [
        subjects(wiki, limit=limit, **kwargs),
        lists(wiki, limit=limit, **kwargs),
        vetted(wiki, limit=limit, **kwargs),
        evergreen(wiki, limit=limit, **kwargs),
    ]
    return _round_robin(pools, limit=limit)


STRATEGIES: dict[str, Callable[..., list[str]]] = {
    "mixed": mixed,
    "subjects": subjects,
    "lists": lists,
    "vetted": vetted,
    "evergreen": evergreen,
    "recent": recent,
}


def candidates(name: str, wiki: WikipediaClient, **kwargs: object) -> list[str]:
    """Run one strategy by name."""
    try:
        strategy = STRATEGIES[name]
    except KeyError:
        raise ValueError(f"Unknown strategy {name!r}. Try one of {sorted(STRATEGIES)}.") from None
    return strategy(wiki, **kwargs)


# -- helpers -------------------------------------------------------------


def _members(wiki: WikipediaClient, category: str) -> list[str]:
    """Category members, or nothing. One dead category must not end a run."""
    try:
        return wiki.category_members(category)
    except WikipediaError:
        return []


def _round_robin(pools: Iterable[Iterable[str]], *, limit: int) -> list[str]:
    """Take one from each pool in turn, skipping duplicates and exhausted pools."""
    iterators = [iter(pool) for pool in pools]
    seen: set[str] = set()
    out: list[str] = []

    while iterators and len(out) < limit:
        for iterator in list(iterators):
            try:
                title = next(iterator)
            except StopIteration:
                iterators.remove(iterator)
                continue
            if title in seen:
                continue
            seen.add(title)
            out.append(title)
            if len(out) >= limit:
                break
    return out
