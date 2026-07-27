-- A question is a one-to-one pairing.
--
-- Before this, an item with a NULL category_id was a "fake" -- an answer that
-- belonged to no category, and spotting it was part of the game. That mechanic
-- is gone: every answer now belongs to exactly one category, and every category
-- holds exactly one answer.
--
-- Two constraints express it, and between them they make the old shape
-- unstorable rather than merely discouraged.

-- Existing questions cannot satisfy either rule -- every seeded one has fakes
-- and multi-answer categories -- so the pool is cleared and refilled from the
-- rewritten seed. Nothing is recoverable here that the seed does not replace.
delete from items;
delete from categories;
delete from quizzes;

-- 1. No answer without a category. This is what removes the fake.
alter table items
    alter column category_id set not null;

-- 2. No category with two answers. Without this the pairing is only a
--    convention, and one generated question with two answers under one
--    category would be accepted and then be unplayable -- both answers correct,
--    only one accepted.
alter table items
    add constraint items_one_answer_per_category
    unique (quiz_id, category_id);
