-- Hand-curated questions, batch 01 -- one to two per subject.
--
-- Same shape as supabase/seed.sql: one row of `spec` per question, everything
-- else derived from it. Two differences.
--
-- **It is re-runnable.** A question whose slug already exists is skipped rather
-- than failing the whole file, so applying a batch twice adds nothing. That
-- matters because these files are applied by hand with psql, not by the seed
-- runner, and `db reset` does not replay them.
--
-- **They are marked `origin = 'seed'`.** Not because a person typed every pair,
-- but because they are not from `tools/ingest/` -- so the runbook's
-- `delete from quizzes where origin = 'ingest'` must not take them with it.
--
-- Every board is a strict one-to-one pairing of 10 to 12 pairs, the range
-- `tools/ingest/domain/rules.py` bounds and the lobby deals a random 10 from.
-- The rule to hold when editing: **an answer must fit exactly one category on
-- its own board.** Adding "Mozzarella -> Italien" to a board that already has
-- "Gorgonzola -> Italien" makes both unanswerable.
--
-- Apply with:
--   docker exec -i supabase_db_Quiz_Quiz psql -U postgres -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/questions/batch-01.sql

with spec (subject_slug, slug, title, description, difficulty,
           source_title, source_url, pairs, fakes) as (
    values

    -- === Geografie =========================================================
    ('geografie', 'hauptstaedte-asiens', 'Hauptstädte Asiens',
     'Welche Stadt ist die Hauptstadt des Landes?',
     'easy', 'Hauptstadt', 'https://de.wikipedia.org/wiki/Hauptstadt',
     '[["Japan", "Tokio", "Sitz des Kaisers seit 1868, davor hieß die Stadt Edo."],
       ["China", "Peking", "Der Name bedeutet nördliche Hauptstadt."],
       ["Indien", "Neu-Delhi", "Ab 1911 als Regierungssitz gebaut, 1931 eingeweiht."],
       ["Thailand", "Bangkok", "Hauptstadt seit 1782 unter König Rama I."],
       ["Vietnam", "Hanoi", "Seit der Wiedervereinigung 1976 Hauptstadt des ganzen Landes."],
       ["Südkorea", "Seoul", "Hauptstadt seit 1394, damals unter dem Namen Hanseong."],
       ["Indonesien", "Jakarta", "Liegt auf Java; ein Neubau auf Borneo soll sie ablösen."],
       ["Iran", "Teheran", "Hauptstadt seit 1786 unter den Kadscharen."],
       ["Pakistan", "Islamabad", "In den 1960er Jahren gebaut und löste Karatschi ab."],
       ["Philippinen", "Manila", "Liegt an der Manilabucht auf der Insel Luzon."],
       ["Malaysia", "Kuala Lumpur", "Der Name bedeutet schlammige Flussmündung."],
       ["Mongolei", "Ulaanbaatar", "Der Name bedeutet roter Held, vergeben 1924."]]'::jsonb,
     '[["Kathmandu", "Die Hauptstadt Nepals, und das Land steht nicht auf dem Brett."],
       ["Mumbai", "Die größte Stadt Indiens, dessen Hauptstadt aber Neu-Delhi ist."]]'::jsonb),

    ('geografie', 'gebirge-hoechste-gipfel', 'Gebirge & höchste Gipfel',
     'Welcher Gipfel ist der höchste des Gebirges?',
     'hard', 'Gebirge', 'https://de.wikipedia.org/wiki/Gebirge',
     '[["Himalaya", "Mount Everest", "8849 Meter, höchster Berg der Erde."],
       ["Alpen", "Mont Blanc", "4808 Meter, an der Grenze zwischen Frankreich und Italien."],
       ["Anden", "Aconcagua", "6961 Meter, höchster Berg außerhalb Asiens."],
       ["Kaukasus", "Elbrus", "5642 Meter, ein erloschener Vulkan in Russland."],
       ["Pyrenäen", "Pico de Aneto", "3404 Meter, in den spanischen Zentralpyrenäen."],
       ["Karpaten", "Gerlsdorfer Spitze", "2655 Meter in der slowakischen Hohen Tatra."],
       ["Rocky Mountains", "Mount Elbert", "4401 Meter in Colorado."],
       ["Atlas", "Toubkal", "4167 Meter im marokkanischen Hohen Atlas."],
       ["Ural", "Narodnaja", "1895 Meter, im nördlichen Teil des Gebirges."],
       ["Apennin", "Corno Grande", "2912 Meter im Gran-Sasso-Massiv."],
       ["Skandinavisches Gebirge", "Galdhøpiggen", "2469 Meter, höchster Berg Nordeuropas."],
       ["Harz", "Brocken", "1141 Meter, höchster Berg Norddeutschlands."]]'::jsonb,
     '[["Kilimandscharo", "Ein freistehender Berg, kein Gipfel eines Gebirges auf diesem Brett."],
       ["Zugspitze", "Der höchste Berg Deutschlands, aber nicht der der Alpen."]]'::jsonb),

    -- === Geschichte ========================================================
    ('geschichte', 'schlachten-jahreszahlen', 'Schlachten & Jahreszahlen',
     'In welchem Jahr wurde die Schlacht geschlagen?',
     'hard', 'Liste von Schlachten',
     'https://de.wikipedia.org/wiki/Liste_von_Schlachten',
     '[["Schlacht bei Hastings", "1066", "Wilhelm der Eroberer schlug König Harold II. und nahm England ein."],
       ["Varusschlacht", "9 n. Chr.", "Arminius vernichtete drei römische Legionen in Germanien."],
       ["Schlacht bei Marathon", "490 v. Chr.", "Athen schlug das Heer des Perserkönigs Dareios I."],
       ["Schlacht bei Actium", "31 v. Chr.", "Octavian besiegte Antonius und Kleopatra zur See."],
       ["Seeschlacht von Lepanto", "1571", "Die Heilige Liga schlug die osmanische Flotte im Golf von Patras."],
       ["Schlacht von Trafalgar", "1805", "Nelson vernichtete die französisch-spanische Flotte und fiel dabei."],
       ["Völkerschlacht bei Leipzig", "1813", "Die Verbündeten zwangen Napoleon zum Rückzug über den Rhein."],
       ["Schlacht bei Waterloo", "1815", "Napoleons letzte Schlacht, kurz nach seiner Rückkehr von Elba."],
       ["Schlacht von Gettysburg", "1863", "Wendepunkt des amerikanischen Bürgerkriegs in Pennsylvania."],
       ["Schlacht bei Königgrätz", "1866", "Preußen entschied den Deutschen Krieg gegen Österreich."],
       ["Schlacht um Verdun", "1916", "Zehn Monate Stellungskrieg um die französische Festungsstadt."],
       ["Schlacht von Stalingrad", "1943", "Die eingeschlossene 6. Armee kapitulierte im Februar."]]'::jsonb,
     '[["1815 im Winter", "Waterloo wurde im Juni geschlagen, nicht im Winter."],
       ["1944", "Die Landung in der Normandie fällt in dieses Jahr, das hier fehlt."]]'::jsonb),

    -- === Naturwissenschaft =================================================
    ('naturwissenschaft', 'groessen-einheiten', 'Größen & Einheiten',
     'Womit wird diese Größe gemessen?',
     'medium', 'Internationales Einheitensystem',
     'https://de.wikipedia.org/wiki/Internationales_Einheitensystem',
     '[["Kraft", "Newton", "Ein Newton beschleunigt ein Kilogramm um einen Meter pro Sekundenquadrat."],
       ["Energie", "Joule", "Ein Joule ist ein Newtonmeter, also Kraft mal Weg."],
       ["Leistung", "Watt", "Ein Watt ist ein Joule pro Sekunde."],
       ["Druck", "Pascal", "Ein Pascal ist ein Newton pro Quadratmeter."],
       ["Frequenz", "Hertz", "Ein Hertz ist eine Schwingung pro Sekunde."],
       ["Elektrische Spannung", "Volt", "Benannt nach Alessandro Volta, dem Erfinder der Batterie."],
       ["Elektrische Stromstärke", "Ampere", "Eine der sieben Basiseinheiten des Einheitensystems."],
       ["Elektrischer Widerstand", "Ohm", "Ein Ohm ist ein Volt pro Ampere."],
       ["Elektrische Ladung", "Coulomb", "Ein Coulomb ist eine Amperesekunde."],
       ["Temperatur", "Kelvin", "Beginnt beim absoluten Nullpunkt und kennt keine Minusgrade."],
       ["Stoffmenge", "Mol", "Enthält rund 6,022 mal 10 hoch 23 Teilchen."],
       ["Lichtstärke", "Candela", "Misst das Licht, das eine Quelle in eine Richtung abgibt."]]'::jsonb,
     '[["Sekunde", "Die Einheit der Zeit, nach der auf diesem Brett niemand fragt."],
       ["Tesla", "Sie misst die magnetische Flussdichte, und die fehlt hier."]]'::jsonb),

    -- === Kunst & Kultur ====================================================
    ('kunst-kultur', 'museen-staedte', 'Museen & Städte',
     'In welcher Stadt steht das Museum?',
     'medium', 'Kunstmuseum', 'https://de.wikipedia.org/wiki/Kunstmuseum',
     '[["Louvre", "Paris", "Der frühere Königspalast wurde 1793 als Museum eröffnet."],
       ["Prado", "Madrid", "Zeigt die königliche Sammlung mit Velázquez und Goya."],
       ["Uffizien", "Florenz", "Erbaut als Amtsräume der Medici, daher der Name."],
       ["Eremitage", "Sankt Petersburg", "Untergebracht im Winterpalast der Zaren."],
       ["Rijksmuseum", "Amsterdam", "Hauptwerk der Sammlung ist Rembrandts Nachtwache."],
       ["Pergamonmuseum", "Berlin", "Steht auf der Museumsinsel und zeigt den Pergamonaltar."],
       ["Metropolitan Museum of Art", "New York", "Größtes Kunstmuseum der USA, an der Fifth Avenue."],
       ["British Museum", "London", "Zeigt den Stein von Rosetta und die Parthenon-Skulpturen."],
       ["Kunsthistorisches Museum", "Wien", "Steht an der Ringstraße, gegenüber dem Naturhistorischen Museum."],
       ["Alte Pinakothek", "München", "Zeigt die Sammlung alter Meister der Wittelsbacher."],
       ["Zwinger", "Dresden", "Barockbau von Pöppelmann mit der Gemäldegalerie Alte Meister."],
       ["Mauritshuis", "Den Haag", "Zeigt Vermeers Mädchen mit dem Perlenohrgehänge."]]'::jsonb,
     '[["Vatikanstadt", "Die Vatikanischen Museen lägen dort, und die fehlen auf dem Brett."],
       ["Brüssel", "Kein Museum in dieser Liste steht dort."]]'::jsonb),

    -- === Sport =============================================================
    ('sport', 'wettbewerbe-sportarten', 'Wettbewerbe & Sportarten',
     'Zu welcher Sportart gehört der Wettbewerb?',
     'medium', 'Wettkampf', 'https://de.wikipedia.org/wiki/Wettkampf',
     '[["Wimbledon", "Tennis", "Das Turnier im All England Club wird auf Rasen gespielt."],
       ["Tour de France", "Radsport", "Dreiwöchige Rundfahrt; das Gelbe Trikot führt die Wertung an."],
       ["Super Bowl", "American Football", "Endspiel der NFL, jedes Jahr im Februar."],
       ["Stanley Cup", "Eishockey", "Trophäe des NHL-Meisters, gestiftet 1892."],
       ["Vierschanzentournee", "Skispringen", "Vier Springen zwischen Weihnachten und Dreikönigstag."],
       ["Ryder Cup", "Golf", "Europa gegen die USA, alle zwei Jahre."],
       ["America''s Cup", "Segeln", "Ältester noch ausgetragener Sportwettbewerb der Welt."],
       ["Kentucky Derby", "Pferderennen", "Galopprennen in Louisville, seit 1875."],
       ["Six Nations", "Rugby", "Turnier der sechs europäischen Nationalmannschaften."],
       ["Hahnenkammrennen", "Ski Alpin", "Abfahrt auf der Streif in Kitzbühel."],
       ["Boston-Marathon", "Leichtathletik", "Ältester jährlich ausgetragener Marathon der Welt."],
       ["24 Stunden von Le Mans", "Motorsport", "Langstreckenrennen an der Sarthe, seit 1923."]]'::jsonb,
     '[["Schwimmen", "Kein Wettbewerb auf diesem Brett gehört dazu."],
       ["Turnen", "Auch dafür steht in dieser Liste kein Wettbewerb."]]'::jsonb),

    -- === Technik ===========================================================
    ('technik', 'unternehmen-gruender', 'Unternehmen & Gründer',
     'Wer hat das Unternehmen gegründet?',
     'medium', 'Unternehmer', 'https://de.wikipedia.org/wiki/Unternehmer',
     '[["Microsoft", "Bill Gates", "1975 zusammen mit Paul Allen gegründet."],
       ["Apple", "Steve Jobs", "1976 mit Steve Wozniak in Kalifornien gegründet."],
       ["Amazon", "Jeff Bezos", "1994 als Online-Buchhandel in Seattle gestartet."],
       ["Facebook", "Mark Zuckerberg", "2004 im Studentenwohnheim in Harvard gestartet."],
       ["Ford", "Henry Ford", "1903 gegründet, ab 1913 mit Fließbandfertigung."],
       ["Siemens", "Werner von Siemens", "1847 als Telegraphenbauanstalt in Berlin gegründet."],
       ["Oracle", "Larry Ellison", "1977 gegründet, groß geworden mit Datenbanken."],
       ["Dell", "Michael Dell", "1984 aus dem Studentenzimmer in Austin heraus gegründet."],
       ["Bosch", "Robert Bosch", "1886 als Werkstätte für Feinmechanik in Stuttgart."],
       ["Nvidia", "Jensen Huang", "1993 gegründet, prägte den Begriff Grafikprozessor."],
       ["SpaceX", "Elon Musk", "2002 gegründet, um Raketen wiederverwendbar zu machen."],
       ["IKEA", "Ingvar Kamprad", "1943 in Schweden gegründet, im Alter von 17 Jahren."]]'::jsonb,
     '[["Larry Page", "Er gründete Google, und das fehlt auf diesem Brett."],
       ["Gottlieb Daimler", "Sein Unternehmen steht nicht in dieser Liste."]]'::jsonb),

    -- === Musik =============================================================
    ('musik', 'opern-komponisten', 'Opern & Komponisten',
     'Wer hat die Oper komponiert?',
     'hard', 'Oper', 'https://de.wikipedia.org/wiki/Oper',
     '[["Die Zauberflöte", "Mozart", "Singspiel von 1791, uraufgeführt in Wien."],
       ["Carmen", "Bizet", "1875 in Paris uraufgeführt, nach der Novelle von Mérimée."],
       ["Aida", "Verdi", "1871 in Kairo uraufgeführt."],
       ["Tosca", "Puccini", "1900 in Rom uraufgeführt, nach dem Drama von Sardou."],
       ["Der Ring des Nibelungen", "Richard Wagner", "Vier Abende, 1876 zur Eröffnung von Bayreuth erstmals ganz gespielt."],
       ["Der Freischütz", "Carl Maria von Weber", "1821 uraufgeführt, die erste deutsche romantische Oper."],
       ["Fidelio", "Beethoven", "Seine einzige Oper, die er dreimal umarbeitete."],
       ["Der Barbier von Sevilla", "Rossini", "1816 in Rom uraufgeführt, nach Beaumarchais."],
       ["Boris Godunow", "Modest Mussorgski", "Nach Puschkins Drama über den russischen Zaren."],
       ["Wozzeck", "Alban Berg", "1925 uraufgeführt, nach dem Dramenfragment von Büchner."],
       ["Peter Grimes", "Benjamin Britten", "1945 in London uraufgeführt, über einen Fischer in Suffolk."],
       ["Orpheus und Eurydike", "Christoph Willibald Gluck", "1762 uraufgeführt, der Beginn seiner Opernreform."]]'::jsonb,
     '[["Johann Strauss", "Die Fledermaus wäre das Werk dazu, und die fehlt hier."],
       ["Richard Strauss", "Der Rosenkavalier steht nicht auf diesem Brett."]]'::jsonb),

    -- === Film & Fernsehen ==================================================
    ('film-fernsehen', 'verfilmungen-autoren', 'Verfilmungen & Autoren',
     'Wer schrieb die Romanvorlage zum Film?',
     'medium', 'Literaturverfilmung',
     'https://de.wikipedia.org/wiki/Literaturverfilmung',
     '[["Der Herr der Ringe", "J. R. R. Tolkien", "Die Romanvorlage erschien 1954 und 1955 in drei Bänden."],
       ["Shining", "Stephen King", "Roman von 1977; Kubrick verfilmte ihn 1980."],
       ["Der Pate", "Mario Puzo", "Roman von 1969; er schrieb am Drehbuch mit."],
       ["Jurassic Park", "Michael Crichton", "Roman von 1990 über geklonte Dinosaurier."],
       ["Blade Runner", "Philip K. Dick", "Nach dem Roman Träumen Androiden von elektrischen Schafen?"],
       ["Der Name der Rose", "Umberto Eco", "Klosterkrimi von 1980, verfilmt mit Sean Connery."],
       ["Fight Club", "Chuck Palahniuk", "Roman von 1996, verfilmt von David Fincher."],
       ["Das Schweigen der Lämmer", "Thomas Harris", "Zweiter Roman um Hannibal Lecter, erschienen 1988."],
       ["Der Marsianer", "Andy Weir", "Zuerst im Selbstverlag erschienen, verfilmt von Ridley Scott."],
       ["Verblendung", "Stieg Larsson", "Erster Band der Millennium-Trilogie, posthum erschienen."],
       ["Schindlers Liste", "Thomas Keneally", "Nach dem Roman Schindlers Ark von 1982."],
       ["Die unendliche Geschichte", "Michael Ende", "Kinderbuch von 1979; der Autor klagte gegen die Verfilmung."]]'::jsonb,
     '[["George R. R. Martin", "Game of Thrones wäre die Vorlage, und die fehlt auf dem Brett."],
       ["Joanne K. Rowling", "Harry Potter steht nicht in dieser Liste."]]'::jsonb),

    -- === Essen & Trinken ===================================================
    ('essen-trinken', 'kaesesorten-herkunft', 'Käsesorten & Herkunft',
     'Aus welchem Land stammt der Käse?',
     'medium', 'Käse', 'https://de.wikipedia.org/wiki/K%C3%A4se',
     '[["Gorgonzola", "Italien", "Blauschimmelkäse aus der Lombardei, benannt nach einem Ort bei Mailand."],
       ["Roquefort", "Frankreich", "Schafskäse aus Roquefort-sur-Soulzon, in Kalkhöhlen gereift."],
       ["Manchego", "Spanien", "Schafskäse aus der Hochebene von La Mancha."],
       ["Feta", "Griechenland", "Salzlakenkäse aus Schafmilch, seit 2002 geschützte Herkunft."],
       ["Gouda", "Niederlande", "Benannt nach der Stadt, auf deren Markt er gehandelt wurde."],
       ["Cheddar", "England", "Benannt nach dem Dorf Cheddar in Somerset."],
       ["Emmentaler", "Schweiz", "Hartkäse aus dem Emmental, bekannt für seine großen Löcher."],
       ["Halloumi", "Zypern", "Aus Ziegen- und Schafmilch, bleibt beim Braten in Form."],
       ["Danablu", "Dänemark", "Blauschimmelkäse aus Kuhmilch, in den 1920er Jahren entwickelt."],
       ["Oscypek", "Polen", "Geräucherter Schafskäse aus der Tatra."],
       ["Tiroler Bergkäse", "Österreich", "Rohmilchkäse mit geschützter Ursprungsbezeichnung."],
       ["Harzer", "Deutschland", "Sauermilchkäse aus dem Harz, fast ohne Fett."]]'::jsonb,
     '[["Norwegen", "Der Jarlsberg käme von dort, und der fehlt auf diesem Brett."],
       ["Portugal", "Der Queijo da Serra steht nicht in dieser Liste."]]'::jsonb)
),

-- A slug that is already in the database is skipped rather than colliding, so
-- the file can be applied again after being extended.
new_quizzes as (
    insert into quizzes (subject_id, slug, title, description,
                         difficulty, source_title, source_url, origin)
    select s.id, sp.slug, sp.title, sp.description,
           sp.difficulty::difficulty, sp.source_title, sp.source_url, 'seed'
      from spec sp
      join subjects s on s.slug = sp.subject_slug
     where not exists (select 1 from quizzes q where q.slug = sp.slug)
    returning id, slug
),

-- One row per pair, carrying all three parts. The ordinal is the position for
-- the category and its answer alike, which is what keeps the two aligned.
-- Joining on `new_quizzes` rather than on `quizzes` is what confines the
-- categories and items to the questions this run actually inserted.
flat as (
    select q.id          as quiz_id,
           p.value ->> 0 as label,
           p.value ->> 1 as answer,
           p.value ->> 2 as explanation,
           p.ord::int    as position
      from spec sp
      join new_quizzes q on q.slug = sp.slug
     cross join lateral jsonb_array_elements(sp.pairs) with ordinality p(value, ord)
),

-- The answers that belong to no category. Numbered after the pairs so the two
-- sets never collide on `position`, though nothing reads it for a fake: the
-- pool is shuffled before a player sees it, and the review lists fakes on their
-- own rather than in board order.
fakes as (
    select q.id                                         as quiz_id,
           k.value ->> 0                                as label,
           k.value ->> 1                                as explanation,
           (jsonb_array_length(sp.pairs) + k.ord)::int  as position
      from spec sp
      join new_quizzes q on q.slug = sp.slug
     cross join lateral jsonb_array_elements(sp.fakes) with ordinality k(value, ord)
),

new_categories as (
    insert into categories (quiz_id, label, position)
    select quiz_id, label, position from flat
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select f.quiz_id, c.id, f.answer, f.position, f.explanation
      from flat f
      join new_categories c
        on c.quiz_id = f.quiz_id
       and c.label = f.label
    returning id
)

-- Same table, `category_id` left null. Both inserts run in the one statement,
-- so `items_quiz_id_label_key` still sees the pairs above: a fake written to
-- repeat an answer already on its own board fails the file rather than becoming
-- a second row nobody can tell apart.
insert into items (quiz_id, category_id, label, position, explanation)
select k.quiz_id, null, k.label, k.position, k.explanation
  from fakes k;
