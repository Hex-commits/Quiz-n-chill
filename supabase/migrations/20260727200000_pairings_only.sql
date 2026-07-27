-- A question is a one-to-one pairing.
--
-- Before this, an item with a NULL category_id was a "fake" -- an answer that
-- belonged to no category, and spotting it was part of the game. That mechanic
-- is gone: every answer now belongs to exactly one category, and every category
-- holds exactly one answer.
--
-- Two constraints express it, and between them they make the old shape
-- unstorable rather than merely discouraged.

-- Questions written for the old design cannot satisfy either rule. This
-- migration refuses to run rather than deleting them: it also runs against
-- databases holding generated questions that took hours of model time and
-- exist nowhere else, and a migration is the last place a silent `delete from`
-- belongs. Clearing the pool is a decision for whoever is at the keyboard.
do $$
declare
    orphans bigint;
    crowded bigint;
begin
    select count(*) into orphans
      from items
     where category_id is null;

    select count(*) into crowded
      from (
            select 1
              from items
             where category_id is not null
             group by quiz_id, category_id
            having count(*) > 1
           ) as offending;

    if orphans > 0 or crowded > 0 then
        raise exception
            'Cannot enforce one-to-one pairings: % answer(s) without a category, % category/categories holding more than one answer.',
            orphans, crowded
        using hint =
            'These are questions from the removed fake-based design. Delete the '
            'affected quizzes and re-run. To clear the whole pool and refill it '
            'from the rewritten seed: delete from items; delete from categories; '
            'delete from quizzes;';
    end if;
end
$$;

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
