-- Subjects: the pool a game is drawn from.
--
-- Naming matters here. `categories` already means "the buckets inside one
-- Zuordnungsfrage" (Deutschland, Frankreich). A subject is a level above that:
-- the area a whole question belongs to (Geografie, Musik). Two different things
-- called "category" in the same UI would be genuinely confusing mid-game.
--
--   subjects          Geografie
--     └ quizzes       "Hauptstädte Europas"
--         ├ categories  Deutschland, Frankreich
--         └ items       Berlin, Paris, Zürich (fake)

create table subjects (
    id          uuid primary key default gen_random_uuid(),
    slug        text not null unique,
    name        text not null,
    description text,
    position    integer not null default 0
);

comment on table subjects is
    'Quiz-pool area. A game draws its rounds evenly across the chosen subjects.';

-- Every quiz belongs to exactly one subject. Safe as NOT NULL because
-- migrations run against an empty database before the seed.
alter table quizzes
    add column subject_id uuid not null references subjects (id) on delete cascade;

create index quizzes_subject_id_idx on quizzes (subject_id);

alter table subjects enable row level security;

grant all privileges on table subjects to service_role;
