-- Picture questions: the answer is an image rather than a word.
--
-- "Ordne jede Brücke ihrem Land zu", with eight photographs in the pool. The
-- pairing is unchanged -- one category, one answer -- so nothing about the game
-- rules moves. What changes is what an answer *is*, and that is a property of
-- the question, not of each item: a board must not mix words and pictures, or
-- the ones with text are simply easier.
--
-- Hence `answer_kind` on the quiz. `items.label` stays NOT NULL for every kind:
-- a picture still needs a name for the review screen, for the explanation to
-- read against, and for alt text once the round is over. It is simply withheld
-- while the answer is still in play -- see `_round_view` in the API, which is
-- the only place that decides what a player may see.
--
-- Attribution is a licence obligation, not a nicety. Most Commons images are
-- CC BY-SA and require credit; storing the licence beside the file is what
-- makes rendering it possible, and a picture with no `image_licence` should
-- never be shown.

alter table quizzes
  add column answer_kind text not null default 'text'
    check (answer_kind in ('text', 'image'));

comment on column quizzes.answer_kind is
  'How this quiz''s answers are presented. "image" hides item labels until the round is over.';

alter table items
  -- The Commons file name, not a URL. Thumbnail URLs contain a hash-derived
  -- path that cannot be computed from the name, but Special:FilePath resolves
  -- a bare name and takes a width -- so the name is the stable thing to keep
  -- and the URL is built when it is needed.
  add column image_file text,
  add column image_credit text,
  add column image_licence text,
  add column image_licence_url text;

comment on column items.image_file is
  'Wikimedia Commons file name, e.g. "Cityscape Berlin.jpg". Rendered via Special:FilePath.';

-- Either an item has a usable picture or it has none. A file with no licence
-- cannot be shown -- there would be no way to credit it -- so half-filled rows
-- are refused here rather than discovered by a blank card mid-game.
alter table items
  add constraint items_image_is_complete check (
    (image_file is null and image_licence is null)
    or (image_file is not null and image_licence is not null)
  );

-- Every quiz drawn for a picture round is filtered on this, so it is worth an
-- index even at this size.
create index quizzes_answer_kind_idx on quizzes (answer_kind);
