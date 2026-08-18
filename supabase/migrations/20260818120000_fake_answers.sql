-- Fakes come back: answers in the pool that belong to no category.
--
-- `20260727200000_pairings_only.sql` removed them, and the reasoning there
-- still holds for the *pairing*: one category, one answer, no board where two
-- answers are both defensible. What it also removed, as a side effect of how it
-- was written, was the pool being larger than the board. Every answer on the
-- table belonged somewhere, so the last one placed itself -- by the end of a
-- round the player was reading the leftovers rather than the question.
--
-- A fake restores the doubt. Two per board, written to sit close enough to the
-- subject that ruling them out means knowing the material.
--
-- Only the NOT NULL goes. `items_one_answer_per_category` stays exactly as it
-- was: Postgres treats NULLs as distinct in a unique constraint, so the rule
-- still refuses a second real answer under one category while placing no bound
-- at all on how many fakes a quiz holds. The half of `pairings_only` that was
-- about the pairing is untouched; only the half that made the pool and the
-- board the same set is undone.
--
-- No backfill: existing questions simply have no fakes, which is the shape the
-- code has to handle anyway for a board whose fakes were all trimmed off.

alter table items
    alter column category_id drop not null;

comment on column items.category_id is
    'NULL means this answer is a fake -- it belongs to no category, and saying '
    'so is a correct move. Withheld from players until the round is over.';

-- Reading the pool needs to tell the two kinds apart, and every board load does
-- it. Partial, because the fakes are the small side: two per question against
-- ten to thirty pairs.
create index items_fakes_idx on items (quiz_id) where category_id is null;
