-- Where a question came from, and how hard it is.
--
-- `source_url` exists so a player can check the answer against the material it
-- was written from. It is shown only after a question has been answered --
-- during play it would be a link straight to the answers.
--
-- `difficulty` is set by whoever writes the question; for machine-generated
-- questions the model classifies it (see tools/ingest/).

create type difficulty as enum ('easy', 'medium', 'hard');

alter table quizzes
    add column source_url   text,
    add column source_title text,
    add column difficulty   difficulty not null default 'medium';

comment on column quizzes.source_url is
    'Canonical URL of the material this question was written from. Revealed to '
    'players only once the question is over.';
comment on column quizzes.source_title is
    'Human-readable label for source_url, e.g. the article title.';

-- Only sanity-check the shape; the ingest pipeline is what guarantees a URL
-- resolves, by taking it from the source API rather than constructing it.
alter table quizzes
    add constraint quizzes_source_url_is_http
    check (source_url is null or source_url ~ '^https?://');

create index quizzes_difficulty_idx on quizzes (difficulty);
