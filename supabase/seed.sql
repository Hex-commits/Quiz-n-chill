-- Development seed data, reloaded by `supabase db reset`.
--
-- Content is German; identifiers stay English.
--
-- **Every question is a one-to-one pairing, plus two fakes.** One category,
-- one answer, and no category holds two -- `unique (quiz_id, category_id)`
-- enforces that. What it does not enforce is that every answer has a category:
-- the two fakes per board belong to none, and spotting them is part of the
-- game. See supabase/migrations/20260818120000_fake_answers.sql.
--
-- Each question is one row of the `spec` table below:
--
--   subject, slug, title, description,
--   difficulty, source_title, source_url,
--   '[["Kategorie", "Antwort", "Begründung"], ...]',
--   '[["Falsche Antwort", "Warum sie nirgends passt"], ...]'
--
-- The third element is shown to the player *after* the round, underneath the
-- answer it belongs to, so a lost round still teaches something. It gives the
-- answer away, so it is served only on the solution paths -- never in what a
-- player sees while the question is live.
--
-- Keep it to one short sentence that names the deciding fact. Not "richtig,
-- weil ..." and not the rule of the game: the fact itself.
--
-- Every source_url here was read back from the Wikipedia API rather than
-- assembled by hand, so each one resolves.
--
-- Every question here is also marked `origin = 'seed'`. That is what separates
-- this pool from what `tools/ingest/` generates: both kinds carry a Wikipedia
-- source_url and fill the same columns, so without the marker a row gives no
-- clue whether a person wrote it or a model did.
--
-- The one thing to watch when editing: **an answer must fit only one category
-- on its own board.** "Wasser" under "Anorganische Stoffe" is fine until
-- "Reduktionsmittel" is also on the board -- then the player who picks the
-- other one is marked wrong for being right. Every pairing below is chosen so
-- that exactly one category can take it.
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
    ('essen-trinken',     'Essen & Trinken',   'Gerichte, Zutaten und Getränke.',                9),
    ('videospiele',       'Videospiele',       'Konsolen, Spielereihen und Studios.',           10);


with spec (subject_slug, slug, title, description, difficulty,
           source_title, source_url, pairs, fakes) as (
    values

    -- === Geografie =========================================================
    ('geografie', 'hauptstaedte-europas', 'Hauptstädte Europas',
     'Welche Stadt ist die Hauptstadt des Landes?',
     'easy', 'Hauptstadt', 'https://de.wikipedia.org/wiki/Hauptstadt',
     '[["Deutschland", "Berlin", "Hauptstadt seit 1990, Regierungssitz seit 1999."],
       ["Frankreich", "Paris", "Hauptstadt seit dem 10. Jahrhundert."],
       ["Italien", "Rom", "Hauptstadt seit 1871, davor Turin und Florenz."],
       ["Spanien", "Madrid", "Hauptstadt seit 1561 unter Philipp II."],
       ["Portugal", "Lissabon", "Hauptstadt seit 1255, davor Coimbra."],
       ["Österreich", "Wien", "Hauptstadt und zugleich eigenes Bundesland."],
       ["Polen", "Warschau", "Hauptstadt seit 1596, davor Krakau."],
       ["Griechenland", "Athen", "Hauptstadt seit 1834, kurz nach der Unabhängigkeit."]]'::jsonb,
     '[["Amsterdam", "Die Hauptstadt der Niederlande, und das Land fehlt auf dem Brett."],
       ["Zürich", "Die größte Stadt der Schweiz, aber nicht deren Hauptstadt."]]'::jsonb),

    ('geografie', 'fluesse-hauptstaedte', 'Flüsse & Hauptstädte',
     'An welchem Fluss liegt die Stadt?',
     'medium', 'Liste von Flüssen in Europa',
     'https://de.wikipedia.org/wiki/Liste_von_Fl%C3%BCssen_in_Europa',
     '[["Seine", "Paris", "Die Stadt entstand auf der Seine-Insel Île de la Cité."],
       ["Themse", "London", "Der Hafen an der Themse begründete den Aufstieg der Stadt."],
       ["Donau", "Wien", "Die Donau fließt im Nordosten an der Stadt vorbei."],
       ["Tiber", "Rom", "Die Stadt wuchs auf den Hügeln über dem Tiber."],
       ["Spree", "Berlin", "Die Spree durchfließt die Stadt und mündet dort in die Havel."],
       ["Moldau", "Prag", "Die Moldau teilt die Stadt, überspannt von der Karlsbrücke."],
       ["Weichsel", "Warschau", "Die Weichsel trennt die Innenstadt vom Stadtteil Praga."]]'::jsonb,
     '[["Hamburg", "Es liegt an der Elbe, und die fehlt auf diesem Brett."],
       ["Lissabon", "Es liegt am Tejo, der hier nicht steht."]]'::jsonb),

    ('geografie', 'laender-waehrungen', 'Länder & Währungen',
     'Welche Währung gehört zu welchem Land?',
     'medium', 'ISO 4217', 'https://de.wikipedia.org/wiki/ISO_4217',
     '[["Japan", "Yen", "Währung seit der Meiji-Reform 1871."],
       ["Schweiz", "Franken", "Währung seit 1850, Code CHF."],
       ["Polen", "Złoty", "Der Name bedeutet golden."],
       ["Indien", "Rupie", "Vom Sanskrit-Wort rupya für Silber."],
       ["Russland", "Rubel", "Eine der ältesten noch genutzten Währungen Europas."],
       ["Dänemark", "Dänische Krone", "Das Land behielt sie und trat dem Euro nicht bei."],
       ["Vereinigtes Königreich", "Pfund Sterling", "Älteste durchgehend genutzte Währung der Welt."],
       ["Südafrika", "Rand", "Benannt nach dem Goldgebiet Witwatersrand."]]'::jsonb,
     '[["Forint", "Damit zahlt man in Ungarn, das auf diesem Brett fehlt."],
       ["Real", "Die Währung Brasiliens, und das steht nicht in dieser Liste."]]'::jsonb),

    -- === Geschichte ========================================================
    ('geschichte', 'beruehmte-herrscher', 'Berühmte Herrscher',
     'Über welches Reich herrschte diese Person?',
     'medium', 'Herrscher', 'https://de.wikipedia.org/wiki/Herrscher',
     '[["Frankreich", "Ludwig XIV.", "Der Sonnenkönig regierte 72 Jahre von Versailles aus."],
       ["Russland", "Katharina die Große", "Zarin von 1762 bis 1796, gebürtige Deutsche."],
       ["Ägypten", "Kleopatra", "Letzte Herrscherin der Ptolemäer-Dynastie."],
       ["Makedonien", "Alexander der Große", "Zog bis nach Indien und gründete Alexandria."],
       ["Mongolei", "Dschingis Khan", "Einte die Stämme und gründete das Mongolenreich."],
       ["England", "Elisabeth I.", "Regierte 1558 bis 1603, das elisabethanische Zeitalter."],
       ["Preußen", "Friedrich der Große", "König von 1740 bis 1786, genannt der Alte Fritz."]]'::jsonb,
     '[["Sultan Süleyman", "Er herrschte über das Osmanische Reich, das hier fehlt."],
       ["Qin Shihuangdi", "Der erste Kaiser Chinas, und China steht nicht auf dem Brett."]]'::jsonb),

    ('geschichte', 'ereignisse-jahrhunderte', 'Ereignisse & Jahrhunderte',
     'In welches Jahrhundert gehört das Ereignis?',
     'hard', 'Zeitleiste', 'https://de.wikipedia.org/wiki/Zeitleiste',
     '[["15. Jahrhundert", "Entdeckung Amerikas", "Kolumbus erreichte 1492 die Bahamas."],
       ["16. Jahrhundert", "Reformation", "Luthers Thesen von 1517 spalteten die Kirche."],
       ["17. Jahrhundert", "Dreißigjähriger Krieg", "1618 bis 1648, beendet im Westfälischen Frieden."],
       ["18. Jahrhundert", "Französische Revolution", "Der Sturm auf die Bastille war 1789."],
       ["19. Jahrhundert", "Deutsche Reichsgründung", "Kaiserproklamation in Versailles 1871."],
       ["20. Jahrhundert", "Mondlandung", "Apollo 11 landete 1969 auf dem Mond."],
       ["21. Jahrhundert", "Euro-Bargeld", "Scheine und Münzen kamen 2002 in Umlauf."]]'::jsonb,
     '[["Krönung Karls des Großen", "Sie fällt ins 9. Jahrhundert, das hier fehlt."],
       ["Untergang des Weströmischen Reiches", "Das 5. Jahrhundert steht nicht auf diesem Brett."]]'::jsonb),

    ('geschichte', 'historische-bauwerke', 'Historische Bauwerke',
     'In welchem Land steht das Bauwerk?',
     'easy', 'Weltwunder', 'https://de.wikipedia.org/wiki/Weltwunder',
     '[["Ägypten", "Pyramiden von Gizeh", "Einziges erhaltenes der sieben antiken Weltwunder."],
       ["China", "Chinesische Mauer", "Über Jahrhunderte gebauter Grenzwall im Norden."],
       ["Italien", "Kolosseum", "Amphitheater in Rom, um 80 n. Chr. eingeweiht."],
       ["Indien", "Taj Mahal", "Grabmal in Agra, erbaut für die Frau von Shah Jahan."],
       ["Peru", "Machu Picchu", "Inkastadt in den Anden, 1911 weltweit bekannt gemacht."],
       ["Jordanien", "Petra", "Nabatäerstadt, in roten Sandstein geschlagen."],
       ["Griechenland", "Akropolis", "Tempelberg über Athen mit dem Parthenon."]]'::jsonb,
     '[["Stonehenge", "Es steht in England, und das fehlt auf diesem Brett."],
       ["Angkor Wat", "Es steht in Kambodscha, das hier nicht vorkommt."]]'::jsonb),

    -- === Naturwissenschaft =================================================
    ('naturwissenschaft', 'chemische-elemente', 'Chemische Elemente',
     'Welches Symbol steht für das Element?',
     'medium', 'Chemisches Element', 'https://de.wikipedia.org/wiki/Chemisches_Element',
     '[["Sauerstoff", "O", "Vom lateinischen oxygenium."],
       ["Wasserstoff", "H", "Vom lateinischen hydrogenium."],
       ["Eisen", "Fe", "Vom lateinischen ferrum."],
       ["Gold", "Au", "Vom lateinischen aurum."],
       ["Silber", "Ag", "Vom lateinischen argentum."],
       ["Kupfer", "Cu", "Vom lateinischen cuprum, nach der Insel Zypern."],
       ["Natrium", "Na", "Vom lateinischen natrium, englisch sodium."],
       ["Kalium", "K", "Vom lateinischen kalium, englisch potassium."]]'::jsonb,
     '[["N", "Das Symbol für Stickstoff, und das Element fehlt auf dem Brett."],
       ["Pb", "Blei trägt es, und das steht nicht in dieser Liste."]]'::jsonb),

    ('naturwissenschaft', 'planeten-monde', 'Planeten & Monde',
     'Welchen Planeten umkreist der Mond?',
     'hard', 'Sonnensystem', 'https://de.wikipedia.org/wiki/Sonnensystem',
     '[["Erde", "Mond", "Der einzige natürliche Satellit der Erde."],
       ["Mars", "Phobos", "Der innere der beiden Marsmonde."],
       ["Jupiter", "Ganymed", "Größter Mond des Sonnensystems, größer als Merkur."],
       ["Saturn", "Titan", "Einziger Mond mit dichter Atmosphäre."],
       ["Neptun", "Triton", "Läuft rückläufig um, vermutlich eingefangen."],
       ["Uranus", "Titania", "Größter Uranusmond, benannt nach Shakespeare."]]'::jsonb,
     '[["Charon", "Der Begleiter Plutos, und Pluto fehlt auf diesem Brett."],
       ["Ceres", "Ein Zwergplanet im Asteroidengürtel, gar kein Mond."]]'::jsonb),

    ('naturwissenschaft', 'organe-systeme', 'Organe & Organsysteme',
     'Zu welchem Organsystem gehört das Organ?',
     'medium', 'Organsystem', 'https://de.wikipedia.org/wiki/Organsystem',
     '[["Herz", "Kreislaufsystem", "Pumpt das Blut durch den ganzen Körper."],
       ["Lunge", "Atmungssystem", "Nimmt Sauerstoff auf und gibt Kohlendioxid ab."],
       ["Magen", "Verdauungssystem", "Zersetzt die Nahrung mit Magensäure."],
       ["Niere", "Harnsystem", "Filtert das Blut und bildet den Harn."],
       ["Gehirn", "Nervensystem", "Steuerzentrale aller Nervenbahnen."],
       ["Schilddrüse", "Hormonsystem", "Bildet die Hormone Thyroxin und Trijodthyronin."],
       ["Milz", "Immunsystem", "Filtert Krankheitserreger aus dem Blut."]]'::jsonb,
     '[["Skelettsystem", "Kein Organ auf diesem Brett gehört dazu."],
       ["Muskelsystem", "Auch dafür steht in dieser Liste kein Organ."]]'::jsonb),

    -- === Kunst & Kultur ====================================================
    ('kunst-kultur', 'gemaelde-maler', 'Gemälde & Maler',
     'Wer hat das Gemälde gemalt?',
     'medium', 'Liste von Malern', 'https://de.wikipedia.org/wiki/Liste_von_Malern',
     '[["Mona Lisa", "Leonardo da Vinci", "Um 1503 entstanden, heute im Louvre."],
       ["Sternennacht", "Vincent van Gogh", "1889 in der Heilanstalt Saint-Rémy gemalt."],
       ["Guernica", "Pablo Picasso", "1937 gegen die Bombardierung der Stadt gemalt."],
       ["Der Schrei", "Edvard Munch", "1893, Sinnbild existenzieller Angst."],
       ["Die Geburt der Venus", "Sandro Botticelli", "Um 1485, Hauptwerk der Florentiner Renaissance."],
       ["Der Kuss", "Gustav Klimt", "1908, Höhepunkt seiner Goldenen Periode."],
       ["Das Nebelmeer", "Caspar David Friedrich", "Um 1818, Ikone der deutschen Romantik."]]'::jsonb,
     '[["Rembrandt", "Die Nachtwache wäre das Bild dazu, und die fehlt hier."],
       ["Salvador Dalí", "Seine zerfließenden Uhren stehen nicht auf diesem Brett."]]'::jsonb),

    ('kunst-kultur', 'werke-autoren', 'Werke & Autoren',
     'Wer hat das Werk geschrieben?',
     'medium', 'Weltliteratur', 'https://de.wikipedia.org/wiki/Weltliteratur',
     '[["Faust", "Goethe", "Tragödie in zwei Teilen, vollendet 1831."],
       ["Hamlet", "Shakespeare", "Um 1600 entstandene Rachetragödie."],
       ["Don Quijote", "Cervantes", "1605 erschienen, gilt als erster moderner Roman."],
       ["Krieg und Frieden", "Tolstoi", "Russland zur Zeit der Napoleonischen Kriege."],
       ["Die Verwandlung", "Kafka", "1915, Gregor Samsa erwacht als Ungeziefer."],
       ["Madame Bovary", "Flaubert", "1857, Skandalroman um Emma Bovary."],
       ["Die Göttliche Komödie", "Dante", "Reise durch Hölle, Läuterungsberg und Paradies."]]'::jsonb,
     '[["Dostojewski", "Schuld und Sühne wäre das Werk dazu, und das fehlt hier."],
       ["Homer", "Die Ilias steht nicht auf diesem Brett."]]'::jsonb),

    ('kunst-kultur', 'bauwerke-baustile', 'Bauwerke & Baustile',
     'In welchem Baustil wurde das Bauwerk errichtet?',
     'hard', 'Baustil', 'https://de.wikipedia.org/wiki/Baustil',
     '[["Kölner Dom", "Gotik", "Spitzbögen und Strebewerk, begonnen 1248."],
       ["Schloss Versailles", "Barock", "Prunk und strenge Symmetrie unter Ludwig XIV."],
       ["Bauhaus Dessau", "Moderne", "Gropius-Bau von 1926, Form folgt Funktion."],
       ["Kolosseum", "Römische Antike", "Rundbögen und Travertin, um 80 n. Chr."],
       ["Hagia Sophia", "Byzantinisch", "Riesenkuppel über Pendentifs, 537 geweiht."],
       ["Alhambra", "Maurisch", "Stuckornamente und Muqarnas in Granada."],
       ["Petersdom", "Renaissance", "Kuppel nach dem Entwurf Michelangelos."]]'::jsonb,
     '[["Rokoko", "Die Wieskirche stünde dafür, und die fehlt auf diesem Brett."],
       ["Art déco", "Kein Bauwerk in dieser Liste ist so gebaut."]]'::jsonb),

    -- === Sport =============================================================
    ('sport', 'sportarten-geraete', 'Sportarten & Geräte',
     'Welches Gerät gehört zur Sportart?',
     'easy', 'Sportart', 'https://de.wikipedia.org/wiki/Sportart',
     '[["Eishockey", "Puck", "Hartgummischeibe, vor dem Spiel gekühlt."],
       ["Golf", "Golfschläger", "Ein Satz umfasst höchstens vierzehn Stück."],
       ["Fechten", "Florett", "Stoßwaffe, Treffer zählen nur am Rumpf."],
       ["Curling", "Curlingstein", "Granitstein von rund zwanzig Kilogramm."],
       ["Bogenschießen", "Pfeil", "Wird mit dem Bogen auf die Scheibe geschossen."],
       ["Billard", "Queue", "Stock zum Stoßen der Kugeln."],
       ["Tischtennis", "Zelluloidball", "Hohlball, heute meist aus Kunststoff."]]'::jsonb,
     '[["Federball", "Er gehört zum Badminton, und das fehlt auf diesem Brett."],
       ["Boxhandschuh", "Boxen steht nicht in dieser Liste."]]'::jsonb),

    ('sport', 'vereine-laender', 'Vereine & Länder',
     'In welchem Land spielt der Verein?',
     'easy', 'Fußballverein', 'https://de.wikipedia.org/wiki/Fu%C3%9Fballverein',
     '[["FC Bayern München", "Deutschland", "Rekordmeister der Bundesliga."],
       ["Real Madrid", "Spanien", "Spielt in der spanischen La Liga."],
       ["Juventus Turin", "Italien", "Rekordmeister der italienischen Serie A."],
       ["Manchester United", "England", "Spielt in der englischen Premier League."],
       ["Ajax Amsterdam", "Niederlande", "Rekordmeister der niederländischen Eredivisie."],
       ["Benfica Lissabon", "Portugal", "Rekordmeister der portugiesischen Primeira Liga."],
       ["Paris Saint-Germain", "Frankreich", "Spielt in der französischen Ligue 1."]]'::jsonb,
     '[["Schottland", "Celtic Glasgow spielte dort, und der Verein fehlt hier."],
       ["Griechenland", "Kein Verein auf diesem Brett spielt dort."]]'::jsonb),

    ('sport', 'olympische-disziplinen', 'Olympische Disziplinen',
     'Zu welcher Sportart gehört die Disziplin?',
     'medium', 'Olympische Sportarten',
     'https://de.wikipedia.org/wiki/Olympische_Sportarten',
     '[["Leichtathletik", "Stabhochsprung", "Sprung über die Latte mit Hilfe eines Stabs."],
       ["Schwimmen", "Delfinschwimmen", "Schmetterlingsstil mit gleichzeitigem Armzug."],
       ["Turnen", "Reck", "Gerätturnen an der horizontalen Stange."],
       ["Reiten", "Dressur", "Bewertet wird die Lektionsfolge von Pferd und Reiter."],
       ["Fechten", "Degen", "Fechtwaffe, bei der der ganze Körper Trefferfläche ist."],
       ["Kanu", "Slalom", "Fahrt durch hängende Tore im Wildwasser."],
       ["Radsport", "Bahnradfahren", "Rennen auf der ovalen, überhöhten Radrennbahn."]]'::jsonb,
     '[["Freistilringen", "Ringen steht nicht auf diesem Brett."],
       ["Kunstspringen vom Brett", "Das Wasserspringen fehlt in dieser Liste."]]'::jsonb),

    -- === Technik ===========================================================
    ('technik', 'erfindungen', 'Erfindungen & Erfinder',
     'Was hat diese Person erfunden?',
     'medium', 'Erfindung', 'https://de.wikipedia.org/wiki/Erfindung',
     '[["Johannes Gutenberg", "Buchdruck", "Bewegliche Metalllettern, um 1450 in Mainz."],
       ["Karl Benz", "Automobil", "Der Patent-Motorwagen von 1886."],
       ["Alexander Fleming", "Penicillin", "1928 zufällig an einer Schimmelkultur entdeckt."],
       ["Wilhelm Conrad Röntgen", "Röntgenstrahlen", "1895 entdeckt, erster Nobelpreis für Physik."],
       ["Alexander Graham Bell", "Telefon", "Erhielt 1876 das US-Patent."],
       ["Thomas Edison", "Glühlampe", "Machte die Kohlefadenlampe 1879 marktreif."],
       ["Alfred Nobel", "Dynamit", "1867 patentiert, Grundlage der Nobelpreise."]]'::jsonb,
     '[["Dampfmaschine", "Sie geht auf James Watt zurück, und der fehlt auf dem Brett."],
       ["Funktelegrafie", "Guglielmo Marconi steht nicht in dieser Liste."]]'::jsonb),

    ('technik', 'programmiersprachen', 'Programmiersprachen',
     'Wer hat die Sprache entworfen?',
     'hard', 'Programmiersprache', 'https://de.wikipedia.org/wiki/Programmiersprache',
     '[["Python", "Guido van Rossum", "1991 veröffentlicht, benannt nach Monty Python."],
       ["C", "Dennis Ritchie", "Anfang der 1970er in den Bell Labs entwickelt."],
       ["Java", "James Gosling", "1995 bei Sun Microsystems veröffentlicht."],
       ["JavaScript", "Brendan Eich", "1995 bei Netscape in zehn Tagen entworfen."],
       ["Ruby", "Yukihiro Matsumoto", "1995 in Japan veröffentlicht."],
       ["PHP", "Rasmus Lerdorf", "1995 aus eigenen Webseiten-Skripten entstanden."],
       ["Pascal", "Niklaus Wirth", "1970 als Lehrsprache entworfen."]]'::jsonb,
     '[["Bjarne Stroustrup", "Er entwarf C++, und das fehlt auf diesem Brett."],
       ["Grace Hopper", "Sie steht für COBOL, das hier nicht vorkommt."]]'::jsonb),

    ('technik', 'automarken-laender', 'Automarken & Länder',
     'Aus welchem Land stammt die Marke?',
     'easy', 'Liste von Pkw-Marken', 'https://de.wikipedia.org/wiki/Liste_von_Pkw-Marken',
     '[["Volkswagen", "Deutschland", "Stammsitz ist Wolfsburg."],
       ["Renault", "Frankreich", "1899 in Boulogne-Billancourt gegründet."],
       ["Fiat", "Italien", "Steht für Fabbrica Italiana Automobili Torino."],
       ["Toyota", "Japan", "Sitz in der Stadt Toyota, Präfektur Aichi."],
       ["Volvo", "Schweden", "1927 in Göteborg gegründet."],
       ["Hyundai", "Südkorea", "Konzernsitz in Seoul."],
       ["Škoda", "Tschechien", "1895 in Mladá Boleslav gegründet."]]'::jsonb,
     '[["Vereinigtes Königreich", "Jaguar käme von dort, und die Marke fehlt hier."],
       ["USA", "Ford steht nicht auf diesem Brett."]]'::jsonb),

    -- === Musik =============================================================
    ('musik', 'instrumente-familien', 'Instrumente & Familien',
     'Zu welcher Instrumentenfamilie gehört es?',
     'medium', 'Musikinstrument', 'https://de.wikipedia.org/wiki/Musikinstrument',
     '[["Violine", "Streichinstrument", "Die Saiten werden mit dem Bogen gestrichen."],
       ["Trompete", "Blechblasinstrument", "Der Ton entsteht durch Lippenschwingung im Kesselmundstück."],
       ["Klarinette", "Holzblasinstrument", "Ein einfaches Rohrblatt erzeugt den Ton."],
       ["Pauke", "Schlaginstrument", "Das Fell wird angeschlagen und über ein Pedal gestimmt."],
       ["Harfe", "Zupfinstrument", "Die Saiten werden mit den Fingern gezupft."],
       ["Orgel", "Tasteninstrument", "Die Tasten öffnen die Ventile der Pfeifen."]]'::jsonb,
     '[["Elektrophon", "Die Orgel steht hier als Tasteninstrument; ein elektronisches fehlt."],
       ["Gesangsstimme", "Sie bildet eine eigene Gruppe, und die kommt hier nicht vor."]]'::jsonb),

    ('musik', 'komponisten-epochen', 'Komponisten & Epochen',
     'In welcher Epoche komponierte er?',
     'hard', 'Komponist', 'https://de.wikipedia.org/wiki/Komponist',
     '[["Johann Sebastian Bach", "Barock", "Sein Todesjahr 1750 gilt als Ende der Epoche."],
       ["Wolfgang Amadeus Mozart", "Wiener Klassik", "Neben Haydn und Beethoven ihr Hauptvertreter."],
       ["Frédéric Chopin", "Romantik", "Schrieb fast ausschließlich für das Klavier."],
       ["Claude Debussy", "Impressionismus", "Klangfarbe wurde wichtiger als klare Harmonik."],
       ["Arnold Schönberg", "Moderne", "Begründete die Zwölftonmusik."],
       ["Giovanni Palestrina", "Renaissance", "Meister der Vokalpolyphonie des 16. Jahrhunderts."],
       ["Guillaume de Machaut", "Mittelalter", "Führender Komponist der Ars nova."]]'::jsonb,
     '[["Minimal Music", "Steve Reich stünde dafür, und der fehlt auf diesem Brett."],
       ["Neue Musik nach 1945", "Kein Komponist in dieser Liste wird ihr zugerechnet."]]'::jsonb),

    ('musik', 'bands-herkunft', 'Bands & Herkunft',
     'Aus welchem Land kommt die Band?',
     'easy', 'Rockband', 'https://de.wikipedia.org/wiki/Rockband',
     '[["The Beatles", "Vereinigtes Königreich", "1960 in Liverpool gegründet."],
       ["Nirvana", "USA", "1987 in Aberdeen im Bundesstaat Washington gegründet."],
       ["ABBA", "Schweden", "1972 in Stockholm gegründet."],
       ["Rammstein", "Deutschland", "1994 in Berlin gegründet."],
       ["U2", "Irland", "1976 in Dublin gegründet."],
       ["AC/DC", "Australien", "1973 in Sydney gegründet."],
       ["Rush", "Kanada", "1968 in Toronto gegründet."]]'::jsonb,
     '[["Norwegen", "A-ha käme von dort, und die Band fehlt auf diesem Brett."],
       ["Italien", "Måneskin steht nicht in dieser Liste."]]'::jsonb),

    -- === Film & Fernsehen ==================================================
    ('film-fernsehen', 'regisseure-filme', 'Regisseure & Filme',
     'Wer hat bei dem Film Regie geführt?',
     'medium', 'Filmregisseur', 'https://de.wikipedia.org/wiki/Filmregisseur',
     '[["Pulp Fiction", "Quentin Tarantino", "Gewann 1994 die Goldene Palme in Cannes."],
       ["Inception", "Christopher Nolan", "2010, verschachtelte Traumebenen."],
       ["Psycho", "Alfred Hitchcock", "1960, berühmt für die Duschszene."],
       ["Der Pate", "Francis Ford Coppola", "1972, nach dem Roman von Mario Puzo."],
       ["Jurassic Park", "Steven Spielberg", "1993, Maßstab für digitale Effekte."],
       ["Parasite", "Bong Joon-ho", "Erster nicht englischsprachiger Oscar als bester Film."],
       ["Metropolis", "Fritz Lang", "1927, Klassiker des Stummfilms."]]'::jsonb,
     '[["Martin Scorsese", "Taxi Driver wäre der Film dazu, und der fehlt hier."],
       ["Akira Kurosawa", "Die sieben Samurai stehen nicht auf diesem Brett."]]'::jsonb),

    ('film-fernsehen', 'figuren-serien', 'Figuren & Serien',
     'Aus welcher Serie stammt die Figur?',
     'easy', 'Fernsehserie', 'https://de.wikipedia.org/wiki/Fernsehserie',
     '[["Walter White", "Breaking Bad", "Chemielehrer, der Crystal Meth zu kochen beginnt."],
       ["Homer Simpson", "Die Simpsons", "Sicherheitsinspektor im Kernkraftwerk von Springfield."],
       ["Jon Schnee", "Game of Thrones", "Zieht aus Winterfell zur Nachtwache an der Mauer."],
       ["Michael Scott", "The Office", "Regionalleiter der Papierfirma Dunder Mifflin."],
       ["Eleven", "Stranger Things", "Mädchen mit telekinetischen Kräften aus Hawkins."],
       ["Tony Soprano", "Die Sopranos", "Mafiaboss aus New Jersey, der in Therapie geht."],
       ["Don Draper", "Mad Men", "Werbetexter im New York der 1960er Jahre."]]'::jsonb,
     '[["Sherlock", "Keine Figur auf diesem Brett stammt daraus."],
       ["Friends", "Die Serie fehlt in dieser Liste."]]'::jsonb),

    ('film-fernsehen', 'filmgenres', 'Filme & Genres',
     'Zu welchem Genre gehört der Film?',
     'medium', 'Filmgenre', 'https://de.wikipedia.org/wiki/Filmgenre',
     '[["Alien", "Science-Fiction", "1979, das Grauen an Bord eines Raumschiffs."],
       ["Der Exorzist", "Horror", "1973, Teufelsaustreibung an einem Mädchen."],
       ["Ziemlich beste Freunde", "Komödie", "2011, Freundschaft zwischen Millionär und Pfleger."],
       ["Zwölf Uhr mittags", "Western", "1952, ein Sheriff allein gegen die Bande."],
       ["Casablanca", "Liebesfilm", "1942, Wiedersehen zweier Liebender im Krieg."],
       ["Stirb langsam", "Actionfilm", "1988, ein Polizist gegen Geiselnehmer im Hochhaus."],
       ["Der dritte Mann", "Film noir", "1949, harte Schatten und schiefe Kamerawinkel."]]'::jsonb,
     '[["Musical", "Kein Film auf diesem Brett gehört dazu."],
       ["Dokumentarfilm", "Auch dafür steht hier kein Film."]]'::jsonb),

    -- === Essen & Trinken ===================================================
    ('essen-trinken', 'gerichte-laender', 'Gerichte & Länder',
     'Aus welchem Land stammt das Gericht?',
     'easy', 'Nationalgericht', 'https://de.wikipedia.org/wiki/Nationalgericht',
     '[["Pizza Margherita", "Italien", "1889 in Neapel nach Königin Margherita benannt."],
       ["Sushi", "Japan", "Gesäuerter Reis, meist mit rohem Fisch."],
       ["Tacos", "Mexiko", "Gefüllte und gefaltete Maistortilla."],
       ["Paella", "Spanien", "Reisgericht aus Valencia, in flacher Pfanne gegart."],
       ["Wiener Schnitzel", "Österreich", "Paniertes Kalbfleisch, die Bezeichnung ist geschützt."],
       ["Gulasch", "Ungarn", "Paprikaeintopf, ursprünglich von Rinderhirten."],
       ["Moussaka", "Griechenland", "Auflauf aus Auberginen und Hackfleisch."]]'::jsonb,
     '[["Vietnam", "Phở käme von dort, und das Gericht fehlt auf dem Brett."],
       ["Indien", "Das Curry steht nicht in dieser Liste."]]'::jsonb),

    ('essen-trinken', 'gerichte-zutaten', 'Gerichte & Hauptzutaten',
     'Welche Zutat macht das Gericht aus?',
     'medium', 'Zutat', 'https://de.wikipedia.org/wiki/Zutat',
     '[["Guacamole", "Avocado", "Zerdrückte Avocado mit Limette und Salz."],
       ["Hummus", "Kichererbsen", "Püree aus Kichererbsen und Sesammus."],
       ["Pesto alla genovese", "Basilikum", "Basilikum wird mit Pinienkernen im Mörser zerrieben."],
       ["Tzatziki", "Joghurt", "Joghurt mit Gurke und Knoblauch."],
       ["Ratatouille", "Aubergine", "Auberginen tragen das provenzalische Gemüseschmoren."],
       ["Sauerkraut", "Weißkohl", "Milchsauer vergorener Weißkohl."],
       ["Polenta", "Maisgrieß", "Brei aus gekochtem Maisgrieß."]]'::jsonb,
     '[["Kartoffel", "Kein Gericht auf diesem Brett wird von ihr bestimmt."],
       ["Linsen", "Auch sie macht kein Gericht in dieser Liste aus."]]'::jsonb),

    ('essen-trinken', 'getraenke-herkunft', 'Getränke & Herkunft',
     'Woher stammt das Getränk?',
     'medium', 'Spirituose', 'https://de.wikipedia.org/wiki/Spirituose',
     '[["Scotch Whisky", "Schottland", "Muss mindestens drei Jahre in Schottland reifen."],
       ["Tequila", "Mexiko", "Aus blauer Agave, mit geschützter Herkunft."],
       ["Sake", "Japan", "Aus Reis gebraut, nicht gebrannt."],
       ["Cognac", "Frankreich", "Weinbrand aus der Region um die Stadt Cognac."],
       ["Wodka", "Russland", "Aus Getreide oder Kartoffeln gebrannt."],
       ["Grappa", "Italien", "Aus Traubentrester gebrannt."],
       ["Ouzo", "Griechenland", "Anisschnaps, der sich mit Wasser trübt."]]'::jsonb,
     '[["Peru", "Der Pisco käme von dort, und der fehlt auf diesem Brett."],
       ["Kuba", "Der Rum steht nicht in dieser Liste."]]'::jsonb)
),

-- `origin` is a literal rather than a column of `spec`: every question in this
-- file is hand-written by definition, and the value is what separates them from
-- the machine's afterwards.
new_quizzes as (
    insert into quizzes (subject_id, slug, title, description,
                         difficulty, source_title, source_url, origin)
    select s.id, sp.slug, sp.title, sp.description,
           sp.difficulty::difficulty, sp.source_title, sp.source_url, 'seed'
      from spec sp
      join subjects s on s.slug = sp.subject_slug
    returning id, slug
),

-- One row per pair, carrying all three parts. The ordinal is the position for
-- the category and its answer alike, which is what keeps the two aligned.
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
