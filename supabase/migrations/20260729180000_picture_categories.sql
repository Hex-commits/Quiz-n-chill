-- Picture questions, the other way round: the *category* is the photograph.
--
-- The first cut put pictures in the answer pool -- ten text targets on the
-- board, ten photographs to drag onto them. That is backwards for the question
-- this feature exists to ask. "Locate where this bridge is" wants the bridge on
-- the board, being looked at, with the countries as the things you assign to
-- it. A photograph is the *subject* of a Zuordnung, not a token you place.
--
-- Consequences worth stating, because they are why this is a move rather than
-- an addition:
--
-- * **The redaction moves, it does not go away.** `categories.label` holds the
--   name of the thing in the photograph -- "Albert Bridge" -- and printing that
--   above the picture answers the question the picture was chosen to ask, while
--   naming the city that is usually the paired answer. So the *name* is still
--   withheld while a picture round is being played, and returns for the review.
--   What did go away is the withholding of `items.label`, which used to be the
--   answer itself and had to be stripped on every read path that touched it.
--
-- * **Attribution is now always rendered**, which is what CC BY-SA actually
--   requires. The old design withheld the credit line during play because an
--   artist field can describe its subject, and licence compliance lost to a
--   game rule. Here the two stop fighting: an artist line under a photograph
--   describes the photograph, which the player is already looking at.
--
-- * `items` goes back to being plain text. A picture question's answers are
--   words -- "Türkei", "Ungarn" -- exactly like every other question's.

-- The flag moves with the pictures. `answer_kind` described a property the
-- answers no longer have.
alter table quizzes rename column answer_kind to category_kind;

comment on column quizzes.category_kind is
  'How this quiz''s categories are presented. "image" means each category is a photograph and its answers are words.';

alter index quizzes_answer_kind_idx rename to quizzes_category_kind_idx;

-- Same four columns, same meaning, one table to the left. The Commons file
-- name rather than a URL: thumbnail URLs contain a hash-derived path that
-- cannot be computed from the name, but Special:FilePath resolves a bare name
-- and takes a width -- so the name is the stable thing to keep and the URL is
-- built when it is needed.
alter table categories
  add column image_file text,
  add column image_credit text,
  add column image_licence text,
  add column image_licence_url text;

comment on column categories.image_file is
  'Wikimedia Commons file name, e.g. "Cityscape Berlin.jpg". Rendered via Special:FilePath.';

-- Either a category has a usable picture or it has none. A file with no licence
-- cannot be shown -- there would be no way to credit it -- so half-filled rows
-- are refused here rather than discovered by a blank card mid-game.
alter table categories
  add constraint categories_image_is_complete check (
    (image_file is null and image_licence is null)
    or (image_file is not null and image_licence is not null)
  );

-- The old picture questions cannot be carried across: their pairing points the
-- wrong way. Turning `Türkei -> [photo of a bridge]` into
-- `[photo of a bridge] -> Türkei` means swapping every category label with its
-- item label, and the titles and descriptions were written for the old
-- direction too. Regenerating them costs one ingest run and yields questions
-- the current pipeline actually produces; migrating them yields questions
-- nothing would write again. Text questions are untouched.
delete from quizzes where category_kind = 'image';

alter table items
  drop constraint items_image_is_complete,
  drop column image_file,
  drop column image_credit,
  drop column image_licence,
  drop column image_licence_url;
