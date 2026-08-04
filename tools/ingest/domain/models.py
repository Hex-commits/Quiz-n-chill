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

# -- what the generator produces -----------------------------------------


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

    # Filled by the explain step, not by the extract grammar -- which is why it
    # is absent from `question_schema`. Keyed by answer label.
    explanations: dict[str, str] = Field(default_factory=dict)

    @property
    def labels(self) -> list[str]:
        return [pair.label for pair in self.pairs]

    @property
    def answers(self) -> list[str]:
        return [pair.answer for pair in self.pairs]

    # Kept for the callers that just want "everything on the board". With no
    # extras left, that is simply the answers.
    all_items = answers


class Extraction(BaseModel):
    """One pass of the extract step: the parsed drafts and the raw reply.

    Several drafts, because one article usually holds more than one question and
    asking for one means taking whichever the model wrote first. Which of them is
    worth a board is a judgement, and it belongs to `select`.

    The raw dict is kept because the repair turn has to show the model its own
    previous answer, and because a reply that fails to parse still has to be
    reported as something more useful than "it broke".
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    raw: dict = Field(default_factory=dict)
    questions: list[GeneratedQuestion] = Field(default_factory=list)
    error: str = ""

    @property
    def question(self) -> GeneratedQuestion | None:
        """The first draft, for callers that only ever wanted one."""
        return self.questions[0] if self.questions else None


# -- what the reviewer produces ------------------------------------------


class Review(BaseModel):
    """The second pass's verdict on one question."""

    ok: bool = True
    problems: list[str] = Field(default_factory=list)
    # The only content defect a pairing can have: an answer sitting beside the
    # wrong category. With no extras on the board there is nothing else to get
    # wrong -- which is why `bad_fakes` and `weak_fakes` are gone.
    misplaced_items: list[str] = Field(default_factory=list)
    # True when the reviewer could not run at all. The question is kept, but the
    # report has to say it went unchecked rather than imply it passed.
    skipped: bool = False


# -- the grammars handed to Ollama ---------------------------------------


# How many drafts one extract call asks for. Two rather than four: the whole
# batch shares one 8k context with the article, and every draft is 10-14 pairs,
# so the fourth is written by a model that has already spent its attention. Two
# good angles is what a Wikipedia article usually holds anyway.
DEFAULT_DRAFTS = 2


def questions_schema(subject_slugs: list[str], count: int = DEFAULT_DRAFTS) -> dict:
    """Constrains the extract step to at most `count` drafts of one article.

    `minItems` is 1, not `count`: an article that only supports one question must
    be able to return one rather than pad the batch, and a grammar demanding two
    is a grammar that makes the model invent the second. Declining is a single
    draft with `usable: false`.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": max(1, count),
                "items": question_schema(subject_slugs),
            }
        },
    }


def question_schema(subject_slugs: list[str]) -> dict:
    """Constrains one draft. Every field required; enums where possible."""
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
            # One object per pairing, so the grammar itself makes "two answers
            # in one category" unrepresentable rather than merely invalid.
            #
            # No `minItems`, and that is the opposite of what it looks like.
            # `MIN_PAIRS` was here, and Ollama does enforce it -- which made a
            # short reply *unrepresentable*, so a model with too little material
            # could not take the way out the prompt offers it. Measured on
            # glm4:9b with a four-fact article, three runs each:
            #
            #   minItems=10 -> `usable: true`, 10-12 pairs, 0/3/8 of the answers
            #                  duplicated -- it padded the board by repeating
            #                  itself, and `validate` then reports a duplicate
            #                  answer, which the repair loop argues with for
            #                  three attempts before the article is dropped for
            #                  the wrong reason.
            #   minItems=0  -> four clean pairs, every time.
            #
            # And it bought nothing where it looked like it might. On the real
            # leads of `Schach` and `Kaffee`, three runs each: ten pairs and no
            # duplicates with the floor and without it, 3/3 acceptable both ways.
            # The floor was not the pressure keeping boards full.
            #
            # So the floor is a *validator* rule, and it has to stay one --
            # falling below it is how the model declines and how `augment` gets a
            # question to top up. `maxItems` stays, because a ceiling needs no
            # escape hatch.
            "pairs": {
                "type": "array",
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


# Roughly one line beside the answer. Enforced at decoding time rather than
# checked afterwards, because "keep it short" in a prompt is a suggestion and a
# `maxLength` in the grammar is not. The database repeats it as a constraint.
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


# Bounded at decoding time rather than asked for in words. "Genau ein kurzer
# Satz" in a prompt is a suggestion a 9B model ignores -- it returned three
# sentences, one of them the prompt's own example pasted verbatim. A `maxLength`
# in the grammar is not a suggestion.
#
# `shown` and `asked` come first, and constrained decoding emits properties in
# declaration order, so the model has to name which side is the photograph and
# which side the player supplies *before* it may write the instruction that
# depends on that. Same trick as `VET_SCHEMA`, for the same reason: this is the
# one model output nothing downstream can check, because it is prose a player
# reads rather than data a validator sees. Getting the direction backwards --
# "Welches Land gehört zu dieser Hauptstadt?" over photographs of countries --
# is the failure it exists to prevent.
REFRAME_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["shown", "asked", "title", "description"],
    "properties": {
        "shown": {"type": "string", "minLength": 2, "maxLength": 60},
        "asked": {"type": "string", "minLength": 2, "maxLength": 60},
        "title": {"type": "string", "minLength": 3, "maxLength": 60},
        "description": {"type": "string", "minLength": 3, "maxLength": 80},
    },
}


def more_pairs_schema(needed: int) -> dict:
    """Constrains the augment step to at most `needed` further pairings.

    `maxItems` is the point of it. Asked in words for "up to two more", a 9B
    model returns six and lets the caller sort it out -- and the caller then
    either truncates arbitrarily or overshoots `MAX_PAIRS` and fails the very
    check this step exists to satisfy. The bound belongs where it cannot be
    ignored.

    `minItems` is 0 on purpose: most articles genuinely have nothing to add, and
    a grammar that demands at least one pair is a grammar that makes the model
    invent one.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["pairs"],
        "properties": {
            "pairs": {
                "type": "array",
                "minItems": 0,
                "maxItems": max(1, needed),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "answer"],
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "answer": {"type": "string", "minLength": 1},
                    },
                },
            }
        },
    }


# `relation` before `fits`, because constrained decoding emits properties in the
# order they are declared: naming what the board asks is what forces the
# judgement to be about meaning rather than about shape.
VET_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relation", "answers_it", "fits"],
    "properties": {
        "relation": {"type": "string", "maxLength": 90},
        "answers_it": {"type": "string", "maxLength": 90},
        "fits": {"type": "boolean"},
    },
}


# `keep` holds the *numbers* the prompt labelled the drafts with, as an enum of
# strings rather than integers: a 9B model asked for an integer array will
# cheerfully return `[1, 2]` for a batch of one, and an enum of the labels that
# actually exist cannot name a draft that is not there.
#
# `verdict` first, so ordered decoding forces the model to say what the drafts
# are worth before it says which to keep -- without it the field is a coin toss
# and the sentence afterwards rationalises it.
def selection_schema(count: int) -> dict:
    """Constrains the select step to a subset of `count` drafts, possibly empty."""
    labels = [str(index) for index in range(1, max(1, count) + 1)]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "keep"],
        "properties": {
            "verdict": {"type": "string", "minLength": 3, "maxLength": 200},
            "keep": {
                "type": "array",
                # Empty is a legitimate answer: two well-formed drafts that teach
                # nobody anything are two drafts to drop, and the pipeline has
                # another article. A `minItems: 1` here would make the step
                # decorative.
                "minItems": 0,
                "maxItems": len(labels),
                "items": {"type": "string", "enum": labels},
            },
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
