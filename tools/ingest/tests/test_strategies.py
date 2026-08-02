"""Tests for candidate selection.

No network: the client is stubbed. What is being checked is the *policy* --
which pool a strategy draws from, and whether the interleaving keeps a short run
balanced.
"""

from __future__ import annotations

import pytest

from tools.ingest.sources import strategies
from tools.ingest.sources.strategies import (
    SUBJECT_CATEGORIES,
    STRATEGIES,
    candidates,
    is_list_article,
    _round_robin,
)
from tools.ingest.sources.wikipedia import WikipediaError


class StubClient:
    """Answers category and popularity queries from canned data."""

    def __init__(self, members=None, popular=None, top=None, fail=()):
        self.members = members or {}
        self.popular = popular or []
        self.top = top or []
        self.fail = set(fail)
        self.asked: list[str] = []

    def category_members(self, category, *, limit=500):
        self.asked.append(category)
        if category in self.fail:
            raise WikipediaError("boom")
        return list(self.members.get(category, []))[:limit]

    def popular_titles(self, *, months=24, limit=200, keep=None, **_):
        titles = self.popular if keep is None else [t for t in self.popular if keep(t)]
        return titles[:limit]

    def top_titles(self, *, limit=50):
        return self.top[:limit]



def test_a_list_article_is_recognised():
    assert is_list_article("Liste_der_Staaten_der_Erde")
    assert is_list_article("Liste der IPA-Zeichen")
    assert not is_list_article("Deutschland")
    assert not is_list_article("Liszt_Ferenc")


def test_the_lists_strategy_keeps_only_list_articles():
    """The intersection is the point: popular *and* already tabulated."""
    client = StubClient(popular=[
        "Deutschland", "Liste_der_Staaten_der_Erde", "ChatGPT",
        "Liste_der_IPA-Zeichen",
    ])

    assert strategies.lists(client, limit=10) == [
        "Liste_der_Staaten_der_Erde",
        "Liste_der_IPA-Zeichen",
    ]


def test_the_lists_strategy_preserves_the_popularity_order():
    client = StubClient(popular=["Liste_A", "Deutschland", "Liste_B"])

    assert strategies.lists(client, limit=10) == ["Liste_A", "Liste_B"]



def test_every_subject_maps_to_at_least_one_category():
    """A subject with no category can never be drawn from."""
    for slug, cats in SUBJECT_CATEGORIES.items():
        assert cats, slug


def test_the_subject_map_matches_the_database_subjects():
    """These nine slugs are what `subjects` returns from Supabase; a typo here
    silently drops a whole subject out of the pool."""
    assert set(SUBJECT_CATEGORIES) == {
        "geografie", "geschichte", "naturwissenschaft", "kunst-kultur", "sport",
        "technik", "musik", "film-fernsehen", "essen-trinken",
    }


def test_subjects_are_interleaved_so_a_short_run_touches_all_of_them():
    """Concatenating would spend a 6-article run entirely on geography."""
    client = StubClient(members={
        "Staat in Europa": ["Albanien", "Andorra", "Belgien"],
        "Chemisches Element": ["Wasserstoff", "Helium", "Lithium"],
    })

    out = strategies.subjects(
        client, limit=4, subject_slugs=["geografie", "naturwissenschaft"]
    )

    assert "Albanien" in out
    assert "Wasserstoff" in out


def test_an_unknown_subject_slug_is_ignored_rather_than_fatal():
    client = StubClient(members={"Staat in Europa": ["Albanien"]})

    out = strategies.subjects(client, limit=5, subject_slugs=["geografie", "nonsense"])

    assert out == ["Albanien"]


def test_no_usable_slugs_falls_back_to_every_subject():
    client = StubClient(members={"Käsesorte": ["Gouda"]})

    assert strategies.subjects(client, limit=5, subject_slugs=["nope"]) == ["Gouda"]


def test_one_dead_category_does_not_end_the_run():
    """Wikipedia categories get renamed; losing one must cost one category."""
    client = StubClient(
        members={"Hauptstadt in Europa": ["Athen"]},
        fail={"Staat in Europa"},
    )

    assert strategies.subjects(client, limit=5, subject_slugs=["geografie"]) == ["Athen"]



def test_vetted_draws_from_both_review_grades():
    client = StubClient(members={
        "Wikipedia:Exzellent": ["Exzellent-1"],
        "Wikipedia:Lesenswert": ["Lesenswert-1"],
    })

    out = strategies.vetted(client, limit=5)

    assert set(out) == {"Exzellent-1", "Lesenswert-1"}



def test_mixed_takes_from_every_strategy():
    client = StubClient(
        members={
            "Staat in Europa": ["Albanien"],
            "Wikipedia:Exzellent": ["Ein exzellenter Artikel"],
        },
        popular=["Deutschland", "Liste_der_Staaten_der_Erde"],
    )

    out = strategies.mixed(client, limit=10, subject_slugs=["geografie"])

    assert "Albanien" in out
    assert "Liste_der_Staaten_der_Erde" in out
    assert "Ein exzellenter Artikel" in out
    assert "Deutschland" in out


def test_mixed_never_repeats_an_article():
    """`Liste_der_Staaten_der_Erde` is both a list and evergreen."""
    client = StubClient(popular=["Liste_der_Staaten_der_Erde", "Deutschland"])

    out = strategies.mixed(client, limit=10)

    assert len(out) == len(set(out))



def test_every_named_strategy_is_callable():
    client = StubClient(popular=["Deutschland"], top=["Tagesthema"])

    for name in STRATEGIES:
        assert isinstance(candidates(name, client, limit=2, subject_slugs=["geografie"]), list)


def test_an_unknown_strategy_names_the_valid_ones():
    with pytest.raises(ValueError, match="mixed"):
        candidates("nonsense", StubClient(), limit=1)



def test_round_robin_alternates_and_respects_the_limit():
    assert _round_robin([["a1", "a2", "a3"], ["b1", "b2"]], limit=4) == ["a1", "b1", "a2", "b2"]


def test_round_robin_drains_the_remaining_pool_when_one_runs_out():
    assert _round_robin([["a1"], ["b1", "b2", "b3"]], limit=4) == ["a1", "b1", "b2", "b3"]


def test_round_robin_drops_duplicates_across_pools():
    assert _round_robin([["x", "a"], ["x", "b"]], limit=4) == ["x", "a", "b"]


def test_round_robin_survives_every_pool_being_empty():
    assert _round_robin([[], []], limit=5) == []
