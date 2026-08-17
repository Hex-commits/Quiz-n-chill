"""Build a picture-question SQL batch from verified Wikidata/Commons images.

Every category of a picture question needs a real Commons file *and* a licence --
`categories_image_is_complete` refuses half-filled rows, and an image that cannot
be credited cannot be shown. So nothing here is written from memory: each label
is resolved through the same provider the ingest pipeline uses
(de.wikipedia title -> Wikidata item -> P18 -> Commons licence), and a board that
cannot reach MIN_PAIRS verified images is dropped rather than padded.

Usage: python build_picture_sql.py <output.sql>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.ingest.sources.wikimedia_images import (
    WikimediaImages,
    _chunks,
    _current_value,
    _meta,
    _strip_html,
    COMMONS_API,
    WD_API,
)
import re as _re


class WikidataPictures(WikimediaImages):
    """`WikimediaImages`, but free to follow image properties other than P18.

    P18 is the curated "image of this thing" and stays the default. It is not
    the only one Wikidata maintains, and the others open boards that P18 cannot
    fill: a country's flag is P41, its coat of arms P94, its outline on the
    globe P242. Same Commons files, same licence check, wider reach.

    Properties are tried in order and the first hit wins, so a chain like
    ("P41", "P18") means "the flag if there is one, otherwise the photograph".
    """

    def __init__(self, *args, properties: tuple[str, ...] = ("P18",), **kwargs):
        super().__init__(*args, **kwargs)
        self._properties = properties

    def _licences(self, files: list[str]) -> dict[str, dict]:
        """File -> attribution fields, refusing anything that cannot be credited.

        The parent looks only at `Artist`. That leaves three gaps, and all three
        showed up in a single batch:

        * the credit sits in `Attribution` instead of `Artist`;
        * `Artist` is a signature *image*, so stripping the markup leaves "";
        * there is no attribution anywhere, though `AttributionRequired` is true.

        The first two are recoverable -- fall through the fields, and failing
        that lift the user name out of the link markup. The third is not: a
        CC BY-SA file with no author to name cannot lawfully be shown, so it is
        omitted and the caller drops that pair, exactly as for a missing licence.
        """
        out: dict[str, dict] = {}
        for chunk in _chunks(files, 50):
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

                credit = None
                for field in ("Artist", "Attribution", "Credit"):
                    raw = _meta(meta, field)
                    if not raw:
                        continue
                    credit = _strip_html(raw).strip() or _user_from_markup(raw)
                    if credit:
                        break

                required = str(_meta(meta, "AttributionRequired")).lower() == "true"
                if required and not credit:
                    continue

                out[page["title"][len("File:") :]] = {
                    "licence": licence,
                    "credit": credit or None,
                    "licence_url": _meta(meta, "LicenseUrl") or None,
                }
        return out

    def _image_files(self, qids: dict[str, str]) -> dict[str, str]:
        files: dict[str, str] = {}
        by_qid = {qid: label for label, qid in qids.items()}
        for chunk in _chunks(list(qids.values()), 50):
            entities = self._get(
                WD_API,
                {"action": "wbgetentities", "props": "claims", "ids": "|".join(chunk)},
            ).get("entities", {})
            for qid in chunk:
                claims = (entities.get(qid) or {}).get("claims") or {}
                for prop in self._properties:
                    image = _current_value(claims.get(prop))
                    if image and by_qid.get(qid):
                        files[by_qid[qid]] = str(image)
                        break
        return files

MIN_PAIRS = 10


class NoDocument:
    """`require_link=False` means the document is never consulted."""

    title = ""
    links = ()


def _user_from_markup(raw: str) -> str | None:
    """The Commons user name out of link markup, when the text is an image."""
    match = _re.search(r'title="User:([^"]+)"', raw)
    return match.group(1).strip() if match else None


def q(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


# Each board: the photographed thing is the category, the word is the answer.
# pairs = (wikipedia title used for the lookup, shown answer, explanation)
BOARDS: list[dict] = []


def _load_extra_boards(only: str | None = None) -> None:
    """Pick up every `boards_*.py` sitting next to this script.

    Board data grows; the resolver does not. Keeping later batches in their own
    modules means adding questions never touches the machinery that verifies
    them.
    """
    import importlib.util

    pattern = f"{only}.py" if only else "boards_*.py"
    for module_path in sorted(Path(__file__).resolve().parent.glob(pattern)):
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        BOARDS.extend(getattr(module, "BOARDS", []))




def main(out_path: str, only: str | None = None) -> int:
    _load_extra_boards(only)
    here = Path(__file__).resolve().parent
    already_present = {
        match
        for sql in here.glob('*.sql')
        if sql.name != Path(out_path).name
        for match in re.findall(r"select s\.id, '([^']+)'", sql.read_text(encoding='utf-8'))
    }
    kept: list[tuple[dict, list]] = []
    providers: dict[tuple, WikidataPictures] = {}

    for board in BOARDS:
        if board["slug"] in already_present:
            print(f"skip {board['slug']}: already in another batch file")
            continue
        properties = tuple(board.get("properties", ("P18",)))
        if properties not in providers:
            providers[properties] = WikidataPictures(
                require_link=False, throttle=1.0, properties=properties
            )
        labels = [title for title, _, _ in board["pairs"]]
        images = providers[properties].images_for(labels, document=NoDocument())

        rows, seen_answers = [], set()
        for title, answer, explanation in board["pairs"]:
            image = images.get(title)
            placeholder = "Doppelt" in (answer, explanation) or not explanation.strip()
            if image is None or answer in seen_answers or placeholder:
                continue
            seen_answers.add(answer)
            rows.append((title, answer, explanation, image))

        status = "keep" if len(rows) >= MIN_PAIRS else "DROP"
        print(f"{status} {board['slug']}: {len(rows)}/{len(board['pairs'])} usable")
        for missing in [p[0] for p in board["pairs"] if p[0] not in images]:
            print(f"      no image: {missing}")
        if len(rows) >= MIN_PAIRS:
            kept.append((board, rows[:14]))

    if not kept:
        print("nothing to write")
        return 1

    parts = [
        "-- Bildfragen: die Kategorie ist ein Foto, die Antwort ein Wort.\n"
        "--\n"
        "-- Anders als bei den Textdateien ist hier nichts aus dem Gedächtnis\n"
        "-- geschrieben: jeder Dateiname und jede Lizenz stammt aus Wikidata (P18)\n"
        "-- und Commons, abgefragt über denselben Provider, den tools/ingest nutzt.\n"
        "-- Eine Kategorie ohne belegte Lizenz ist gar nicht erst aufgenommen --\n"
        "-- categories_image_is_complete würde sie ohnehin zurückweisen.\n"
        "--\n"
        "-- Anwenden wie die Textdateien, siehe supabase/questions/batch-01.sql.\n"
    ]

    for board, rows in kept:
        parts.append(
            "\nwith new_quiz as (\n"
            "    insert into quizzes (subject_id, slug, title, description, difficulty,\n"
            "                         source_title, source_url, category_kind, origin)\n"
            f"    select s.id, {q(board['slug'])}, {q(board['title'])},\n"
            f"           {q(board['description'])}, {q(board['difficulty'])}::difficulty,\n"
            f"           {q(board['source_title'])}, {q(board['source_url'])}, 'image', 'seed'\n"
            f"      from subjects s\n"
            f"     where s.slug = {q(board['subject'])}\n"
            f"       and not exists (select 1 from quizzes q where q.slug = {q(board['slug'])})\n"
            "    returning id\n"
            "),\n"
            "pairs (label, answer, explanation, image_file, image_credit,\n"
            "       image_licence, image_licence_url, position) as (\n    values\n"
        )
        values = []
        for position, (title, answer, explanation, image) in enumerate(rows, start=1):
            values.append(
                f"    ({q(title)}, {q(answer)}, {q(explanation)},\n"
                f"     {q(image.file)}, {q(image.credit)},\n"
                f"     {q(image.licence)}, {q(image.licence_url)}, {position})"
            )
        parts.append(",\n".join(values))
        parts.append(
            "\n),\n"
            "new_categories as (\n"
            "    insert into categories (quiz_id, label, position, image_file,\n"
            "                            image_credit, image_licence, image_licence_url)\n"
            "    select q.id, p.label, p.position, p.image_file,\n"
            "           p.image_credit, p.image_licence, p.image_licence_url\n"
            "      from new_quiz q cross join pairs p\n"
            "    returning id, quiz_id, label\n"
            ")\n"
            "insert into items (quiz_id, category_id, label, position, explanation)\n"
            "select c.quiz_id, c.id, p.answer, p.position, p.explanation\n"
            "  from new_categories c\n"
            "  join pairs p on p.label = c.label;\n"
        )

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("".join(parts))
    total = sum(len(rows) for _, rows in kept)
    print(f"\nwrote {len(kept)} picture questions, {total} verified images -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main(
            sys.argv[1] if len(sys.argv) > 1 else "bilder-01.sql",
            sys.argv[2] if len(sys.argv) > 2 else None,
        )
    )
