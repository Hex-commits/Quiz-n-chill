from uuid import uuid4

from app.services.scoring import grade_item, score_assignments

DEUTSCHLAND, FRANKREICH, ESPANA = uuid4(), uuid4(), uuid4()
BERLIN, PARIS, BARCELONA = uuid4(), uuid4(), uuid4()
ZUERICH = uuid4()  # a fake: belongs to no category


def test_item_assigned_to_the_right_category():
    assert grade_item(assigned_category_id=DEUTSCHLAND, correct_category_id=DEUTSCHLAND)


def test_item_assigned_to_the_wrong_category():
    assert not grade_item(assigned_category_id=FRANKREICH, correct_category_id=DEUTSCHLAND)


def test_calling_a_real_answer_a_fake_is_wrong():
    """None as the assignment is the player saying "this belongs nowhere"."""
    assert not grade_item(assigned_category_id=None, correct_category_id=DEUTSCHLAND)


def test_spotting_a_fake_is_right():
    assert grade_item(assigned_category_id=None, correct_category_id=None)


def test_placing_a_fake_in_a_category_is_wrong():
    assert not grade_item(assigned_category_id=DEUTSCHLAND, correct_category_id=None)


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


def test_untouched_fake_counts_as_wrong():
    """The one case `.get()` would have got backwards: a missing key is the
    player never answering, not the player calling it a fake. Defaulting would
    hand a point to whoever submits an empty form."""
    verdicts = score_assignments(
        correct_by_item={ZUERICH: None},
        assigned_by_item={},
    )
    assert verdicts == {ZUERICH: False}


def test_a_declared_fake_scores():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND, ZUERICH: None},
        assigned_by_item={BERLIN: DEUTSCHLAND, ZUERICH: None},
    )
    assert verdicts == {BERLIN: True, ZUERICH: True}
