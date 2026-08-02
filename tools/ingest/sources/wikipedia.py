"""Reading Wikipedia: what is popular, and what an article says.

Two Wikimedia APIs are used:

* the pageviews API, for the most-read articles on a given day
* the REST summary/content endpoints, for an article's text and canonical URL

The canonical URL always comes back *from* the API rather than being assembled
from a title. Titles get normalised, redirected and percent-encoded in ways that
are easy to get subtly wrong, and a source link that 404s is worse than none.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_USER_AGENT = "quiz-quiz/0.1 (https://github.com/example/quiz-quiz)"

BORING_PREFIXES = (
    "Spezial:",
    "Hauptseite",
    "Wikipedia:",
    "Portal:",
    "Datei:",
    "Kategorie:",
    "Hilfe:",
    "Diskussion:",
    "Benutzer:",
    "Vorlage:",
    "Special:",
    "Main_Page",
)

BORING_SUFFIXES = (".php", ".phtml", ".html", ".htm", ".js", ".css")

BLOCKED_TITLES = frozenset(
    {
        "sex",
        "geschlechtsverkehr",
        "pornografie",
        "pornographie",
        "masturbation",
        "oralverkehr",
        "analverkehr",
        "vagina",
        "penis",
        "vulva",
        "brust",
        "sexuelle_orientierung",
    }
)

BLOCKED_SUBSTRINGS = ("porn", "xhamster", "xvideos", "xnxx", "onlyfans", "erotik")


def is_article_title(title: str) -> bool:
    """A real article, rather than a namespace page or an asset path."""
    if not title or title.startswith(BORING_PREFIXES):
        return False
    return not title.lower().endswith(BORING_SUFFIXES)


def is_quiz_material(title: str) -> bool:
    """A real article that also belongs in a general-audience quiz."""
    if not is_article_title(title):
        return False
    lowered = title.lower()
    if lowered in BLOCKED_TITLES:
        return False
    return not any(bad in lowered for bad in BLOCKED_SUBSTRINGS)


BIOGRAPHY_CATEGORIES = ("Kategorie:Mann", "Kategorie:Frau", "Kategorie:Geboren", "Kategorie:Gestorben")


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    summary: str
    extract: str
    categories: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """Everything the model gets to read about this article."""
        return f"{self.summary}\n\n{self.extract}".strip()

    @property
    def is_biography(self) -> bool:
        """A person's life story, which makes poor Zuordnungs material.

        A matching question needs several categories each holding two or more
        members of the same kind. A biography has no such structure: asked for
        one anyway, the model either declines or invents categories to fill the
        shape. Detecting it here saves the two or three minutes a model call
        costs on CPU.
        """
        return any(c.startswith(BIOGRAPHY_CATEGORIES) for c in self.categories)


def _months_back(year: int, month: int, offset: int) -> tuple[int, int]:
    """`offset` whole months before `year`/`month`."""
    index = (year * 12 + month - 1) - offset
    return divmod(index, 12)[0], divmod(index, 12)[1] + 1


class WikipediaError(RuntimeError):
    pass


class WikipediaClient:
    """Minimal Wikimedia client with polite pacing and retry-on-429.

    Rate limiting is not hypothetical here: fetching a few dozen articles back
    to back reliably trips 429s, and the API answers them without a Retry-After
    header, so the backoff below is what keeps a run alive.
    """

    def __init__(
        self,
        *,
        lang: str = "de",
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: float = 0.5,
        timeout: float = 25.0,
        max_attempts: int = 5,
        cache_dir: Path | None = None,
    ) -> None:
        self.lang = lang
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.cache_dir = cache_dir
        self._last_call = 0.0
        self._pacing = threading.Lock()

    def _get(self, url: str) -> dict:
        for attempt in range(1, self.max_attempts + 1):
            with self._pacing:
                gap = time.monotonic() - self._last_call
                if gap < self.min_interval:
                    time.sleep(self.min_interval - gap)
                self._last_call = time.monotonic()

            request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self._last_call = time.monotonic()
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                self._last_call = time.monotonic()
                if exc.code == 404:
                    raise WikipediaError(f"Not found: {url}") from exc
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self.max_attempts:
                    raise WikipediaError(f"HTTP {exc.code} for {url}") from exc
            except urllib.error.URLError as exc:
                self._last_call = time.monotonic()
                if attempt == self.max_attempts:
                    raise WikipediaError(f"Network error for {url}: {exc.reason}") from exc

            time.sleep(2.0 * attempt)

        raise WikipediaError(f"Gave up on {url}")

    def top_titles(self, *, day: datetime | None = None, limit: int = 50) -> list[str]:
        """Most-read articles for a day, cleaned of namespace and meta pages.

        Defaults to two days ago: the pageviews API publishes on a lag, and
        "yesterday" is often not ready yet.
        """
        day = day or datetime.now(UTC) - timedelta(days=2)
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
            f"{self.lang}.wikipedia/all-access/"
            f"{day.year}/{day.month:02d}/{day.day:02d}"
        )
        payload = self._get(url)
        try:
            rows = payload["items"][0]["articles"]
        except (KeyError, IndexError) as exc:
            raise WikipediaError("Unexpected pageviews payload") from exc

        titles: list[str] = []
        for row in rows:
            title = row.get("article", "")
            if not is_article_title(title):
                continue
            titles.append(title)
            if len(titles) >= limit:
                break
        return titles

    def category_members(self, category: str, *, limit: int = 500) -> list[str]:
        """Article titles filed directly under a category.

        Namespace 0 only, so subcategories are not returned -- which means a
        pure container category comes back empty rather than as a list of
        categories. `strategies.py` only names categories verified to hold
        articles directly.

        Paged. The API caps one response at 500 members, and the categories that
        matter most are far larger than that: `Wikipedia:Exzellent` and
        `:Lesenswert` hold several thousand between them, and without following
        `cmcontinue` the peer-reviewed pool silently stops at 500 each -- a
        ceiling that looks like a small category rather than a truncated one.
        """
        if not category.startswith("Kategorie:"):
            category = f"Kategorie:{category}"

        titles: list[str] = []
        cursor: str | None = None

        while len(titles) < limit:
            params = {
                "action": "query",
                "format": "json",
                "list": "categorymembers",
                "cmtitle": category,
                "cmlimit": "500",
                "cmnamespace": "0",
            }
            if cursor:
                params["cmcontinue"] = cursor

            payload = self._get(
                f"https://{self.lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
            )
            members = payload.get("query", {}).get("categorymembers", [])
            titles += [
                m["title"]
                for m in members
                if is_quiz_material(m.get("title", "").replace(" ", "_"))
            ]

            cursor = (payload.get("continue") or {}).get("cmcontinue")
            if not cursor or not members:
                break

        return titles[:limit]

    def popular_titles(
        self,
        *,
        months: int = 24,
        limit: int = 200,
        day_of_month: int = 15,
        keep: "Callable[[str], bool] | None" = None,
    ) -> list[str]:
        """Articles that stayed popular, sampled one day per month.

        `top_titles` answers "what is being read right now", which on any given
        day is mostly people in the news -- and a biography is close to the worst
        source for a Zuordnungsfrage, because there is no set of categories with
        several members each to sort.

        This asks a different question: **what is read every month, year after
        year?** Ranking by the number of months an article appears in, rather
        than by views, is what separates the two. A news story spikes enormously
        in one month and vanishes; `Deutschland`, `Periodensystem` and
        `Wolfgang Amadeus Mozart` show up in all of them. Total views only break
        ties.

        One day per month rather than every day: the ranking barely moves for
        30x the requests, and the API rate-limits hard enough that the
        difference is minutes against hours.
        """
        appearances: dict[str, int] = {}
        views: dict[str, int] = {}
        today = datetime.now(UTC)

        for offset in range(1, months + 1):
            year, month = _months_back(today.year, today.month, offset)
            try:
                rows = self._daily_top(year, month, day_of_month)
            except WikipediaError:
                continue
            for title, count in rows:
                appearances[title] = appearances.get(title, 0) + 1
                views[title] = views.get(title, 0) + count

        ranked = sorted(
            appearances,
            key=lambda title: (-appearances[title], -views[title], title),
        )
        if keep is not None:
            ranked = [title for title in ranked if keep(title)]
        return ranked[:limit]

    def _daily_top(self, year: int, month: int, day: int) -> list[tuple[str, int]]:
        """One day's chart, filtered. Cached on disk: history does not change.

        The cache is what makes this usable at all. Two dozen calls in a row
        reliably trip the rate limiter, and every retry costs a backoff sleep --
        but a past day's pageview counts are immutable, so a day fetched once
        never needs fetching again.
        """
        cached = self._read_cache(year, month, day)
        if cached is not None:
            return cached

        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
            f"{self.lang}.wikipedia/all-access/{year}/{month:02d}/{day:02d}"
        )
        payload = self._get(url)
        try:
            articles = payload["items"][0]["articles"]
        except (KeyError, IndexError) as exc:
            raise WikipediaError("Unexpected pageviews payload") from exc

        rows = [
            (row["article"], int(row.get("views", 0)))
            for row in articles
            if is_quiz_material(row.get("article", ""))
        ]
        self._write_cache(year, month, day, rows)
        return rows

    def _cache_file(self, year: int, month: int, day: int) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"top-{self.lang}-{year}{month:02d}{day:02d}.json"

    def _read_cache(self, year: int, month: int, day: int) -> list[tuple[str, int]] | None:
        path = self._cache_file(year, month, day)
        if path is None or not path.exists():
            return None
        try:
            return [(t, int(v)) for t, v in json.loads(path.read_text(encoding="utf-8"))]
        except (ValueError, TypeError):
            return None

    def _write_cache(self, year: int, month: int, day: int, rows: list[tuple[str, int]]) -> None:
        path = self._cache_file(year, month, day)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def article(self, title: str) -> Article:
        """Summary + lead extract for one article, with its canonical URL."""
        quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")

        summary = self._get(
            f"https://{self.lang}.wikipedia.org/api/rest_v1/page/summary/{quoted}"
        )
        if summary.get("type", "").endswith("not_found"):
            raise WikipediaError(f"No such article: {title}")

        query = self._get(
            f"https://{self.lang}.wikipedia.org/w/api.php?"
            + urllib.parse.urlencode(
                {
                    "action": "query",
                    "format": "json",
                    "prop": "extracts|categories",
                    "explaintext": "1",
                    "exsectionformat": "plain",
                    "cllimit": "500",
                    "redirects": "1",
                    "titles": title.replace("_", " "),
                }
            )
        )
        pages = query.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {}) if pages else {}

        return Article(
            title=summary["titles"]["normalized"],
            url=summary["content_urls"]["desktop"]["page"],
            summary=summary.get("extract", ""),
            extract=page.get("extract", ""),
            categories=tuple(c.get("title", "") for c in page.get("categories", [])),
        )
