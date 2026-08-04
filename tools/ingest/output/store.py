"""Writing generated questions into Supabase.

Uses the service-role key, exactly like the API does -- row level security is on
with no policies, so nothing else can write.

Inserts are ordered quiz -> categories -> items and the quiz row is deleted
again if a later step fails. The three tables have no transaction across them
through PostgREST, so this is the closest thing available to all-or-nothing;
without it a failure would leave a question with no answers, which the game
would happily try to deal into a round.
"""

from __future__ import annotations

from dataclasses import dataclass

from supabase import Client, create_client

from ..domain.models import GeneratedQuestion
from ..sources.wikipedia import Article


def _image_columns(image) -> dict:
    """The four flat columns behind one `Image`, or nulls.

    Flat in the database and nested above it: `categories_image_is_complete`
    refuses a file without a licence, so the two cannot be split by a partial
    write.
    """
    if image is None:
        return {}
    return {
        "image_file": image.file,
        "image_credit": image.credit,
        "image_licence": image.licence,
        "image_licence_url": image.licence_url,
    }


@dataclass(frozen=True)
class Written:
    quiz_id: str
    slug: str
    categories: int
    items: int


class StoreError(RuntimeError):
    pass


def connect(url: str, service_role_key: str) -> Client:
    return create_client(url, service_role_key)


def subjects(client: Client) -> list[tuple[str, str]]:
    rows = client.table("subjects").select("slug, name").order("position").execute().data
    return [(row["slug"], row["name"]) for row in rows]


def existing_slugs(client: Client) -> set[str]:
    rows = client.table("quizzes").select("slug").execute().data
    return {row["slug"] for row in rows}


def existing_source_urls(client: Client) -> set[str]:
    rows = client.table("quizzes").select("source_url").not_.is_("source_url", "null").execute()
    return {row["source_url"] for row in rows.data if row["source_url"]}


def write_question(
    client: Client,
    question: GeneratedQuestion,
    article: Article,
    images: dict | None = None,
) -> Written:
    """Write one question. `images` maps category label -> `Image`.

    A question with images is stored as `category_kind='image'`, which tells the
    client to draw each category as a photograph. Setting it here rather than
    inferring it later means the flag and the picture columns are written in the
    same transaction, so a quiz can never claim to be one and lack the other.

    `origin` is written explicitly even though the column defaults to it. This
    is the one place in the codebase that generates a question, and a marker
    saying "written by a model" should be stated by the thing doing the writing
    rather than inherited from a default that a later migration could change.
    """
    subject = (
        client.table("subjects")
        .select("id")
        .eq("slug", question.subject_slug)
        .limit(1)
        .execute()
    )
    if not subject.data:
        raise StoreError(f"Unknown subject slug {question.subject_slug!r}")

    quiz = (
        client.table("quizzes")
        .insert(
            {
                "subject_id": subject.data[0]["id"],
                "slug": question.slug,
                "title": question.title,
                "description": question.description or None,
                "difficulty": question.difficulty,
                "source_url": article.url,
                "source_title": article.title,
                "category_kind": "image" if images else "text",
                "origin": "ingest",
            }
        )
        .execute()
    )
    quiz_id = quiz.data[0]["id"]

    try:
        category_rows = (
            client.table("categories")
            .insert(
                [
                    {
                        "quiz_id": quiz_id,
                        "label": pair.label.strip(),
                        "position": index,
                        **_image_columns((images or {}).get(pair.label)),
                    }
                    for index, pair in enumerate(question.pairs, start=1)
                ]
            )
            .execute()
            .data
        )
        by_label = {row["label"]: row["id"] for row in category_rows}

        explanations = question.explanations

        client.table("items").insert(
            [
                {
                    "quiz_id": quiz_id,
                    "category_id": by_label[pair.label.strip()],
                    "label": pair.answer.strip(),
                    "position": index,
                    "explanation": explanations.get(pair.answer) or None,
                }
                for index, pair in enumerate(question.pairs, start=1)
            ]
        ).execute()
    except Exception:
        client.table("quizzes").delete().eq("id", quiz_id).execute()
        raise

    return Written(
        quiz_id=quiz_id,
        slug=question.slug,
        categories=len(question.pairs),
        items=len(question.pairs),
    )
