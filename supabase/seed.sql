-- Development seed data, reloaded by `supabase db reset`.
--
-- Content is German; identifiers stay English. Every question carries fakes --
-- plausible answers that belong to no category at all, which the player is
-- meant to spot.
--
-- Each question is one row of the `spec` table below:
--
--   subject, slug, title, description,
--   '[["Kategorie", ["Antwort", "Antwort"]], ...]',   -- ordered groups
--   array['Fake', 'Fake']                             -- belong nowhere
--
-- The inserts are driven off that one table rather than hundreds of hand-written
-- UUIDs. It is a single statement on purpose: a PL/pgSQL helper would read
-- better still, but the Supabase CLI's seed runner cannot handle a $$-quoted
-- function body, so this stays plain SQL.

insert into subjects (slug, name, description, position) values
    ('geografie',         'Geografie',         'Länder, Städte, Flüsse und Grenzen.',            1),
    ('geschichte',        'Geschichte',        'Herrscher, Epochen und historische Bauwerke.',   2),
    ('naturwissenschaft', 'Naturwissenschaft', 'Chemie, Astronomie und der menschliche Körper.', 3),
    ('kunst-kultur',      'Kunst & Kultur',    'Gemälde, Literatur und Baustile.',               4),
    ('sport',             'Sport',             'Disziplinen, Vereine und Ausrüstung.',           5),
    ('technik',           'Technik',           'Erfindungen, Programmiersprachen und Marken.',   6),
    ('musik',             'Musik',             'Instrumente, Komponisten und Bands.',            7),
    ('film-fernsehen',    'Film & Fernsehen',  'Regisseure, Serienfiguren und Genres.',          8),
    ('essen-trinken',     'Essen & Trinken',   'Gerichte, Zutaten und Getränke.',                9);


with spec (subject_slug, slug, title, description, groups, fakes) as (
    values

    -- === Geografie =========================================================
    ('geografie', 'hauptstaedte-europas', 'Hauptstädte Europas',
     'Ordne die Städte ihren Ländern zu. Achtung: Nicht jede Stadt ist eine Hauptstadt.',
     '[["Deutschland", ["Berlin"]],
       ["Frankreich",  ["Paris"]],
       ["Italien",     ["Rom"]],
       ["Spanien",     ["Madrid"]]]'::jsonb,
     array['Barcelona', 'München', 'Mailand']),

    ('geografie', 'fluesse-europas', 'Flüsse Europas',
     'Durch welches Land fließt der Fluss? Zwei Flüsse liegen auf einem anderen Kontinent.',
     '[["Deutschland", ["Rhein", "Elbe"]],
       ["Frankreich",  ["Seine", "Loire"]],
       ["Russland",    ["Wolga"]]]'::jsonb,
     array['Amazonas', 'Sambesi']),

    ('geografie', 'laender-waehrungen', 'Länder & Währungen',
     'Welche Währung gehört zu welchem Land?',
     '[["Japan",                  ["Yen"]],
       ["Schweiz",                ["Franken"]],
       ["Vereinigtes Königreich", ["Pfund Sterling"]],
       ["Polen",                  ["Złoty"]]]'::jsonb,
     array['Rubel', 'Dänische Krone']),

    -- === Geschichte ========================================================
    ('geschichte', 'beruehmte-herrscher', 'Berühmte Herrscher',
     'Welcher Herrscher regierte welches Reich?',
     '[["Frankreich", ["Ludwig XIV.", "Napoleon Bonaparte"]],
       ["Russland",   ["Katharina die Große", "Peter der Große"]],
       ["Ägypten",    ["Kleopatra"]]]'::jsonb,
     array['Alexander der Große', 'Dschingis Khan']),

    ('geschichte', 'ereignisse-jahrhunderte', 'Ereignisse & Jahrhunderte',
     'In welchem Jahrhundert geschah das? Zwei Ereignisse liegen weit davor.',
     '[["18. Jahrhundert", ["Französische Revolution", "Amerikanische Unabhängigkeitserklärung"]],
       ["19. Jahrhundert", ["Deutsche Reichsgründung"]],
       ["20. Jahrhundert", ["Erster Weltkrieg", "Mondlandung"]]]'::jsonb,
     array['Fall von Konstantinopel', 'Entdeckung Amerikas']),

    ('geschichte', 'historische-bauwerke', 'Historische Bauwerke',
     'In welchem Land steht das Bauwerk?',
     '[["Ägypten", ["Pyramiden von Gizeh"]],
       ["China",   ["Chinesische Mauer"]],
       ["Italien", ["Kolosseum"]],
       ["Indien",  ["Taj Mahal"]]]'::jsonb,
     array['Machu Picchu', 'Stonehenge']),

    -- === Naturwissenschaft =================================================
    ('naturwissenschaft', 'chemische-elemente', 'Chemische Elemente',
     'Ordne die Elemente ihrer Gruppe zu. Zwei Einträge sind gar keine Elemente.',
     '[["Metalle",      ["Eisen", "Kupfer"]],
       ["Edelgase",     ["Helium", "Neon"]],
       ["Nichtmetalle", ["Sauerstoff", "Schwefel"]]]'::jsonb,
     array['Wasser', 'Bronze']),

    ('naturwissenschaft', 'planeten', 'Planeten des Sonnensystems',
     'Gasriese oder Gesteinsplanet? Drei Himmelskörper sind gar keine Planeten.',
     '[["Gasriesen",        ["Jupiter", "Saturn"]],
       ["Gesteinsplaneten", ["Merkur", "Venus", "Erde", "Mars"]]]'::jsonb,
     array['Pluto', 'Titan', 'Ceres']),

    ('naturwissenschaft', 'organe-systeme', 'Organe & Organsysteme',
     'Zu welchem System gehört das Organ?',
     '[["Herz-Kreislauf-System", ["Herz", "Arterien"]],
       ["Verdauungssystem",      ["Magen", "Leber", "Dünndarm"]],
       ["Nervensystem",          ["Gehirn", "Rückenmark"]]]'::jsonb,
     array['Bizeps', 'Kniescheibe']),

    -- === Kunst & Kultur ====================================================
    ('kunst-kultur', 'gemaelde-maler', 'Gemälde & Maler',
     'Wer hat das Bild gemalt?',
     '[["Vincent van Gogh",  ["Sternennacht", "Sonnenblumen"]],
       ["Leonardo da Vinci", ["Mona Lisa", "Das Abendmahl"]],
       ["Pablo Picasso",     ["Guernica"]]]'::jsonb,
     array['Der Schrei', 'Die Geburt der Venus']),

    ('kunst-kultur', 'werke-autoren', 'Werke & Autoren',
     'Wer hat das Werk geschrieben?',
     '[["Johann Wolfgang von Goethe", ["Faust", "Die Leiden des jungen Werthers"]],
       ["William Shakespeare",        ["Hamlet", "Romeo und Julia"]],
       ["Franz Kafka",                ["Die Verwandlung", "Der Prozess"]]]'::jsonb,
     array['Krieg und Frieden', 'Der alte Mann und das Meer']),

    ('kunst-kultur', 'bauwerke-baustile', 'Bauwerke & Baustile',
     'In welchem Stil wurde gebaut?',
     '[["Gotik",   ["Kölner Dom", "Notre-Dame de Paris"]],
       ["Barock",  ["Schloss Versailles", "Zwinger Dresden"]],
       ["Moderne", ["Bauhaus Dessau"]]]'::jsonb,
     array['Kolosseum', 'Hagia Sophia']),

    -- === Sport =============================================================
    ('sport', 'sportarten-geraete', 'Sportarten & Geräte',
     'Welches Gerät gehört zu welcher Sportart?',
     '[["Tennis",    ["Filzball", "Tennisschläger"]],
       ["Golf",      ["Golfball", "Abschlagtee"]],
       ["Eishockey", ["Puck", "Eishockeyschläger"]]]'::jsonb,
     array['Speer', 'Diskus']),

    ('sport', 'vereine-laender', 'Fußballvereine & Länder',
     'In welchem Land spielt der Verein?',
     '[["Deutschland", ["FC Bayern München", "Borussia Dortmund"]],
       ["Spanien",     ["Real Madrid", "FC Barcelona"]],
       ["England",     ["Manchester United"]],
       ["Italien",     ["Juventus Turin"]]]'::jsonb,
     array['Ajax Amsterdam', 'Benfica Lissabon']),

    ('sport', 'olympische-disziplinen', 'Olympische Disziplinen',
     'Zu welcher Sportart gehört die Disziplin?',
     '[["Leichtathletik", ["Speerwurf", "Stabhochsprung", "Marathon"]],
       ["Schwimmen",      ["Brustschwimmen", "Delfinschwimmen"]],
       ["Turnen",         ["Reck", "Barren"]]]'::jsonb,
     array['Slalom', 'Dressur']),

    -- === Technik ===========================================================
    ('technik', 'erfindungen', 'Erfindungen & Erfinder',
     'Wer hat es erfunden? Zwei Erfindungen stammen von niemandem aus der Liste.',
     '[["Johannes Gutenberg", ["Buchdruck mit beweglichen Lettern"]],
       ["Karl Benz",          ["Automobil mit Verbrennungsmotor"]],
       ["Alexander Fleming",  ["Penicillin"]]]'::jsonb,
     array['Telefon', 'Glühbirne']),

    ('technik', 'programmiersprachen', 'Programmiersprachen',
     'Wofür wird die Sprache typischerweise eingesetzt? Zwei sind gar keine Programmiersprachen.',
     '[["Webentwicklung",       ["JavaScript", "TypeScript"]],
       ["Systemprogrammierung", ["C", "Rust"]],
       ["Datenanalyse",         ["Python", "R"]]]'::jsonb,
     array['HTML', 'CSS']),

    ('technik', 'automarken-laender', 'Automarken & Länder',
     'Aus welchem Land stammt die Marke?',
     '[["Deutschland", ["Volkswagen", "BMW"]],
       ["Japan",       ["Toyota", "Honda"]],
       ["Italien",     ["Ferrari"]],
       ["Schweden",    ["Volvo"]]]'::jsonb,
     array['Renault', 'Ford']),

    -- === Musik =============================================================
    ('musik', 'instrumente-familien', 'Instrumente & Familien',
     'Zu welcher Instrumentenfamilie gehört das Instrument?',
     '[["Streichinstrumente", ["Violine", "Violoncello"]],
       ["Blasinstrumente",    ["Trompete", "Querflöte"]],
       ["Schlaginstrumente",  ["Pauke", "Kleine Trommel"]]]'::jsonb,
     array['Klavier', 'Harfe']),

    ('musik', 'komponisten-epochen', 'Komponisten & Epochen',
     'In welcher Epoche komponierte er?',
     '[["Barock",   ["Johann Sebastian Bach", "Georg Friedrich Händel"]],
       ["Klassik",  ["Wolfgang Amadeus Mozart", "Joseph Haydn"]],
       ["Romantik", ["Frédéric Chopin", "Robert Schumann"]]]'::jsonb,
     array['Igor Strawinsky', 'Claude Debussy']),

    ('musik', 'bands-herkunft', 'Bands & Herkunftsländer',
     'Aus welchem Land kommt die Band?',
     '[["Vereinigtes Königreich", ["The Beatles", "Queen"]],
       ["USA",                    ["Nirvana", "The Beach Boys"]],
       ["Schweden",               ["ABBA"]]]'::jsonb,
     array['Rammstein', 'U2']),

    -- === Film & Fernsehen ==================================================
    ('film-fernsehen', 'regisseure-filme', 'Regisseure & Filme',
     'Wer hat Regie geführt?',
     '[["Steven Spielberg",  ["Jurassic Park", "Der weiße Hai"]],
       ["Quentin Tarantino", ["Pulp Fiction", "Kill Bill"]],
       ["Christopher Nolan", ["Inception", "Interstellar"]]]'::jsonb,
     array['Titanic', 'Der Pate']),

    ('film-fernsehen', 'figuren-serien', 'Figuren & Serien',
     'Aus welcher Serie stammt die Figur?',
     '[["Die Simpsons",    ["Homer Simpson", "Bart Simpson"]],
       ["Game of Thrones", ["Jon Schnee", "Daenerys Targaryen"]],
       ["Breaking Bad",    ["Walter White", "Jesse Pinkman"]]]'::jsonb,
     array['Michael Scott', 'Tony Soprano']),

    ('film-fernsehen', 'filmgenres', 'Filmgenres',
     'Zu welchem Genre gehört der Film?',
     '[["Western",         ["Zwölf Uhr mittags", "Spiel mir das Lied vom Tod"]],
       ["Science-Fiction", ["Blade Runner", "Matrix"]],
       ["Horror",          ["Der Exorzist", "Shining"]]]'::jsonb,
     array['Casablanca', 'Ziemlich beste Freunde']),

    -- === Essen & Trinken ===================================================
    ('essen-trinken', 'gerichte-laender', 'Gerichte & Länder',
     'Aus welchem Land stammt das Gericht?',
     '[["Italien", ["Pizza Margherita", "Risotto"]],
       ["Japan",   ["Sushi", "Ramen"]],
       ["Mexiko",  ["Tacos"]],
       ["Spanien", ["Paella"]]]'::jsonb,
     array['Wiener Schnitzel', 'Gulasch']),

    ('essen-trinken', 'zutaten-gerichte', 'Zutaten & Gerichte',
     'In welchem Gericht steckt die Zutat?',
     '[["Guacamole",           ["Avocado", "Limette"]],
       ["Pesto alla genovese", ["Basilikum", "Pinienkerne"]],
       ["Hummus",              ["Kichererbsen", "Tahini"]]]'::jsonb,
     array['Sojasauce', 'Safran']),

    ('essen-trinken', 'getraenke-herkunft', 'Getränke & Herkunft',
     'Woher stammt das Getränk?',
     '[["Schottland", ["Scotch Whisky"]],
       ["Mexiko",     ["Tequila", "Mezcal"]],
       ["Japan",      ["Sake"]],
       ["Frankreich", ["Champagner", "Cognac"]]]'::jsonb,
     array['Wodka', 'Rum'])
),

new_quizzes as (
    insert into quizzes (subject_id, slug, title, description)
    select s.id, sp.slug, sp.title, sp.description
      from spec sp
      join subjects s on s.slug = sp.subject_slug
    returning id, slug
),

new_categories as (
    insert into categories (quiz_id, label, position)
    select q.id, g.value ->> 0, g.ord::int
      from spec sp
      join new_quizzes q on q.slug = sp.slug
     cross join lateral jsonb_array_elements(sp.groups) with ordinality g(value, ord)
    returning id, quiz_id, label
),

-- Positions only need to sort stably, so group/item ordinals are combined
-- rather than renumbered, and fakes are pushed to the end.
real_items as (
    select q.id                        as quiz_id,
           g.value ->> 0               as category_label,
           it.value                    as label,
           (g.ord * 100 + it.ord)::int as position
      from spec sp
      join new_quizzes q on q.slug = sp.slug
     cross join lateral jsonb_array_elements(sp.groups) with ordinality g(value, ord)
     cross join lateral jsonb_array_elements_text(g.value -> 1) with ordinality it(value, ord)
),

fake_items as (
    select q.id as quiz_id, f.value as label, (9000 + f.ord)::int as position
      from spec sp
      join new_quizzes q on q.slug = sp.slug
     cross join lateral unnest(sp.fakes) with ordinality f(value, ord)
)

insert into items (quiz_id, category_id, label, position)
select r.quiz_id, c.id, r.label, r.position
  from real_items r
  join new_categories c
    on c.quiz_id = r.quiz_id
   and c.label = r.category_label
union all
-- category_id NULL is what makes an item a fake.
select f.quiz_id, null, f.label, f.position
  from fake_items f;
