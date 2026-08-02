"""What the pipeline passes around: the shapes, and the grammars behind them.

Two kinds of thing live here and they are not the same:

* **Pydantic models** — what our code holds. Validated, typed, easy to test.
* **JSON Schemas** — what Ollama is *constrained to emit*. Handed to the model
  in `format`, they restrict token sampling so a reply cannot come back
  malformed.

They are written separately on purpose. `GeneratedQuestion.model_json_schema()`
looks like it would save the duplication, but Pydantic omits every field that
has a default from `required` -- and a 9B model reads that as permission to skip
them, returning `subject_slug: ""` and `title: ""` and calling it done. The
hand-built schema marks everything required, and pushes anything a grammar can
enforce (subject, difficulty, list bounds) into the grammar, where it is
*impossible to emit* rather than merely rejected afterwards.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .rules import DIFFICULTIES, MAX_PAIRS, MIN_PAIRS


class GeneratedPair(BaseModel):
    """One category and the single answer that belongs to it."""

    label: str = Field(description="Name der Kategorie, z. B. 'Deutschland'")
    answer: str = Field(description="Die eine Antwort dazu, z. B. 'Berlin'")


class GeneratedQuestion(BaseModel):
    usable: bool = Field(
        description="false, wenn der Artikel keine saubere Zuordnungsfrage hergibt"
    )
    reason: str = Field(default="", description="Bei usable=false: kurze Begründung")
    subject_slug: str = Field(default="", description="Slug eines der vorgegebenen Themengebiete")
    slug: str = Field(default="", description="URL-tauglicher Bezeichner, klein, mit Bindestrichen")
    title: str = Field(default="", description="Titel der Frage, z. B. 'Flüsse Europas'")
    description: str = Field(default="", description="Ein Satz Spielanleitung")
    difficulty: str = Field(default="medium", description="easy, medium oder hard")
    pairs: list[GeneratedPair] = Field(default_factory=list)

    explanations: dict[str, str] = Field(default_factory=dict)

    @property
    def labels(self) -> list[str]:
        return [pair.label for pair in self.pairs]

    @property
    def answers(self) -> list[str]:
        return [pair.answer for pair in self.pairs]

    all_items = answers


class Extraction(BaseModel):
    """One pass of the extract step: the parsed question and the raw reply.

    The raw dict is kept because the repair turn has to show the model its own
    previous answer, and because a reply that fails to parse still has to be
    reported as something more useful than "it broke".
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    raw: dict = Field(default_factory=dict)
    question: GeneratedQuestion | None = None
    error: str = ""



class Review(BaseModel):
    """The second pass's verdict on one question."""

    ok: bool = True
    problems: list[str] = Field(default_factory=list)
    misplaced_items: list[str] = Field(default_factory=list)
    skipped: bool = False



def question_schema(subject_slugs: list[str]) -> dict:
    """Constrains the extract step. Every field required; enums where possible."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "usable",
            "reason",
            "subject_slug",
            "slug",
            "title",
            "description",
            "difficulty",
            "pairs",
        ],
        "properties": {
            "usable": {"type": "boolean"},
            "reason": {"type": "string"},
            "subject_slug": {"type": "string", "enum": sorted(subject_slugs)},
            "slug": {"type": "string", "minLength": 3},
            "title": {"type": "string", "minLength": 3},
            "description": {"type": "string"},
            "difficulty": {"type": "string", "enum": list(DIFFICULTIES)},
            "pairs": {
                "type": "array",
                "minItems": MIN_PAIRS,
                "maxItems": MAX_PAIRS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "answer"],
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "answer": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


MAX_EXPLANATION_CHARS = 120


def explanation_schema(answers: list[str]) -> dict:
    """Constrains the explain step to one short line per answer.

    `answers` becomes an enum, so the model cannot explain an answer that is not
    on the board or invent a new one -- the labels have to match exactly for the
    explanations to be attachable to items afterwards.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["explanations"],
        "properties": {
            "explanations": {
                "type": "array",
                "minItems": 1,
                "maxItems": len(answers),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["answer", "why"],
                    "properties": {
                        "answer": {"type": "string", "enum": sorted(answers)},
                        "why": {
                            "type": "string",
                            "minLength": 3,
                            "maxLength": MAX_EXPLANATION_CHARS,
                        },
                    },
                },
            }
        },
    }


REFRAME_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "description"],
    "properties": {
        "title": {"type": "string", "minLength": 3, "maxLength": 60},
        "description": {"type": "string", "minLength": 3, "maxLength": 80},
    },
}


REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok", "problems", "misplaced_items"],
    "properties": {
        "ok": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
        "misplaced_items": {"type": "array", "items": {"type": "string"}},
    },
}
