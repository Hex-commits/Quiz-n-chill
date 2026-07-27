from tools.ingest.output.report import render_markdown

QUESTION = {
    "article": {"title": "Photosynthese", "url": "https://de.wikipedia.org/wiki/Photosynthese"},
    "question": {
        "usable": True,
        "subject_slug": "naturwissenschaft",
        "slug": "photosynthese-zuordnungsfrage",
        "title": "Photosynthese",
        "description": "Ordne die Begriffe zu.",
        "difficulty": "medium",
        "pairs": [
            {"label": "Farbstoffe", "answer": "Chlorophyll"},
            {"label": "Produkte", "answer": "Sauerstoff"},
            {"label": "Edukte", "answer": "Kohlenstoffdioxid"},
            {"label": "Ort", "answer": "Chloroplast"},
            {"label": "Energiequelle", "answer": "Sonnenlicht"},
            {"label": "Speicherstoff", "answer": "Stärke"},
        ],
    },
    "problems": [],
}

REJECTED = {
    "article": {"title": "Kaffee", "url": "https://de.wikipedia.org/wiki/Kaffee"},
    "question": {"usable": True},
    "problems": ["15 items, want 10-12", "duplicate items"],
}


def render(accepted=(), rejected=(), committed=False, **kwargs) -> str:
    return render_markdown(
        {"accepted": list(accepted), "rejected": list(rejected), "committed": committed},
        **kwargs,
    )


def test_the_header_states_whether_anything_was_written():
    assert "no (dry run)" in render()
    assert "**Written to the database:** yes" in render(committed=True)


def test_a_question_renders_every_pairing():
    out = render([QUESTION])

    assert "### 1. Photosynthese" in out
    assert "| **Farbstoffe** | Chlorophyll |" in out
    assert "| **Produkte** | Sauerstoff |" in out


def test_the_source_is_a_clickable_link():
    out = render([QUESTION])
    assert "[Photosynthese](https://de.wikipedia.org/wiki/Photosynthese)" in out






def test_a_clean_review_says_so_without_hedging():
    review = {"ok": True, "problems": [], "bad_fakes": [], "weak_fakes": [],
              "misplaced_items": [], "skipped": False}

    assert "found no content problems" in render([{**QUESTION, "review": review}])




def test_rejected_questions_are_listed_with_the_first_reason():
    out = render(rejected=[REJECTED])

    assert "## Rejected" in out
    assert "15 items, want 10-12" in out
    assert "+1 more" in out  # the rest are summarised, not dumped


def test_sections_are_not_separated_twice():
    out = render([QUESTION], [REJECTED])
    assert "---\n\n---" not in out


def test_an_empty_run_still_produces_a_readable_file():
    out = render()

    assert out.startswith("# Ingest run")
    assert "_None._" in out
    assert out.endswith("\n")


def test_the_model_is_recorded_so_a_report_is_attributable():
    assert "`glm4:9b`" in render([QUESTION], model="glm4:9b")


def test_the_pipeline_trace_is_collapsed_out_of_the_way():
    """On a clean first-pass run it says nothing interesting, so it must not
    push the content a reviewer is here for further down the page."""
    steps = ["extract  3 categories, 6 real + 2 fakes", "check    ok", "review   ok"]
    out = render([{**QUESTION, "steps": steps}])

    assert "<details><summary>Pipeline steps</summary>" in out
    assert "check    ok" in out


def test_a_question_without_a_trace_renders_no_empty_block():
    assert "Pipeline steps" not in render([QUESTION])


def test_a_dropped_article_shows_how_far_it_got():
    """This is the case the trace exists for."""
    steps = ["extract  3 categories", "check    1 problem(s): duplicate items", "repair   retrying, attempt 2"]
    out = render(rejected=[{**REJECTED, "steps": steps}])

    assert "Kaffee — pipeline steps" in out
    assert "repair   retrying, attempt 2" in out


def test_a_written_question_shows_its_database_id():
    written = {**QUESTION, "written": {"quiz_id": "abc-123", "slug": "x", "categories": 3, "items": 8}}
    assert "abc-123" in render([written], committed=True)




def test_the_size_line_counts_pairs():
    assert "**Size:** 6 pairs" in render([QUESTION])


def test_explanations_appear_beside_their_answer():
    """A wrong reason is as bad as a wrong pairing, and the report is the only
    place anyone reads them before they ship."""
    q = {**QUESTION, "question": {**QUESTION["question"],
                                  "explanations": {"Chlorophyll": "Grüner Farbstoff."}}}
    out = render([q])

    assert "| **Farbstoffe** | Chlorophyll | Grüner Farbstoff. |" in out


def test_the_reviewer_is_pointed_at_the_defect_no_check_can_see():
    """An answer that fits two categories on the same board marks a correct
    player wrong, and nothing automatic can spot it."""
    out = render([QUESTION])

    assert "No answer would fit a second category" in out
    assert "All 6 pairings check out against the source" in out
