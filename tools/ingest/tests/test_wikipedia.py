import pytest

from tools.ingest.sources.wikipedia import Article, is_article_title


@pytest.mark.parametrize(
    "title",
    ["Berlin", "Jürgen_Klopp", "Liste_der_größten_Auslegerbrücken", "Die_Odyssee_(2026)"],
)
def test_real_articles_are_kept(title):
    assert is_article_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "",
        "Hauptseite",
        "Spezial:Suche",
        "Wikipedia:Impressum",
        "Portal:Sport",
        "Datei:Foo.jpg",
        "Kategorie:Physik",
        # Not articles at all -- these really do appear in the top-views list.
        "wiki.phtml",
        "index.php",
        "load.php",
    ],
)
def test_namespace_and_script_paths_are_dropped(title):
    assert not is_article_title(title)


def test_article_text_joins_summary_and_extract():
    article = Article(
        title="Berlin",
        url="https://de.wikipedia.org/wiki/Berlin",
        summary="Berlin ist die Hauptstadt Deutschlands.",
        extract="Berlin ist mit rund 3,7 Millionen Einwohnern...",
    )
    assert article.text.startswith("Berlin ist die Hauptstadt")
    assert "3,7 Millionen" in article.text


def test_article_text_survives_a_missing_extract():
    article = Article(title="X", url="https://example.test/X", summary="Nur die Zusammenfassung.", extract="")
    assert article.text == "Nur die Zusammenfassung."


# -- picking articles worth a model call ---------------------------------


def test_adult_topics_are_not_quiz_material():
    """They sit permanently near the top of the German pageview charts, and
    this is a general-audience quiz."""
    from tools.ingest.sources.wikipedia import is_quiz_material

    assert not is_quiz_material("Pornhub")
    assert not is_quiz_material("XHamster")
    assert not is_quiz_material("Geschlechtsverkehr")


def test_ordinary_articles_survive_the_blocklist():
    """A blocklist that eats real topics is worse than none."""
    from tools.ingest.sources.wikipedia import is_quiz_material

    for title in ("Deutschland", "Periodensystem", "Photosynthese", "Bordeaux",
                  "Liste_der_größten_Auslegerbrücken", "Sexualität_der_Pflanzen"):
        assert is_quiz_material(title), title


def test_namespace_pages_are_still_excluded():
    from tools.ingest.sources.wikipedia import is_quiz_material

    assert not is_quiz_material("Spezial:Suche")
    assert not is_quiz_material("index.php")


def test_a_biography_is_recognised_from_its_categories():
    """Every German Wikipedia biography carries a birth year and a gender."""
    person = Article(
        title="Jürgen Klopp", url="u", summary="s", extract="e",
        categories=("Kategorie:Geboren 1967", "Kategorie:Mann", "Kategorie:Fußballtrainer"),
    )

    assert person.is_biography


def test_a_topic_article_is_not_a_biography():
    topic = Article(
        title="Photosynthese", url="u", summary="s", extract="e",
        categories=("Kategorie:Pflanzenphysiologie", "Kategorie:Stoffwechsel"),
    )

    assert not topic.is_biography


def test_an_article_with_no_categories_is_not_assumed_to_be_a_person():
    assert not Article(title="X", url="u", summary="s", extract="e").is_biography


# -- ranking by staying power --------------------------------------------


def test_months_back_steps_across_a_year_boundary():
    from tools.ingest.sources.wikipedia import _months_back

    assert _months_back(2026, 7, 1) == (2026, 6)
    assert _months_back(2026, 1, 1) == (2025, 12)
    assert _months_back(2026, 7, 24) == (2024, 7)
    assert _months_back(2026, 3, 15) == (2024, 12)


def test_consistency_outranks_a_single_huge_spike(monkeypatch, tmp_path):
    """The whole point: a news story spikes once, general knowledge shows up
    every month. Ranking by views alone would invert this."""
    from tools.ingest.sources.wikipedia import WikipediaClient

    client = WikipediaClient(cache_dir=tmp_path)

    def fake_daily(year, month, day):
        # 'Skandal' appears once with enormous traffic; 'Deutschland' always.
        if (year, month) == (2026, 6):
            return [("Skandal", 5_000_000), ("Deutschland", 10_000)]
        return [("Deutschland", 10_000)]

    monkeypatch.setattr(client, "_daily_top", fake_daily)

    assert client.popular_titles(months=6, limit=5)[0] == "Deutschland"


def test_one_unavailable_month_does_not_lose_the_others(monkeypatch, tmp_path):
    from tools.ingest.sources.wikipedia import WikipediaClient, WikipediaError

    client = WikipediaClient(cache_dir=tmp_path)

    def flaky(year, month, day):
        if month % 2:
            raise WikipediaError("no data")
        return [("Deutschland", 10)]

    monkeypatch.setattr(client, "_daily_top", flaky)

    assert client.popular_titles(months=6, limit=5) == ["Deutschland"]


def test_a_fetched_day_is_cached_and_never_fetched_twice(tmp_path):
    """Past pageview counts are immutable, and the API rate-limits hard."""
    from tools.ingest.sources.wikipedia import WikipediaClient

    client = WikipediaClient(cache_dir=tmp_path)
    calls = []

    def counted(url):
        calls.append(url)
        return {"items": [{"articles": [
            {"article": "Deutschland", "views": 10},
            {"article": "Spezial:Suche", "views": 99},
        ]}]}

    client._get = counted

    assert client._daily_top(2025, 6, 15) == [("Deutschland", 10)]
    assert client._daily_top(2025, 6, 15) == [("Deutschland", 10)]
    assert len(calls) == 1  # second read came from disk


def test_a_corrupt_cache_file_is_ignored_rather_than_fatal(tmp_path):
    from tools.ingest.sources.wikipedia import WikipediaClient

    client = WikipediaClient(cache_dir=tmp_path)
    (tmp_path / "top-de-20250615.json").write_text("not json", encoding="utf-8")

    assert client._read_cache(2025, 6, 15) is None
