from uuid import uuid4

from app.services.scoring import grade_item, score_assignments

DEUTSCHLAND, FRANKREICH, ESPANA = uuid4(), uuid4(), uuid4()
BERLIN, PARIS, BARCELONA = uuid4(), uuid4(), uuid4()


def test_item_assigned_to_the_right_category():
    assert grade_item(assigned_category_id=DEUTSCHLAND, correct_category_id=DEUTSCHLAND)


def test_item_assigned_to_the_wrong_category():
    assert not grade_item(assigned_category_id=FRANKREICH, correct_category_id=DEUTSCHLAND)


def test_an_unplaced_item_counts_as_wrong():
    """Leaving an answer alone is never the right move: every answer belongs to
    exactly one category, so not placing it is simply not answering."""
    assert not grade_item(assigned_category_id=None, correct_category_id=DEUTSCHLAND)


def test_scores_every_item_in_the_answer_key():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND, PARIS: FRANKREICH, BARCELONA: ESPANA},
        assigned_by_item={BERLIN: DEUTSCHLAND, PARIS: DEUTSCHLAND, BARCELONA: ESPANA},
    )
    assert verdicts == {BERLIN: True, PARIS: False, BARCELONA: True}


def test_untouched_real_item_counts_as_wrong():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND},
        assigned_by_item={},
    )
    assert verdicts == {BERLIN: False}


def test_unknown_item_id_cannot_inflate_the_score():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND},
        assigned_by_item={BERLIN: DEUTSCHLAND, uuid4(): FRANKREICH},
    )
    assert verdicts == {BERLIN: True}
