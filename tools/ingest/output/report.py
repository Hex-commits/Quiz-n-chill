"""Rendering an ingest run as Markdown for a human to check.

The JSON report is the machine record; this is the one you actually read. It is
laid out for the job a reviewer is doing, which is not "is this well-formed" --
`validate.py` already answered that -- but **"is this true, and is each pairing
the only one that fits?"**

That second half is the one nothing automatic can answer. A model will pair an
answer with a category it genuinely belongs to, while it belongs just as
plainly to another category on the same board -- and then the player who picks
the other one is marked wrong for being right. So the whole pairing is laid out
as a table next to the source link needed to check it.
"""

from __future__ import annotations

from typing import Any

from ..sources.wikimedia_images import commons_page, commons_url

DIFFICULTY_MARK = {"easy": "🟢 easy", "medium": "🟡 medium", "hard": "🔴 hard"}


def render_markdown(payload: dict[str, Any], *, model: str = "", generated_at: str = "") -> str:
    accepted = payload.get("accepted", [])
    rejected = payload.get("rejected", [])
    committed = payload.get("committed", False)

    lines: list[str] = ["# Ingest run", ""]

    pictures = sum(1 for record in accepted if record.get("images"))

    meta = [
        f"- **Questions accepted:** {len(accepted)}"
        + (f" ({pictures} with pictures)" if pictures else ""),
        f"- **Rejected:** {len(rejected)}",
        f"- **Written to the database:** {'yes' if committed else 'no (dry run)'}",
    ]
    if model:
        meta.append(f"- **Model:** `{model}`")
    if generated_at:
        meta.append(f"- **Run at:** {generated_at}")
    lines += meta + [""]

    if accepted:
        lines += [
            "## How to check these",
            "",
            "Everything below already passed the structural rules, so the thing",
            "worth your time is the content:",
            "",
            "1. **Open the source** and confirm each answer really belongs to the",
            "   category it is paired with.",
            "2. **Check that each pairing is the only one that fits.** An answer",
            "   that would sit just as well beside a different category on the",
            "   same board makes the question unfair — the player who picks the",
            "   other one is marked wrong for being right. This is the defect no",
            "   automatic check can see.",
            "3. Sanity-check the difficulty.",
            "",
            "---",
            "",
            "## Accepted",
            "",
        ]
        for index, record in enumerate(accepted, start=1):
            lines += _render_question(index, record)
    else:
        lines += ["## Accepted", "", "_None._", ""]

    if rejected:
        # Each accepted question already ends with a rule; only add one here
        # when there were none, otherwise the sections are separated twice.
        if not accepted:
            lines += ["---", ""]
        lines += ["## Rejected", "", _render_rejected(rejected)]

    return "\n".join(lines).rstrip() + "\n"


def _render_question(index: int, record: dict[str, Any]) -> list[str]:
    question = record.get("question", {})
    article = record.get("article", {})
    written = record.get("written")

    title = question.get("title") or "(untitled)"
    difficulty = DIFFICULTY_MARK.get(question.get("difficulty", ""), question.get("difficulty", "?"))

    pairs = question.get("pairs", [])
    images = record.get("images") or {}
    flipped = record.get("flipped", False)

    lines = [
        f"### {index}. {title}",
        "",
        f"- **Subject:** `{question.get('subject_slug', '?')}`  ",
        f"- **Difficulty:** {difficulty}  ",
        f"- **Slug:** `{question.get('slug', '?')}`  ",
        f"- **Source:** [{article.get('title', 'source')}]({article.get('url', '')})  ",
        f"- **Size:** {len(pairs)} pairs",
    ]
    borrowed = record.get("borrowed_from") or []
    if borrowed:
        # Named, because nothing automatic decided these belong on this board.
        # `review` checks that a pair is *true*; whether it answers the same
        # question as the rest is a property of the set, and only `vet` looks at
        # that -- when it is switched on.
        judged = "judged by `vet`" if record.get("vetted") else "**unjudged** (`INGEST_VET` off)"
        lines.append(
            f"- **Pairs borrowed from:** {', '.join(f'_{title}_' for title in borrowed)}"
            f" — {judged}"
        )
    if images:
        turned = " · pairing was flipped to put the pictures on the answers" if flipped else ""
        lines.append(f"- **Answers:** pictures{turned}")
    if written:
        lines.append(f"- **Written:** quiz `{written.get('quiz_id', '')}`")
    lines.append("")

    if question.get("description"):
        lines += [f"> {question['description']}", ""]

    explanations = question.get("explanations") or {}

    if images:
        # Thumbnails, because nothing automatic can look at a photograph. The
        # pipeline can tell you the pairing is right and cannot tell you the
        # picture shows the thing -- so the picture has to be on the page.
        lines += ["| Bild | Category | Answer | Licence |", "| --- | --- | --- | --- |"]
        for pair in pairs:
            answer = pair.get("answer", "?")
            image = images.get(answer)
            cell = "—"
            if image:
                file = image.get("file", "")
                credit = (image.get("credit") or "—").replace("|", "/")[:34]
                cell = (
                    f"[![{answer}]({commons_url(file, width=200)})]({commons_page(file)})"
                )
                licence = f"{image.get('licence','?')}<br><sub>{credit}</sub>"
            else:
                licence = "—"
            lines.append(f"| {cell} | **{pair.get('label','?')}** | {answer} | {licence} |")
        lines.append("")
        lines += [
            f"- [ ] Every picture actually shows the answer beside it",
            "- [ ] Every answer is an instance of what the question asks for",
            f"- [ ] All {len(pairs)} pairings check out against the source",
            # The instruction above was rewritten by the model for a board of
            # photographs, and it is the one thing in this pipeline no gate sees:
            # it is prose a player reads, not data a validator checks. A flipped
            # pairing is where it goes wrong -- the sentence then asks for what
            # the player is already looking at.
            "- [ ] The instruction asks for the **answer**, not for what the picture shows",
            "",
        ]
    else:
        lines += ["| Category | Answer | Why |", "| --- | --- | --- |"]
        for pair in pairs:
            answer = pair.get("answer", "?")
            why = explanations.get(answer, "")
            lines.append(f"| **{pair.get('label', '?')}** | {answer} | {why} |")
        lines.append("")

        lines += [
            f"- [ ] All {len(pairs)} pairings check out against the source",
            "- [ ] No answer would fit a second category on this board",
            *(
                ["- [ ] The borrowed pairs answer the same question as the rest"]
                if borrowed
                else []
            ),
            "",
        ]
    lines += _render_review(record.get("review"))
    lines += _render_steps(record.get("steps"))
    lines += ["---", ""]
    return lines


def _render_steps(steps: list[str] | None) -> list[str]:
    """The path this question took through the pipeline.

    Collapsed, because on a clean first-pass run it says nothing interesting.
    It earns its place on the ones that took three attempts: which gate
    objected, to what, and whether the repair actually fixed it.
    """
    if not steps:
        return []
    return [
        "<details><summary>Pipeline steps</summary>",
        "",
        "```",
        *steps,
        "```",
        "",
        "</details>",
        "",
    ]


def _render_review(review: dict[str, Any] | None) -> list[str]:
    """What the second model pass made of this question.

    Shown even when it passed: knowing a question was checked and cleared is
    different from knowing it was never checked at all.
    """
    if not review:
        return ["_Second-pass review: not run (`--no-review`)._", ""]
    if review.get("skipped"):
        return ["⚠️ _Second-pass review could not run; content is unchecked._", ""]
    if review.get("ok"):
        return ["✅ _Second-pass review found no content problems._", ""]

    lines = [
        "⚠️ **Second-pass review raised these, and they were repaired before acceptance:**",
        "",
    ]
    lines += [f"- {problem}" for problem in review.get("problems", [])]
    return lines + [""]


def _render_rejected(rejected: list[dict[str, Any]]) -> str:
    rows = ["| Article | Why it was dropped |", "| --- | --- |"]
    for record in rejected:
        article = record.get("article", {})
        problems = record.get("problems", [])
        title = article.get("title", "?")
        url = article.get("url", "")
        label = f"[{title}]({url})" if url else title
        # Several complaints usually share one root cause; showing them all just
        # makes the table unreadable.
        why = problems[0] if problems else "unknown"
        if len(problems) > 1:
            why += f" _(+{len(problems) - 1} more)_"
        rows.append(f"| {label} | {why} |")

    # A dropped article is the case where the trace is worth reading, so the
    # steps go below the table rather than being summarised away with the rest.
    for record in rejected:
        steps = record.get("steps")
        if not steps:
            continue
        title = record.get("article", {}).get("title", "?")
        rows += ["", f"<details><summary>{title} — pipeline steps</summary>", "", "```"]
        rows += list(steps)
        rows += ["```", "", "</details>"]

    return "\n".join(rows) + "\n"
