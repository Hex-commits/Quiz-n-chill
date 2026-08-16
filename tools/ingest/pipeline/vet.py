"""Judging borrowed pairs one at a time, and rejecting the ones that do not belong.

`augment` finds pairs in other articles. Nothing there decides whether a found
pair asks the *same question* as the board, because that is a judgement about
meaning and there is no string test for it that survives contact with a board of
painters. This is where that judgement goes.

A rejection is not the end of the pair's slot. `vet` reports what it threw out,
and the graph sends the question back to `augment` to look somewhere it has not
read yet -- so a bad candidate costs a search rather than the question.

**What it is worth today.** Measured on seven hand-built cases against
`glm4:9b`, four framings of this judgement all scored around chance:

    holistic "is this board homogeneous"   missed every bad case
    per-pair "does it follow the rule"     4/7   -- graded on shape, not meaning
    per-pair "name the question first"     4/7   -- copied the board's question back
    "answer the board's question"          2/5   -- ignored the label entirely

So the step is **off by default**, and switched on with `INGEST_VET=true`; the
judge is `INGEST_JUDGE_MODEL`, falling back to the run's own model. Environment
rather than flags because both describe the machine -- whether a judge worth
using is installed there -- not the run.

The mechanism is sound and the judge is not, and those are different problems:
this way the first is solved and waiting for the second.

Those seven cases have not been re-run since the default model became
`gemma4:12b`, and this is the one note in the package where that matters: the
table above is not a fact about the step, it is a fact about a model that is no
longer installed. A judge good enough flips a default. The cases are cheap to
rebuild and the way to settle it is to rebuild them -- not to leave the step off
because a 9B could not do it, and not to switch it on because a newer model
probably can.

Nothing here calls a model. `judge` is passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..domain.models import GeneratedPair, GeneratedQuestion

# How many `augment -> vet` passes one question may have. Two, because the point
# of a rejection is to go and look somewhere else once -- a third pass is
# reading the fourth-best article for the same shortfall, and by then the
# question is not being saved so much as forced.
MAX_ROUNDS = 2


@dataclass(frozen=True)
class Verdict:
    """What survived, what did not, and why."""

    kept: tuple[GeneratedPair, ...] = ()
    rejected: tuple[GeneratedPair, ...] = ()
    # Rejected pair -> the judge's reason, for the trace and the report.
    reasons: tuple[tuple[str, str], ...] = ()

    @property
    def rejected_any(self) -> bool:
        return bool(self.rejected)

    @property
    def detail(self) -> str:
        if not self.rejected:
            return f"{len(self.kept)} kept"
        worst = self.reasons[0][1] if self.reasons else ""
        return f"{len(self.kept)} kept, {len(self.rejected)} rejected -- {worst}"[:160]


def vet(
    question: GeneratedQuestion,
    candidates: list[GeneratedPair],
    judge: Callable[[GeneratedQuestion, GeneratedPair], tuple[bool, str]],
) -> Verdict:
    """Keep the candidates that ask the same question as the board.

    `judge` is asked once per candidate rather than once per board. That is
    deliberate: a model asked "are these all the same kind of thing" answers
    about the set and reliably says yes, where one asked about a single pair at
    least has something specific to be wrong about.

    The board it judges against is the *original* question -- candidates are
    never compared to each other, so one that slipped through cannot become the
    precedent that admits the next.
    """
    kept: list[GeneratedPair] = []
    rejected: list[GeneratedPair] = []
    reasons: list[tuple[str, str]] = []

    for candidate in candidates:
        try:
            fits, why = judge(question, candidate)
        except Exception:  # noqa: BLE001 - a broken judge must not admit everything
            # Refusing on error rather than passing: the whole point of this step
            # is to be the thing that says no, and a judge that cannot answer has
            # not said yes.
            fits, why = False, "judge unavailable"
        if fits:
            kept.append(candidate)
        else:
            rejected.append(candidate)
            reasons.append((f"{candidate.label} -> {candidate.answer}", why))

    return Verdict(tuple(kept), tuple(rejected), tuple(reasons))
