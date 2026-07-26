from uuid import uuid4

from app.services.scoring import grade_item, score_assignments

DEUTSCHLAND, FRANKREICH = uuid4(), uuid4()
BERLIN, PARIS, BARCELONA = uuid4(), uuid4(), uuid4()


def test_item_assigned_to_the_right_category():
    assert grade_item(assigned_category_id=DEUTSCHLAND, correct_category_id=DEUTSCHLAND)


def test_item_assigned_to_the_wrong_category():
    assert not grade_item(assigned_category_id=FRANKREICH, correct_category_id=DEUTSCHLAND)


def test_fake_correctly_left_unassigned():
    # Both None: the player spotted the fake.
    assert grade_item(assigned_category_id=None, correct_category_id=None)


def test_fake_wrongly_assigned_to_a_category():
    assert not grade_item(assigned_category_id=DEUTSCHLAND, correct_category_id=None)


def test_real_item_wrongly_called_a_fake():
    assert not grade_item(assigned_category_id=None, correct_category_id=DEUTSCHLAND)


def test_scores_every_item_in_the_answer_key():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND, PARIS: FRANKREICH, BARCELONA: None},
        assigned_by_item={BERLIN: DEUTSCHLAND, PARIS: DEUTSCHLAND, BARCELONA: None},
    )
    assert verdicts == {BERLIN: True, PARIS: False, BARCELONA: True}


def test_untouched_real_item_counts_as_wrong():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND},
        assigned_by_item={},
    )
    assert verdicts == {BERLIN: False}


def test_untouched_fake_counts_as_correct():
    # Leaving a fake alone is the correct move, so an empty submission gets it.
    verdicts = score_assignments(
        correct_by_item={BARCELONA: None},
        assigned_by_item={},
    )
    assert verdicts == {BARCELONA: True}


def test_unknown_item_id_cannot_inflate_the_score():
    verdicts = score_assignments(
        correct_by_item={BERLIN: DEUTSCHLAND},
        assigned_by_item={BERLIN: DEUTSCHLAND, uuid4(): FRANKREICH},
    )
    assert verdicts == {BERLIN: True}
