-- A one-line reason per answer, shown once the question has been answered.
--
-- Same secrecy rule as quizzes.source_url: this text gives the answer away, so
-- it must never appear in a payload a player receives while still playing. The
-- API keeps that split in `ItemPublic` (no explanation) versus `ItemSolution`
-- and `ItemResult` (explanation included).
--
-- Nullable on purpose. Explanations come from a separate, optional pass in the
-- ingest pipeline, and every question seeded or generated before this migration
-- has none. A missing explanation renders as nothing rather than as an error.
alter table items
    add column explanation text;

-- Short enough to read at a glance -- one line beside the answer, not a
-- paragraph. The generator is constrained to roughly this at decoding time;
-- this is the backstop for anything written by hand or by another tool.
alter table items
    add constraint items_explanation_is_brief
    check (explanation is null or char_length(explanation) <= 160);
