-- Quiz Quiz: Zuordnungsfragen (matching questions).
--
-- One quiz = one topic, e.g. "Hauptstädte Europas". Players assign items
-- ("Berlin") to categories ("Deutschland"). Some items belong to no category at
-- all -- those are the fakes, and the player is meant to spot them.
--
-- This database stores questions only. Nothing about who played, what they
-- answered, or how they scored is persisted anywhere: grading happens in the
-- API and the result is returned, not written.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Topics
-- ---------------------------------------------------------------------------

create table quizzes (
    id           uuid primary key default gen_random_uuid(),
    slug         text not null unique,
    title        text not null,
    description  text,
    created_at   timestamptz not null default now(),

    -- Needed as a target for the composite foreign key on items below, which is
    -- what keeps an item from being assigned to another topic's category.
    unique (id)
);

comment on table quizzes is 'One Zuordnungs-topic, e.g. "Hauptstädte Europas".';
comment on column quizzes.slug is 'URL-safe identifier used by the frontend routes.';

-- ---------------------------------------------------------------------------
-- Categories -- the buckets items get assigned to ("Deutschland")
-- ---------------------------------------------------------------------------

create table categories (
    id        uuid primary key default gen_random_uuid(),
    quiz_id   uuid not null references quizzes (id) on delete cascade,
    label     text not null,
    position  integer not null default 0,

    unique (quiz_id, label),
    unique (id, quiz_id)
);

create index categories_quiz_id_position_idx on categories (quiz_id, position);

-- ---------------------------------------------------------------------------
-- Items -- the answer options ("Berlin", "Zürich")
-- ---------------------------------------------------------------------------

create table items (
    id           uuid primary key default gen_random_uuid(),
    quiz_id      uuid not null references quizzes (id) on delete cascade,
    category_id  uuid,
    label        text not null,
    position     integer not null default 0,

    unique (quiz_id, label),

    -- Composite FK: an item may only point at a category of its own quiz.
    -- Without the quiz_id in the key, "Berlin" from one topic could be assigned
    -- to "Italien" from another and the database would happily accept it.
    foreign key (category_id, quiz_id)
        references categories (id, quiz_id)
        on delete cascade
);

create index items_quiz_id_idx on items (quiz_id);
create index items_category_id_idx on items (category_id);

comment on column items.category_id is
    'NULL means this item is a fake -- it belongs to no category, and spotting '
    'it is part of the game. Never sent to players before they submit.';

-- ---------------------------------------------------------------------------
-- Row level security
--
-- Enabled with no policies. The API connects with the service-role key, which
-- bypasses RLS; anon and authenticated are granted nothing, so a leaked
-- publishable key reads zero rows -- including the answer key in
-- items.category_id.
-- ---------------------------------------------------------------------------

alter table quizzes    enable row level security;
alter table categories enable row level security;
alter table items      enable row level security;

-- Tables created inside a migration do not inherit Supabase's default
-- privileges, so without this PostgREST answers 42501 "permission denied".
grant usage on schema public to service_role;
grant all privileges on all tables in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;

alter default privileges in schema public
    grant all privileges on tables to service_role;
alter default privileges in schema public
    grant all privileges on sequences to service_role;
