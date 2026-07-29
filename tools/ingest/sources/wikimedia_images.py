"""Finding a picture for an answer, via Wikidata and Commons.

An `ImageProvider` (see `protocols.py`). Given the labels a question's answers
carry -- "Mont Blanc", "Eisen", "Pont Neuf" -- it returns the ones that can be
illustrated, with the attribution needed to show them.

    label -> German Wikipedia article -> Wikidata item -> P18 -> Commons licence

**`P18` is why this is trustworthy.** It is a curated statement meaning "this is
an image of this thing", maintained by people. The alternative -- `pageimages`,
whatever picture happens to lead the article -- returns the *flag* of Berlin and
a photo montage for Rome, and shares one image between Salzburg, Vienna and
Vorarlberg. Nothing in this pipeline can look at a photograph, so where the
picture comes from is the entire quality argument.

Three guards against illustrating the wrong thing, because a wrong picture is
worse than no picture:

* **Exact title match.** Resolution goes through `titles=`, so an article must
  literally carry that name. A disambiguation page has no `P18` and drops out
  on its own, which is what saves "Titan".
* **The document's own links.** A resolution is only accepted if the article is
  linked from the source document. "Merkur" in an article about the solar system
  is the planet; in one about metals it is not, and the link tells them apart.
* **Current statements only.** See `_current_value`. Without it London's country
  is the Roman Empire.

Everything is batched at fifty -- the API limit -- and throttled, because
Wikidata rate-limits hard and a batch job has nowhere to be.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .protocols import Document, Image

DE_API = "https://de.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

BATCH = 50
THROTTLE_SECONDS = 1.5
DEFAULT_USER_AGENT = "quiz-quiz/0.1 (https://github.com/Hex-commits/Quiz-n-chill)"


class ImageLookupError(RuntimeError):
    """The lookup failed in a way worth reporting rather than retrying."""


class WikimediaImages:
    """The Wikidata + Commons implementation of `ImageProvider`."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        throttle: float = THROTTLE_SECONDS,
        require_link: bool = True,
    ):
        self._headers = {"User-Agent": user_agent}
        self._throttle = throttle
        self._last = 0.0
        # Off only for tests and for sources whose documents carry no links.
        self._require_link = require_link

    # -- transport ---------------------------------------------------------

    def _get(self, api: str, params: dict) -> dict:
        wait = self._throttle - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = f"{api}?{urllib.parse.urlencode({**params, 'format': 'json'})}"
        request = urllib.request.Request(url, headers=self._headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ImageLookupError(
                    "Wikimedia is rate limiting. Raise the throttle and try again."
                ) from exc
            raise ImageLookupError(f"{api} returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ImageLookupError(f"Cannot reach {api}: {exc.reason}") from exc
        finally:
            self._last = time.monotonic()

    # -- the protocol ------------------------------------------------------

    def images_for(self, labels: list[str], *, document: Document) -> dict[str, Image]:
        """Labels that can be illustrated, mapped to their picture."""
        if not labels:
            return {}

        allowed = self._linked_titles(document) if self._require_link else None
        qids = self._entity_ids(labels, allowed=allowed)
        if not qids:
            return {}

        files = self._image_files(qids)
        if not files:
            return {}

        rights = self._licences(sorted({file for file in files.values()}))
        return {
            label: Image(file=file, **rights[file])
            for label, file in files.items()
            if file in rights
        }

    # -- steps -------------------------------------------------------------

    def _linked_titles(self, document: Document) -> set[str]:
        """Every article the source document links to, casefolded.

        The disambiguation guard. One request per document regardless of how
        many answers it has, and a document with no links simply illustrates
        nothing rather than illustrating the wrong things.
        """
        titles: set[str] = set()
        params = {
            "action": "query",
            "prop": "links",
            "pllimit": "500",
            "plnamespace": "0",
            "titles": document.title,
        }
        while True:
            payload = self._get(DE_API, params)
            for page in payload.get("query", {}).get("pages", {}).values():
                titles |= {link["title"].casefold() for link in page.get("links") or []}
            if "continue" not in payload:
                return titles
            params.update(payload["continue"])

    def _entity_ids(
        self, labels: list[str], *, allowed: set[str] | None
    ) -> dict[str, str]:
        """Label -> Wikidata QID, for labels that resolve to a real article.

        `redirects=1` means "Mount Everest" finds "Mount Everest" however the
        article is filed. `normalized` and `redirects` in the reply are how a
        resolved page is traced back to the label that asked for it -- without
        that mapping the results cannot be matched up again.
        """
        found: dict[str, str] = {}
        for chunk in _chunks(labels, BATCH):
            payload = self._get(
                DE_API,
                {
                    "action": "query",
                    "prop": "pageprops",
                    "ppprop": "wikibase_item",
                    "redirects": "1",
                    "titles": "|".join(chunk),
                },
            )
            query = payload.get("query", {})
            # title-as-resolved -> label-as-asked, walking both hops.
            back: dict[str, str] = {label: label for label in chunk}
            for hop in ("normalized", "redirects"):
                for entry in query.get(hop) or []:
                    origin = back.get(entry["from"], entry["from"])
                    back[entry["to"]] = origin

            for page in (query.get("pages") or {}).values():
                qid = (page.get("pageprops") or {}).get("wikibase_item")
                if not qid:
                    continue
                title = page["title"]
                if allowed is not None and title.casefold() not in allowed:
                    continue
                label = back.get(title)
                if label:
                    found[label] = qid
        return found

    def _image_files(self, qids: dict[str, str]) -> dict[str, str]:
        """Label -> Commons file name, for entities that have a `P18`."""
        files: dict[str, str] = {}
        by_qid = {qid: label for label, qid in qids.items()}
        for chunk in _chunks(list(qids.values()), BATCH):
            entities = self._get(
                WD_API,
                {"action": "wbgetentities", "props": "claims", "ids": "|".join(chunk)},
            ).get("entities", {})
            for qid in chunk:
                claims = (entities.get(qid) or {}).get("claims") or {}
                image = _current_value(claims.get("P18"))
                if image and by_qid.get(qid):
                    files[by_qid[qid]] = str(image)
        return files

    def _licences(self, files: list[str]) -> dict[str, dict]:
        """File -> the attribution fields of `Image`.

        A file with no licence is absent, and the caller drops that answer: an
        image that cannot be credited cannot be shown.
        """
        out: dict[str, dict] = {}
        for chunk in _chunks(files, BATCH):
            payload = self._get(
                COMMONS_API,
                {
                    "action": "query",
                    "prop": "imageinfo",
                    "iiprop": "extmetadata",
                    "titles": "|".join(f"File:{name}" for name in chunk),
                },
            )
            for page in payload.get("query", {}).get("pages", {}).values():
                meta = (page.get("imageinfo") or [{}])[0].get("extmetadata") or {}
                licence = _meta(meta, "LicenseShortName")
                if not licence:
                    continue
                out[page["title"][len("File:") :]] = {
                    "licence": licence,
                    "credit": _strip_html(_meta(meta, "Artist")) or None,
                    "licence_url": _meta(meta, "LicenseUrl") or None,
                }
        return out


# -- rendering ----------------------------------------------------------------

# Wide enough to read a photograph on a laptop, small enough that ten of them
# are not a megabyte. Commons renders and caches this size for us.
THUMB_WIDTH = 640


def commons_url(file: str, *, width: int = THUMB_WIDTH) -> str:
    """A directly loadable URL for a Commons file name.

    `Special:FilePath` resolves a bare name and takes a width, which is why the
    *name* is what gets stored: thumbnails live at a hash-derived path that
    cannot be computed from the name.
    """
    quoted = urllib.parse.quote(file.replace(" ", "_"), safe="")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quoted}?width={width}"


def commons_page(file: str) -> str:
    """The file's description page, for a credit link."""
    quoted = urllib.parse.quote(file.replace(" ", "_"), safe="")
    return f"https://commons.wikimedia.org/wiki/File:{quoted}"


# -- helpers ------------------------------------------------------------------


def _chunks(values: list, size: int):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _current_value(claims):
    """The statement that is true *now*, not merely the first one listed.

    Wikidata keeps history. London's `P17` includes the Roman Empire, Berlin's
    the Margraviate of Brandenburg, Moscow's the Grand Duchy -- all correct, all
    ruinous on a quiz board, and all of them ahead of the modern country in the
    order the API returns.

    Three filters, in the order Wikidata itself intends:

    * drop `deprecated` -- the project's own marker for "this is wrong";
    * drop anything with an end date (`P582`), which is what makes a statement
      historical;
    * prefer `preferred` rank, which is how an item says "this is the one".
    """
    if not claims:
        return None

    live = [
        claim
        for claim in claims
        if claim.get("rank") != "deprecated"
        and "P582" not in (claim.get("qualifiers") or {})
    ]
    if not live:
        return None

    preferred = [claim for claim in live if claim.get("rank") == "preferred"]
    chosen = (preferred or live)[0]
    return ((chosen.get("mainsnak") or {}).get("datavalue") or {}).get("value")


def _meta(meta: dict, key: str) -> str:
    return str((meta.get(key) or {}).get("value", "")).strip()


def _strip_html(value: str) -> str:
    """Commons credits arrive as HTML fragments with links in them."""
    out, depth = [], 0
    for char in value:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return " ".join("".join(out).split())
