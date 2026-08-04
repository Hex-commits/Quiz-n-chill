"""Tests for what actually lands in the database.

The fake below answers the exact chain `write_question` walks and nothing else,
which is the point: it is a record of the calls that method makes, so a rewrite
that starts writing a different shape has to come through here.

No network and no Supabase, like the rest of the suite.
"""

from __future__ import annotations

import pytest

from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.output.store import write_question
from tools.ingest.sources.wikipedia import Article


class FakeTable:
    def __init__(self, store: FakeClient, name: str):
        self.store = store
        self.name = name
        self.payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.payload = payload
        self.store.written.setdefault(self.name, []).append(payload)
        return self

    def delete(self):
        self.store.deleted.append(self.name)
        return self

    def execute(self):
        return FakeResponse(self.store.reply(self.name, self.payload))


class FakeResponse:
    def __init__(self, data: list[dict]):
        self.data = data


class FakeClient:
    def __init__(self):
        self.written: dict[str, list] = {}
        self.deleted: list[str] = []

    def table(self, name: str) -> FakeTable:
        return FakeTable(self, name)

    def reply(self, name: str, payload) -> list[dict]:
        if name == "subjects":
            return [{"id": "subject-1"}]
        if name == "quizzes":
            return [{"id": "quiz-1"}]
        if name == "categories" and payload:
            return [
                {"id": f"category-{index}", "label": row["label"]}
                for index, row in enumerate(payload, start=1)
            ]
        return []


def question() -> GeneratedQuestion:
    return GeneratedQuestion(
        usable=True,
        subject_slug="geografie",
        slug="hauptstaedte-europas",
        title="Hauptstädte Europas",
        description="Welche Stadt ist die Hauptstadt des Landes?",
        difficulty="easy",
        pairs=[
            GeneratedPair(label="Deutschland", answer="Berlin"),
            GeneratedPair(label="Frankreich", answer="Paris"),
        ],
    )


def article() -> Article:
    return Article(
        title="Hauptstadt",
        url="https://de.wikipedia.org/wiki/Hauptstadt",
        summary="Eine Hauptstadt ist ...",
        extract="...",
    )


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


def written_quiz(client: FakeClient) -> dict:
    return client.written["quizzes"][0]


def test_a_generated_question_says_so(client):
    """The one thing separating these from the hand-written pool. It is written
    here rather than left to the column default, because the marker should come
    from the thing that did the generating."""
    write_question(client, question(), article())

    assert written_quiz(client)["origin"] == "ingest"


def test_the_quiz_row_carries_the_article_it_came_from(client):
    write_question(client, question(), article())
    row = written_quiz(client)

    assert row["source_url"] == "https://de.wikipedia.org/wiki/Hauptstadt"
    assert row["source_title"] == "Hauptstadt"
    assert row["slug"] == "hauptstaedte-europas"
    assert row["difficulty"] == "easy"
    assert row["category_kind"] == "text"


def test_each_answer_lands_under_its_own_category(client):
    write_question(client, question(), article())
    categories = client.written["categories"][0]
    items = client.written["items"][0]

    assert [row["label"] for row in categories] == ["Deutschland", "Frankreich"]
    assert [row["label"] for row in items] == ["Berlin", "Paris"]
    assert [row["category_id"] for row in items] == ["category-1", "category-2"]
