-- Development seed data, reloaded by `supabase db reset`.
--
-- Content is German; identifiers stay English. Fixed UUIDs so links survive a
-- reset. Every topic deliberately includes fakes (category_id = NULL) -- items
-- that look plausible but belong to no category.

-- ===========================================================================
-- Hauptstädte Europas
-- ===========================================================================

insert into quizzes (id, slug, title, description)
values (
    '11111111-1111-4111-8111-111111111111',
    'hauptstaedte-europas',
    'Hauptstädte Europas',
    'Ordne die Städte ihren Ländern zu. Achtung: Nicht jede Stadt ist eine Hauptstadt.'
);

insert into categories (id, quiz_id, label, position)
values
    ('c1000001-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111', 'Deutschland', 1),
    ('c1000001-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111', 'Frankreich',  2),
    ('c1000001-0000-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111', 'Italien',     3),
    ('c1000001-0000-4000-8000-000000000004', '11111111-1111-4111-8111-111111111111', 'Spanien',     4);

insert into items (quiz_id, category_id, label, position)
values
    ('11111111-1111-4111-8111-111111111111', 'c1000001-0000-4000-8000-000000000001', 'Berlin',    1),
    ('11111111-1111-4111-8111-111111111111', 'c1000001-0000-4000-8000-000000000002', 'Paris',     2),
    ('11111111-1111-4111-8111-111111111111', 'c1000001-0000-4000-8000-000000000003', 'Rom',       3),
    ('11111111-1111-4111-8111-111111111111', 'c1000001-0000-4000-8000-000000000004', 'Madrid',    4),
    -- Fakes: große Städte, aber keine Hauptstädte.
    ('11111111-1111-4111-8111-111111111111', null, 'Barcelona', 5),
    ('11111111-1111-4111-8111-111111111111', null, 'München',   6),
    ('11111111-1111-4111-8111-111111111111', null, 'Mailand',   7);

-- ===========================================================================
-- Flüsse und ihre Länder -- categories with more than one correct item
-- ===========================================================================

insert into quizzes (id, slug, title, description)
values (
    '22222222-2222-4222-8222-222222222222',
    'fluesse-europas',
    'Flüsse Europas',
    'Durch welches Land fließt der Fluss? Manche Flüsse gibt es gar nicht.'
);

insert into categories (id, quiz_id, label, position)
values
    ('c2000002-0000-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222', 'Deutschland', 1),
    ('c2000002-0000-4000-8000-000000000002', '22222222-2222-4222-8222-222222222222', 'Frankreich',  2),
    ('c2000002-0000-4000-8000-000000000003', '22222222-2222-4222-8222-222222222222', 'Russland',    3);

insert into items (quiz_id, category_id, label, position)
values
    ('22222222-2222-4222-8222-222222222222', 'c2000002-0000-4000-8000-000000000001', 'Rhein',   1),
    ('22222222-2222-4222-8222-222222222222', 'c2000002-0000-4000-8000-000000000001', 'Elbe',    2),
    ('22222222-2222-4222-8222-222222222222', 'c2000002-0000-4000-8000-000000000002', 'Seine',   3),
    ('22222222-2222-4222-8222-222222222222', 'c2000002-0000-4000-8000-000000000002', 'Loire',   4),
    ('22222222-2222-4222-8222-222222222222', 'c2000002-0000-4000-8000-000000000003', 'Wolga',   5),
    -- Fakes: erfundene bzw. nicht passende Flussnamen.
    ('22222222-2222-4222-8222-222222222222', null, 'Amazonas', 6),
    ('22222222-2222-4222-8222-222222222222', null, 'Sambesi',  7);

-- ===========================================================================
-- Erfindungen und ihre Erfinder
-- ===========================================================================

insert into quizzes (id, slug, title, description)
values (
    '33333333-3333-4333-8333-333333333333',
    'erfindungen',
    'Erfindungen',
    'Wer hat es erfunden? Zwei der Erfindungen stammen von niemandem aus der Liste.'
);

insert into categories (id, quiz_id, label, position)
values
    ('c3000003-0000-4000-8000-000000000001', '33333333-3333-4333-8333-333333333333', 'Johannes Gutenberg', 1),
    ('c3000003-0000-4000-8000-000000000002', '33333333-3333-4333-8333-333333333333', 'Karl Benz',          2),
    ('c3000003-0000-4000-8000-000000000003', '33333333-3333-4333-8333-333333333333', 'Alexander Fleming',  3);

insert into items (quiz_id, category_id, label, position)
values
    ('33333333-3333-4333-8333-333333333333', 'c3000003-0000-4000-8000-000000000001', 'Buchdruck mit beweglichen Lettern', 1),
    ('33333333-3333-4333-8333-333333333333', 'c3000003-0000-4000-8000-000000000002', 'Automobil mit Verbrennungsmotor',   2),
    ('33333333-3333-4333-8333-333333333333', 'c3000003-0000-4000-8000-000000000003', 'Penicillin',                        3),
    -- Fakes: echte Erfindungen, aber nicht von den genannten Personen.
    ('33333333-3333-4333-8333-333333333333', null, 'Telefon',    4),
    ('33333333-3333-4333-8333-333333333333', null, 'Glühbirne', 5);
