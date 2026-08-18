"""Picture questions: the category is the photograph.

The pairing is unchanged -- one category, one answer -- so none of the game
rules are under test here. What is under test is that the photograph and its
attribution reach the board together, and that a picture question's *answers*
are ordinary words.

There is deliberately no redaction test, because there is no longer anything to
redact. The first design put the photographs in the answer pool, which meant
`items.label` held the answer and every read path -- the pool, the running
commentary, the rejected-guess list -- had to remember to strip it. Moving the
pictures onto the categories deleted that class of bug rather than testing it:
categories are the board, visible from the first frame, so there is no moment
when hiding anything would mean something.
"""

from __future__ import annotations

import random
from uuid import uuid4

import pytest

from app.schemas import Category, CategoryKind, ImagePublic, ItemSolution, LobbyStatus
from app.services import lobbies
from app.services.lobbies import BOARD_FAKES, BOARD_PAIRS, deal_board

from tests.test_lobbies import clean_store  # noqa: F401  -- the autouse fixture

UK, FR, IT, DE = uuid4(), uuid4(), uuid4(), uuid4()

BRIDGES = [
    (UK, "Albert Bridge", "Albert Bridge London.jpg", "Vereinigtes Königreich"),
    (FR, "Pont Neuf", "Pont Neuf Paris.jpg", "Frankreich"),
    (IT, "Ponte Vecchio", "Ponte Vecchio Florenz.jpg", "Italien"),
    (DE, "Rheinbrücke", "Rheinbruecke.jpg", "Deutschland"),
]


def picture_round(slug: str = "bruecken"):
    return lobbies.Round(
        quiz_id=uuid4(),
        slug=slug,
        title="Brücken Europas",
        description="In welchem Land steht diese Brücke?",
        difficulty="medium",
        category_kind=CategoryKind.image,
        source=None,
        categories=[
            Category(
                id=cid,
                label=bridge,
                position=n,
                image=ImagePublic(
                    src=f"https://commons.wikimedia.org/wiki/Special:FilePath/{file}",
                    credit="Ein Fotograf",
                    licence="CC BY-SA 4.0",
                    licence_url="https://creativecommons.org/licenses/by-sa/4.0",
                ),
            )
            for n, (cid, bridge, file, _) in enumerate(BRIDGES, start=1)
        ],
        items=[
            ItemSolution(id=uuid4(), label=country, position=n, category_id=cid)
            for n, (cid, _, _, country) in enumerate(BRIDGES, start=1)
        ],
    )


@pytest.fixture
def picture_game(monkeypatch):
    monkeypatch.setattr(lobbies, "_load_round", picture_round)
    code, anna = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1)
    return code, anna, ben


def board(code):
    return lobbies.get_view(code).round_view.categories


def pool(code):
    return lobbies.get_view(code).round_view.remaining_items


def find(code, country):
    """The id of an answer, looked up by its name.

    Goes through `edit`, which is the store's own read-for-write -- there is no
    plain read, because every entry point the game has is a mutation.
    """
    with lobbies.edit(code) as lobby:
        return next(i.id for i in lobby.current_round.items if i.label == country)



def test_every_category_carries_its_photograph(picture_game):
    code, _anna, _ben = picture_game

    categories = board(code)

    assert len(categories) == len(BRIDGES)
    assert all(category.image is not None for category in categories)
    assert all(c.image.src.startswith("https://commons.") for c in categories)


def test_the_credit_is_on_screen_from_the_first_frame(picture_game):
    """A licence obligation, not a caption. CC BY-SA requires attribution
    wherever the work is shown, and a category is shown immediately -- so unlike
    the picture-answer design there is nothing to time it against."""
    code, _anna, _ben = picture_game

    assert all(c.image.licence == "CC BY-SA 4.0" for c in board(code))
    assert all(c.image.credit == "Ein Fotograf" for c in board(code))


def test_a_category_on_a_running_picture_round_is_not_named(picture_game):
    """The redaction that survived the move. "Albert Bridge" printed above a
    photograph of the Albert Bridge answers the question the photograph was
    chosen to ask -- and names its city while it is at it, which is the paired
    answer."""
    code, _anna, _ben = picture_game

    assert all(category.label is None for category in board(code))
    assert all(category.image is not None for category in board(code))


def test_nothing_in_a_running_picture_round_names_a_category(picture_game):
    """Stated once, over the whole payload a player receives."""
    code, anna, _ben = picture_game

    lobbies.submit_turn(code, anna, find(code, "Frankreich"), UK)
    view = lobbies.get_view(code)

    on_screen = [
        *(c.label for c in view.round_view.categories),
        *(m.item_label for m in view.history),
        *(s.label for s in view.round_view.solved_items),
        *(i.label for i in view.round_view.remaining_items),
    ]

    assert not any(name in (b for _, b, _, _ in BRIDGES) for name in on_screen if name)


def test_the_names_come_back_for_the_review(picture_game, monkeypatch):
    """The point of the pause. Withholding them here would make a picture round
    unlearnable -- you would never find out what you had been looking at."""
    code, anna, ben = picture_game

    lobbies.submit_turn(code, anna, find(code, "Vereinigtes Königreich"), UK)
    lobbies.submit_turn(code, ben, find(code, "Frankreich"), FR)
    lobbies.submit_turn(code, anna, find(code, "Italien"), IT)
    view = lobbies.submit_turn(code, ben, find(code, "Deutschland"), DE)

    solution = view.finished_rounds[0].solution
    assert {pair.category_label for pair in solution} == {b for _, b, _, _ in BRIDGES}


def test_a_text_round_always_names_its_categories(monkeypatch):
    """The redaction is for picture questions only. A worded category with its
    label withheld would be a blank card."""
    from tests.test_lobbies import make_round

    monkeypatch.setattr(lobbies, "_load_round", make_round)
    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1)

    assert all(category.label for category in lobbies.get_view(code).round_view.categories)


def test_blanking_a_name_does_not_consume_the_stored_round(picture_game):
    """The round is held for the whole game and re-read on every poll, so a
    blank written in place would blank it for the review as well."""
    code, _anna, _ben = picture_game

    lobbies.get_view(code)
    lobbies.get_view(code)

    with lobbies.edit(code) as lobby:
        assert all(c.label for c in lobby.current_round.categories)


def test_the_category_kind_reaches_the_client(picture_game):
    code, _anna, _ben = picture_game
    assert lobbies.get_view(code).round_view.category_kind is CategoryKind.image


def test_the_answers_are_ordinary_words(picture_game):
    """The half that makes this playable. The photographs are the question; what
    you assign to them is text, exactly as in every other question."""
    code, _anna, _ben = picture_game

    items = pool(code)

    assert {item.label for item in items} == {country for *_, country in BRIDGES}
    assert all(item.label for item in items)


def test_a_text_question_has_no_pictures_anywhere(monkeypatch):
    from tests.test_lobbies import make_round

    monkeypatch.setattr(lobbies, "_load_round", make_round)
    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1)

    view = lobbies.get_view(code)
    assert view.round_view.category_kind is CategoryKind.text
    assert all(category.image is None for category in view.round_view.categories)
    assert all(item.label for item in view.round_view.remaining_items)



def test_a_wrongly_placed_answer_is_named(picture_game):
    """It goes back in the pool where every player can read it anyway, so
    withholding it would only make the history harder to follow."""
    code, anna, _ben = picture_game

    view = lobbies.submit_turn(code, anna, find(code, "Frankreich"), UK)

    assert view.last_move.was_correct is False
    assert view.last_move.item_label == "Frankreich"
    assert [move.item_label for move in view.history] == ["Frankreich"]


def test_a_correct_placement_is_named_too(picture_game):
    code, anna, _ben = picture_game

    view = lobbies.submit_turn(code, anna, find(code, "Vereinigtes Königreich"), UK)

    assert view.last_move.item_label == "Vereinigtes Königreich"
    assert [s.label for s in view.round_view.solved_items] == ["Vereinigtes Königreich"]



def test_the_review_shows_each_photograph_beside_its_answer(picture_game):
    """The point of the pause: seeing which bridge went with which country."""
    code, anna, ben = picture_game

    lobbies.submit_turn(code, anna, find(code, "Vereinigtes Königreich"), UK)
    lobbies.submit_turn(code, ben, find(code, "Frankreich"), FR)
    lobbies.submit_turn(code, anna, find(code, "Italien"), IT)
    view = lobbies.submit_turn(code, ben, find(code, "Deutschland"), DE)

    assert view.status is LobbyStatus.finished
    solution = view.finished_rounds[0].solution
    assert {pair.item_label for pair in solution} == {c for *_, c in BRIDGES}
    assert {pair.category_label for pair in solution} == {b for _, b, _, _ in BRIDGES}
    assert all(pair.image is not None for pair in solution)
    assert all(pair.image.licence for pair in solution)



def big_round(pairs: int, fakes: int = 0):
    cats = [Category(id=uuid4(), label=f"Bild {n}", position=n) for n in range(pairs)]
    return lobbies.Round(
        quiz_id=uuid4(), slug="s", title="T", description=None, difficulty="medium",
        categories=cats,
        items=[
            ItemSolution(id=uuid4(), label=f"Land {n}", position=n, category_id=c.id)
            for n, c in enumerate(cats)
        ] + [
            ItemSolution(id=uuid4(), label=f"Falsch {n}", position=pairs + n,
                         category_id=None)
            for n in range(fakes)
        ],
    )


def test_a_large_question_is_dealt_down_to_a_board():
    dealt = deal_board(big_round(30), random.Random(1))

    assert len(dealt.categories) == BOARD_PAIRS
    assert len(dealt.items) == BOARD_PAIRS
    assert {i.category_id for i in dealt.items} == {c.id for c in dealt.categories}


def test_a_small_question_is_dealt_whole():
    stored = big_round(6)
    assert deal_board(stored, random.Random(0)) is stored


def test_dealing_does_not_consume_the_stored_question():
    """The loaded question is reused every time the quiz comes up. Trimming it
    in place would make the second game a subset of the first."""
    stored = big_round(30)

    deal_board(stored, random.Random(1))
    deal_board(stored, random.Random(2))

    assert len(stored.categories) == 30


def test_the_same_question_is_a_different_board_each_game():
    boards = {
        tuple(c.label for c in deal_board(big_round(30), random.Random(seed)).categories)
        for seed in range(10)
    }
    assert len(boards) > 1


def test_a_dealt_board_keeps_the_written_order():
    dealt = deal_board(big_round(3), random.Random(3))
    positions = [c.position for c in dealt.categories]
    assert positions == sorted(positions)


def test_a_dealt_board_keeps_its_fakes():
    """Cutting the pairs down to a board must not cut the fakes away with them:
    they have no category to be sampled along with, so the filter that trims
    the pairs would drop every one."""
    dealt = deal_board(big_round(30, fakes=2), random.Random(1))

    assert len(dealt.categories) == BOARD_PAIRS
    assert sum(1 for i in dealt.items if i.category_id is None) == 2
    assert len(dealt.items) == BOARD_PAIRS + 2


def test_a_board_never_carries_more_fakes_than_it_should():
    """Otherwise a question written with six of them would be the one board in
    the game where a third of the pool belongs nowhere."""
    dealt = deal_board(big_round(30, fakes=6), random.Random(1))

    assert sum(1 for i in dealt.items if i.category_id is None) == BOARD_FAKES


def test_a_small_question_with_extra_fakes_is_still_trimmed():
    """The early return for a question that fits is about the pairs. A board
    small enough to deal whole can still be carrying too many fakes."""
    stored = big_round(6, fakes=5)

    dealt = deal_board(stored, random.Random(0))

    assert len(dealt.categories) == 6
    assert sum(1 for i in dealt.items if i.category_id is None) == BOARD_FAKES
    assert len(stored.items) == 11


def test_a_question_without_fakes_deals_exactly_as_before():
    stored = big_round(6)
    assert deal_board(stored, random.Random(0)) is stored
