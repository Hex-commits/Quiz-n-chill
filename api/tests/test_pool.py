"""Which questions a game may be dealt.

Only the hand-written pool is played -- see `PLAYABLE_ORIGIN`. The database is
stubbed out: what is under test is the filter, not PostgREST.

The two paths are tested separately because they are filtered differently, and
for a reason worth pinning down. `list_quizzes` selects the quiz rows, so origin
is a plain condition the query can carry. Everything reached through `subjects`
gets its questions as an *embedded* resource, where a condition nulls the embed
out rather than dropping the parent row -- so those filter in Python, and a
subject whose questions are all generated has to come back empty rather than not
come back at all.
"""

from uuid import uuid4

from app.services import quizzes


class FakeQuery:
    """Every builder method the service chains, and none of their behaviour."""

    def __init__(self, rows: list[dict], calls: list[tuple]):
        self.data = rows
        self.calls = calls

    def select(self, *args, **kwargs):
        return self

    def in_(self, *args):
        return self

    def eq(self, *args):
        self.calls.append(("eq", *args))
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self):
        return self


class FakeClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.calls: list[tuple] = []

    def table(self, _name: str):
        return FakeQuery(self.rows, self.calls)


def stub(monkeypatch, rows: list[dict]) -> FakeClient:
    client = FakeClient(rows)
    monkeypatch.setattr(quizzes, "get_client", lambda: client)
    return client


def quiz(slug: str, origin: str, difficulty: str = "medium") -> dict:
    return {"slug": slug, "difficulty": difficulty, "origin": origin}


def subject(slug: str, quizzes_: list[dict]) -> dict:
    return {
        "id": str(uuid4()),
        "slug": slug,
        "name": slug.title(),
        "description": None,
        "position": 1,
        "quizzes": quizzes_,
    }


def test_the_pool_holds_only_hand_written_questions(monkeypatch):
    stub(
        monkeypatch,
        [subject("geografie", [quiz("a", "seed"), quiz("b", "ingest"), quiz("c", "seed")])],
    )
    assert quizzes.pools_by_subject(["geografie"]) == {"geografie": ["a", "c"]}


def test_a_subject_of_generated_questions_is_not_offered(monkeypatch):
    """Empty, not absent -- the same as a subject holding no questions at all,
    which is what it is as far as a game is concerned."""
    stub(
        monkeypatch,
        [
            subject("geografie", [quiz("a", "seed")]),
            subject("musik", [quiz("b", "ingest"), quiz("c", "ingest")]),
        ],
    )
    assert quizzes.pools_by_subject(["geografie", "musik"]) == {"geografie": ["a"]}


def test_difficulty_still_narrows_the_hand_written_pool(monkeypatch):
    stub(
        monkeypatch,
        [
            subject(
                "geografie",
                [
                    quiz("a", "seed", "easy"),
                    quiz("b", "seed", "hard"),
                    quiz("c", "ingest", "easy"),
                ],
            )
        ],
    )
    assert quizzes.pools_by_subject(["geografie"], ["easy"]) == {"geografie": ["a"]}


def test_the_host_is_shown_the_count_they_will_actually_play(monkeypatch):
    """The counts on the subject picker come from the same pool as the draw. A
    subject advertising forty questions and dealing three would be worse than
    either number on its own."""
    stub(
        monkeypatch,
        [
            subject(
                "geografie",
                [
                    quiz("a", "seed", "easy"),
                    quiz("b", "seed", "hard"),
                    quiz("c", "ingest", "easy"),
                    quiz("d", "ingest", "medium"),
                ],
            )
        ],
    )
    [found] = quizzes.list_subjects()
    assert found.quiz_count == 2
    assert found.difficulty_counts == {"easy": 1, "hard": 1}


def test_browsing_questions_asks_the_database_for_the_playable_ones(monkeypatch):
    client = stub(monkeypatch, [])
    quizzes.list_quizzes()
    assert ("eq", "origin", quizzes.PLAYABLE_ORIGIN) in client.calls
