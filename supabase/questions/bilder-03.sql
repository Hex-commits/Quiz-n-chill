-- Bildfragen: die Kategorie ist ein Foto, die Antwort ein Wort.
--
-- Anders als bei den Textdateien ist hier nichts aus dem Gedächtnis
-- geschrieben: jeder Dateiname und jede Lizenz stammt aus Wikidata (P18)
-- und Commons, abgefragt über denselben Provider, den tools/ingest nutzt.
-- Eine Kategorie ohne belegte Lizenz ist gar nicht erst aufgenommen --
-- categories_image_is_complete würde sie ohnehin zurückweisen.
--
-- Anwenden wie die Textdateien, siehe supabase/questions/batch-01.sql.

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-sportler-disziplinen', 'Sportgrößen im Bild',
           'In welcher Sportart wurde die Person berühmt?', 'medium'::difficulty,
           'Sport', 'https://de.wikipedia.org/wiki/Sport', 'image', 'seed'
      from subjects s
     where s.slug = 'sport'
       and not exists (select 1 from quizzes q where q.slug = 'bild-sportler-disziplinen')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Usain Bolt', 'Leichtathletik', 'Weltrekorde über 100 und 200 Meter.',
     'Usain Bolt Rio 100m final 2016k.jpg', 'Fernando Frazão/Agência Brasil',
     'CC BY 3.0 br', 'https://creativecommons.org/licenses/by/3.0/br/deed.en', 1),
    ('Michael Phelps', 'Schwimmen', '23 olympische Goldmedaillen.',
     'Michael Phelps August 2016.jpg', 'Agência Brasil Fotografias',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 2),
    ('Serena Williams', 'Tennis', '23 Grand-Slam-Titel im Einzel.',
     'Serena Williams at 2013 US Open.jpg', 'Edwin Martinez',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 3),
    ('Michael Jordan', 'Basketball', 'Sechs Meisterschaften mit den Chicago Bulls.',
     'Michael Jordan in 2014.jpg', 'DOD photo by D. Myles Cullen',
     'Public domain', null, 4),
    ('Lionel Messi', 'Fußball', 'Achtmal mit dem Ballon d''Or ausgezeichnet.',
     'Leo Messi Argentina v Egypt 7 July 2026-1.jpg', 'Bryan Berlin',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Muhammad Ali', 'Boxen', 'Dreimal Weltmeister im Schwergewicht.',
     'Muhammad Ali, gtfy.00140.jpg', 'Bernard Gotfryd',
     'Public domain', null, 6),
    ('Michael Schumacher', 'Formel 1', 'Sieben Weltmeistertitel.',
     'Michael Schumacher, September 2005.jpg', 'Original: Aécio Neves – Wellington Pedro/Imprensa MG / Derivative work: F1fans, FMSky',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 7),
    ('Tiger Woods', 'Golf', 'Fünfzehn Major-Titel.',
     'Tiger Woods in May 2019.jpg', 'The White House from Washington, DC',
     'Public domain', null, 8),
    ('Wayne Gretzky', 'Eishockey', 'Seine Nummer 99 ist ligaweit gesperrt.',
     'Wgretz (cropped3).jpg', 'The original uploader was Hakandahlstrom at English Wikipedia. Later versions were uploaded by IrisKawling at en.wikipedia.',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Eddy Merckx', 'Radsport', 'Fünfmal Sieger der Tour de France.',
     'Eddy Merckx Molteni 1973.jpg', 'Nationaal Archief',
     'No restrictions', 'https://www.flickr.com/commons/usage/', 10),
    ('Nadia Comăneci', 'Turnen', 'Erste perfekte Zehn bei Olympischen Spielen.',
     'Nadia Comăneci Moscow1980.jpeg', 'Unknown (Comitetul Olimpic si Sportiv Roman)',
     'Public domain', null, 11),
    ('Katarina Witt', 'Eiskunstlauf', 'Zweimal olympisches Gold in Folge.',
     '14-01-10-tbh-260-katarina-witt.jpg', 'Ralf Roletschek',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-stadien-laender', 'Stadien im Bild',
           'In welchem Land steht das Stadion?', 'hard'::difficulty,
           'Stadion', 'https://de.wikipedia.org/wiki/Stadion', 'image', 'seed'
      from subjects s
     where s.slug = 'sport'
       and not exists (select 1 from quizzes q where q.slug = 'bild-stadien-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Camp Nou', 'Spanien', 'Größtes Stadion Europas nach Plätzen.',
     'Camp Nou aerial (cropped).jpg', 'Oh-Barcelona.com from Barcelona, Spain',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 1),
    ('Estádio do Maracanã', 'Brasilien', '1950 sahen dort fast 200000 Menschen ein Endspiel.',
     'Maracana 2022.jpg', 'Arne Müseler',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 2),
    ('Allianz Arena', 'Deutschland', 'Die Außenhaut lässt sich farbig beleuchten.',
     'München - Allianz-Arena (Luftbild).jpg', 'Maximilian Dörrbecker (Chumwa)',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 3),
    ('Giuseppe-Meazza-Stadion', 'Italien', 'Zwei Vereine teilen sich das Haus.',
     'Stadio Meazza 2021 3.jpg', 'Prelvini',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 4),
    ('Stade de France', 'Frankreich', 'Für die Weltmeisterschaft 1998 gebaut.',
     'StadeFranceNationsLeague2018.jpg', 'Darthvadrouw',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Estadio Azteca', 'Mexiko', 'Schauplatz zweier WM-Endspiele.',
     'Vista aérea del Estadio Azteca - 2026 - 02.jpg', 'ProtoplasmaKid',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 6),
    ('Luschniki-Stadion', 'Russland', 'Finalort der Weltmeisterschaft 2018.',
     'LuzhnikiStadium.jpg', 'Government of Moscow Press centre',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 7),
    ('Johan Cruijff Arena', 'Niederlande', 'Erstes europäisches Stadion mit verschiebbarem Dach.',
     'Arena, Ajax stadion, Amsterdam.JPG', 'Alf van Beem',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 8),
    ('Melbourne Cricket Ground', 'Australien', 'Fasst über 100000 Zuschauer.',
     '2017 AFL Grand Final panorama during national anthem.jpg', 'Flickerd',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Yankee Stadium', 'USA', 'Heimstätte eines Baseballteams aus der Bronx.',
     'Yankee Stadium upper deck 2010.jpg', 'Matt Boulton',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 10),
    ('Ernst-Happel-Stadion', 'Österreich', 'Größtes Stadion des Landes.',
     'Euro 2008 ernst happel stadium vienna 2.jpg', 'Arne Müseler',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 11)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-sportgeraete', 'Sportgeräte im Bild',
           'Zu welcher Sportart gehört das Gerät?', 'hard'::difficulty,
           'Sportgerät', 'https://de.wikipedia.org/wiki/Sportger%C3%A4t', 'image', 'seed'
      from subjects s
     where s.slug = 'sport'
       and not exists (select 1 from quizzes q where q.slug = 'bild-sportgeraete')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Puck (Eishockey)', 'Eishockey', 'Hartgummischeibe, vor dem Spiel gekühlt.',
     'Hockey puck.JPG', 'No machine-readable author provided. Janothird~commonswiki assumed (based on copyright claims).',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 1),
    ('Curlingstein', 'Curling', 'Granitstein von rund zwanzig Kilogramm.',
     '12-01-20-yog-674.jpg', 'Ralf Roletschek',
     'CC BY-SA 3.0 at', 'https://creativecommons.org/licenses/by-sa/3.0/at/deed.en', 2),
    ('Federball', 'Badminton', 'Fliegt schneller als jeder andere Spielball.',
     'Volant badminton.jpg', 'No machine-readable author provided. Badplayer~commonswiki assumed (based on copyright claims).',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 3),
    ('Florett', 'Fechten', 'Treffer zählen nur am Rumpf.',
     'Pariser.jpg', 'User Rabe! on de.wikipedia',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 4),
    ('Queue (Billard)', 'Billard', 'Die Lederkuppe wird gekreidet.',
     'EVD-billar-378.jpg', 'User:Evdcoldeportes',
     'CC BY-SA 2.5 co', 'https://creativecommons.org/licenses/by-sa/2.5/co/deed.en', 5),
    ('Boxhandschuh', 'Boxen', 'Erst seit dem 19. Jahrhundert vorgeschrieben.',
     'Boxing gloves.jpg', 'en:User:Andman8',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 6),
    ('Steigeisen', 'Bergsteigen', 'Zacken für Eis und harten Firn.',
     'Strap-on crampon.JPG', 'Clayoquot',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Skateboard', 'Skateboarding', 'Aus dem Surfen an Land entstanden.',
     'Judi Oyama frontside grind Winchester Skatepark 1979 photo Richard Oyama.png', 'RSOyama',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 8),
    ('Pfeilbogen', 'Bogenschießen', 'Gespannt wird mit drei Fingern.',
     'Arco - África MN 01.jpg', 'Dornicke',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Surfbrett', 'Wellenreiten', 'Früher aus einem Stück Holz geschnitzt.',
     'Elevenfootersmall.jpg', 'No machine-readable author provided. Isurfwater assumed (based on copyright claims).',
     'Public domain', null, 10),
    ('Golfschläger', 'Golf', 'Ein Satz umfasst höchstens vierzehn Stück.',
     'ASICS''s wood clubs for Ground Golf and balls in Japan.jpg', 'kc7fys',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 11),
    ('Tischtennisschläger', 'Tischtennis', 'Eine Seite rot, eine schwarz.',
     'Tabletennis.jpg', 'PJ, User:Piko',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-regisseure-filme', 'Regisseure im Bild',
           'Von wem stammt dieser Film?', 'hard'::difficulty,
           'Filmregisseur', 'https://de.wikipedia.org/wiki/Filmregisseur', 'image', 'seed'
      from subjects s
     where s.slug = 'film-fernsehen'
       and not exists (select 1 from quizzes q where q.slug = 'bild-regisseure-filme')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Steven Spielberg', 'Jurassic Park', 'Maßstab für digitale Effekte.',
     'Steven Spielberg 2025.jpg', 'Raph_PH',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 1),
    ('Quentin Tarantino', 'Pulp Fiction', 'Goldene Palme 1994.',
     'Quentin Tarantino by Gage Skidmore.jpg', 'Gage Skidmore',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Alfred Hitchcock', 'Psycho', 'Berühmt für die Duschszene.',
     'Hitchcock, Alfred 02.jpg', 'Ante Brkan',
     'Public domain', null, 3),
    ('Martin Scorsese', 'Taxi Driver', 'New York als Fiebertraum.',
     'Martin Scorsese MFF 2023.jpg', 'Montclair Film',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 4),
    ('Christopher Nolan', 'Inception', 'Verschachtelte Traumebenen.',
     'Christopher Nolan.jpg', 'Republic of Korea',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Sofia Coppola', 'Lost in Translation', 'Zwei Fremde in einem Tokioter Hotel.',
     'Sofia Coppola-3275 (cropped).jpg', 'Harald Krichel',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Pedro Almodóvar', 'Volver', 'Farbenstarkes Melodram mit Penélope Cruz.',
     'Pedro Almodóvar-69720 (cropped).jpg', 'Harald Krichel',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 7),
    ('Akira Kurosawa', 'Die sieben Samurai', 'Vorbild für unzählige Westernfilme.',
     'Akirakurosawa-onthesetof7samurai-1953-page88.jpg', '映画の友 (Eiga no tomo)',
     'Public domain', null, 8),
    ('Werner Herzog', 'Fitzcarraldo', 'Ein Schiff wurde wirklich über den Berg gezogen.',
     'Werner Herzog Venice Film Festival 2009.jpg', 'Nicolas Genin',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Bong Joon-ho', 'Parasite', 'Erster nicht englischsprachiger Oscar als bester Film.',
     'Bong Joon Ho - Okja.jpg', 'Kevin Paul',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 10),
    ('Wim Wenders', 'Der Himmel über Berlin', 'Engel hören den Gedanken der Stadt zu.',
     'Wim Wenders at the 2026 Berlin International Film Festival-60630.jpg', 'Harald Krichel',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11),
    ('Greta Gerwig', 'Lady Bird', 'Erwachsenwerden in Sacramento.',
     'Greta Gerwig.jpg', 'Raph_PH',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-schauspieler-rollen', 'Schauspieler im Bild',
           'Welche Rolle ist mit dieser Person verbunden?', 'medium'::difficulty,
           'Schauspieler', 'https://de.wikipedia.org/wiki/Schauspieler', 'image', 'seed'
      from subjects s
     where s.slug = 'film-fernsehen'
       and not exists (select 1 from quizzes q where q.slug = 'bild-schauspieler-rollen')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Harrison Ford', 'Indiana Jones', 'Hut und Peitsche als Markenzeichen.',
     'Harrison Ford - Televerse 2025-03.jpg', 'Kevin Paul',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 1),
    ('Sigourney Weaver', 'Ellen Ripley', 'Die Rolle war ursprünglich männlich geschrieben.',
     'Sigourney Weaver at the 2025 Toronto International Film Festival (cropped).jpg', 'Desmond Herzfelder',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 2),
    ('Anthony Hopkins', 'Hannibal Lecter', 'Nur sechzehn Minuten Leinwandzeit, ein Oscar.',
     'Anthony Hopkins Red Sea Festival 2025 Portrait.jpg', 'Omar David Sandoval Sida',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Arnold Schwarzenegger', 'Terminator', 'Wenige Sätze, alle davon berühmt.',
     'Arnold Schwarzenegger 2025 (cropped).jpg', 'DHSgov',
     'Public domain', null, 4),
    ('Meryl Streep', 'Miranda Priestly', 'Die Bosheit klingt hier nur geflüstert.',
     'Meryl Streep- Press conference for the film "The Devil Wears Prada 2" - 55194765350 (cropped1).jpg', 'Ministry of culture, sports and Tourism- Lee Jeong-woo',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Keanu Reeves', 'Neo', 'Monatelanges Kampftraining vor dem Dreh.',
     'Keanu Reeves – Dogstar – Tons of Rock 2026-3.jpg', 'Birgit Fostervold',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Daniel Radcliffe', 'Harry Potter', 'Mit elf Jahren besetzt.',
     'Daniel Radcliffe in July 2015.jpg', 'Gage Skidmore from Peoria, AZ, United States of America',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 7),
    ('Gal Gadot', 'Wonder Woman', 'Ehemalige Soldatin der israelischen Armee.',
     'Gal Gadot for Revlon (cropped).jpg', 'Rogue Artists',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 8),
    ('Tom Hanks', 'Forrest Gump', 'Er läuft quer durch die US-Geschichte.',
     'Tom Hanks at the Elvis Premiere 2022.jpg', 'Eva Rinaldi from Abbotsford, Australia',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 9),
    ('Johnny Depp', 'Jack Sparrow', 'Vorbild war ein Rockgitarrist.',
     'Johnny Depp 2020.jpg', 'Harald Krichel',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 10),
    ('Jennifer Lawrence', 'Katniss Everdeen', 'Bogenschießen extra gelernt.',
     'Jennifer Lawrence, Cannes Film Festival 2025.jpg', 'Ciné Zooms 2',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 11),
    ('Robert Downey Jr.', 'Tony Stark', 'Viele Dialoge entstanden beim Drehen.',
     'Robert Downey Jr 2014 Comic Con (cropped).jpg', 'Gage Skidmore',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-musiker-instrumente', 'Musiker im Bild',
           'Welches Instrument spielte die Person?', 'medium'::difficulty,
           'Musiker', 'https://de.wikipedia.org/wiki/Musiker', 'image', 'seed'
      from subjects s
     where s.slug = 'musik'
       and not exists (select 1 from quizzes q where q.slug = 'bild-musiker-instrumente')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Jimi Hendrix', 'E-Gitarre', 'Spielte linkshändig auf umgedrehter Gitarre.',
     'Jimi Hendrix (1967) (cropped).jpg', 'Original photographer unknown',
     'Public domain', null, 1),
    ('Miles Davis', 'Trompete', 'Prägte gleich mehrere Jazzstile.',
     'Miles Davis (Three Deuces, New York, N.Y. 1947).jpg', 'William P. Gottlieb',
     'Public domain', null, 2),
    ('John Coltrane', 'Saxophon', 'Sein Album A Love Supreme gilt als Meilenstein.',
     'John Coltrane 1963 cropped ver2.jpg', 'Gelderen, Hugo van / Anefo',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 3),
    ('Glenn Gould', 'Klavier', 'Berühmt für seine Bach-Aufnahmen.',
     'Glenn Gould 1.jpg', 'Don Hunstein',
     'Attribution', null, 4),
    ('Yo-Yo Ma', 'Violoncello', 'Spielte bei mehreren Amtseinführungen.',
     'Yo-Yo Ma in 2018 (cropped).jpg', 'Joi Ito',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 5),
    ('Ravi Shankar', 'Sitar', 'Brachte indische Musik in den Westen.',
     'Ravi Shankar.jpg', 'Markgoff2972',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Keith Moon', 'Schlagzeug', 'Trommler von The Who.',
     'Keith Moon 4 - The Who - 1975.jpg', 'Jim Summaria',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('James Galway', 'Querflöte', 'Bekannt für seine goldene Flöte.',
     'JamesGalway.jpg', 'Shtue',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 8),
    ('Andrés Segovia', 'Konzertgitarre', 'Machte die klassische Gitarre konzertfähig.',
     'Andrés Segovia (1963) by Erling Mandelmann.jpg', 'Erling Mandelmann',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Toots Thielemans', 'Mundharmonika', 'Auch als Pfeifer auf Filmmusiken zu hören.',
     'Toots thielemans.jpg', 'Ron van der Kolk',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 10),
    ('Jaco Pastorius', 'E-Bass', 'Spielte bundlos und veränderte die Rolle des Basses.',
     'Jaco Pastorius with bass 1980.jpg', 'Chris Hakkens',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 11),
    ('Anne-Sophie Mutter', 'Violine', 'Mit dreizehn von Karajan entdeckt.',
     'Anne-Sophie Mutter B10-13 (cropped).jpg', 'A.Savin',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-opernhaeuser-staedte', 'Opernhäuser im Bild',
           'In welcher Stadt steht das Haus?', 'hard'::difficulty,
           'Opernhaus', 'https://de.wikipedia.org/wiki/Opernhaus', 'image', 'seed'
      from subjects s
     where s.slug = 'musik'
       and not exists (select 1 from quizzes q where q.slug = 'bild-opernhaeuser-staedte')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Teatro alla Scala', 'Mailand', 'Eröffnet 1778, Maßstab für Sängerkarrieren.',
     '20110725 Milano La Scala 5507.jpg', 'Jakub Hałun',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 1),
    ('Metropolitan Opera', 'New York', 'Seit 1966 am Lincoln Center.',
     'Metropolitan Opera House, Lincoln Center, January 30, 2025.jpg', 'D. Benjamin Miller',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 2),
    ('Bolschoi-Theater', 'Moskau', 'Bekannt für sein Ballettensemble.',
     'Moscow - 2025 - Facade of Big Theatre (1).jpg', 'Юрий Д.К.',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 3),
    ('Royal Opera House', 'London', 'Im Viertel Covent Garden.',
     'Royal Opera House and ballerina.jpg', 'Russ London (talk)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Palais Garnier', 'Paris', 'Prunktreppe und Deckengemälde von Chagall.',
     'Paris Palais Garnier 2010-04-06 16.55.07.jpg', 'Alexander Hoernigk',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 5),
    ('Teatro Colón', 'Buenos Aires', 'Berühmt für seine Akustik.',
     'Fachada del Teatro Colón en Buenos Aires, Argentina.jpg', 'EEJCC',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 6),
    ('Wiener Staatsoper', 'Wien', 'Einmal im Jahr wird sie zum Ballsaal.',
     'Staatsoper Wien DSC 5273w.jpg', 'P e z i',
     'CC BY-SA 3.0 at', 'https://creativecommons.org/licenses/by-sa/3.0/at/deed.en', 7),
    ('Gran Teatre del Liceu', 'Barcelona', 'Zweimal abgebrannt und wieder aufgebaut.',
     'Théâtre Liceu Barcelone 3.jpg', 'Chabe01',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Teatro La Fenice', 'Venedig', 'Der Name bedeutet Phönix, was zur Geschichte passt.',
     'Teatro La Fenice (Venice) - Facade.jpg', 'Didier Descouens',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Elbphilharmonie', 'Hamburg', 'Konzerthaus auf einem alten Kaispeicher.',
     '2019-05-10 Elbphilharmonie Hamburg.jpg', 'Burkhard Mücke',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 10),
    ('Semperoper', 'Dresden', 'Nach der Zerstörung 1985 neu eröffnet.',
     'Dresden - Semperoper - 2013.jpg', 'Avda',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 11)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-antike-staetten', 'Antike Stätten im Bild',
           'In welchem heutigen Land liegt die Stätte?', 'hard'::difficulty,
           'Archäologie', 'https://de.wikipedia.org/wiki/Arch%C3%A4ologie', 'image', 'seed'
      from subjects s
     where s.slug = 'geschichte'
       and not exists (select 1 from quizzes q where q.slug = 'bild-antike-staetten')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Akropolis', 'Griechenland', 'Tempelberg über Athen mit dem Parthenon.',
     'AthensAcropolisDawnAdj06028.jpg', 'User:Leonard G.',
     'Public domain', null, 1),
    ('Pyramiden von Gizeh', 'Ägypten', 'Einziges erhaltenes der antiken Weltwunder.',
     'Pyramids of the Giza Necropolis.jpg', 'KennyOMG',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 2),
    ('Chichén Itzá', 'Mexiko', 'Maya-Stadt mit der Pyramide des Kukulcán.',
     'Chichen Itza 3.jpg', 'Daniel Schwen',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Angkor Wat', 'Kambodscha', 'Größte Tempelanlage der Welt.',
     'Angkor wat temple.jpg', 'The original uploader was Fuzheado at English Wikipedia.',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 4),
    ('Persepolis', 'Iran', 'Residenz der Perserkönige.',
     'Gate of All Nations, Persepolis.jpg', 'Alborzagros',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 5),
    ('Palmyra', 'Syrien', 'Oasenstadt der Königin Zenobia.',
     'Palmira al capvespre (2495033007).jpg', 'Quim Bahí from Catalunya',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 6),
    ('Ephesos', 'Türkei', 'Mit der Fassade der Celsus-Bibliothek.',
     'Ephesus Celsus Library Façade.jpg', 'Benh LIEU SONG',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Karthago', 'Tunesien', 'Von Rom 146 v. Chr. zerstört.',
     'Tunisie Carthage Ruines 08.JPG', 'Calips',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 8),
    ('Timgad', 'Algerien', 'Römische Koloniestadt im Schachbrettgrundriss.',
     'Timgad Ruins Panorama.jpg', 'Hamza-sia',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Leptis Magna', 'Libyen', 'Heimatstadt des Kaisers Septimius Severus.',
     'Leptis Magna (29) (8288918733).jpg', 'joepyrek from Richmond, Va, USA',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 10),
    ('Mohenjo-Daro', 'Pakistan', 'Planstadt der Indus-Kultur mit Kanalisation.',
     'Mohenjodaro Sindh.jpeg', 'The original uploader was M.Imran at English Wikipedia.',
     'CC SA 1.0', 'http://creativecommons.org/licenses/sa/1.0/', 11)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-erfindungen-erfinder', 'Erfindungen im Bild',
           'Wer steckt hinter dem Gerät?', 'hard'::difficulty,
           'Erfindung', 'https://de.wikipedia.org/wiki/Erfindung', 'image', 'seed'
      from subjects s
     where s.slug = 'geschichte'
       and not exists (select 1 from quizzes q where q.slug = 'bild-erfindungen-erfinder')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Benz Patent-Motorwagen Nummer 1', 'Carl Benz', 'Der erste Wagen mit Verbrennungsmotor, 1886.',
     'Patent-Motorwagen Nr.1 Benz 2.jpg', 'DaimlerChrysler AG',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 1),
    ('Gutenberg-Bibel', 'Johannes Gutenberg', 'Erstes bedeutendes Buch aus beweglichen Lettern.',
     'Gutenberg Bible, Lenox Copy, New York Public Library, 2009. Pic 01.jpg', 'NYC Wanderer (Kevin Eng)',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 2),
    ('Wright Flyer', 'Brüder Wright', 'Erster gesteuerter Motorflug, 1903.',
     'First flight2.jpg', 'John T. Daniels',
     'Public domain', null, 3),
    ('Zuse Z3', 'Konrad Zuse', 'Erster frei programmierbarer Rechner.',
     'Z3 Deutsches Museum.JPG', 'Venusianer at German Wikipedia',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 4),
    ('Enigma (Maschine)', 'Arthur Scherbius', 'Rotoren verschlüsselten jeden Anschlag neu.',
     'Enigma (crittografia) - Museo scienza e tecnologia Milano.jpg', 'Alessandro Nassiri',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Sputnik 1', 'Sergei Koroljow', 'Erster Satellit im Erdorbit.',
     'Sputnik 1 satellite model.png', 'Soyuz235',
     'Public domain', null, 6),
    ('Dieselmotor', 'Rudolf Diesel', 'Zündung allein durch verdichtete Luft.',
     'MAN TGX V8 engine.JPG', 'High Contrast',
     'CC BY 3.0 de', 'https://creativecommons.org/licenses/by/3.0/de/deed.en', 7),
    ('Nipkow-Scheibe', 'Paul Nipkow', 'Zerlegte Bilder für die frühe Fernsehtechnik.',
     'Nipkow disk.svg', 'Hzeller, Stannered',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 8),
    ('Telefon', 'Alexander Graham Bell', 'Erhielt 1876 das US-Patent.',
     'Telefon BW 2012-02-18 13-44-32.JPG', 'Berthold Werner',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Glühlampe', 'Thomas Alva Edison', 'Machte die Kohlefadenlampe marktreif.',
     'Gluehlampe 01 KMJ.jpg', 'KMJ',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 10),
    ('Dynamit', 'Alfred Nobel', '1867 patentiert, Grundlage der Nobelpreise.',
     'Caisse dynamite nobel paulilles expo.JPG', 'Olecrab',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 11),
    ('Luftschiff', 'Ferdinand von Zeppelin', 'Erster Aufstieg 1900 über dem Bodensee.',
     'Zeppellin NT amk.JPG', 'AngMoKio',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-heimcomputer-hersteller', 'Heimcomputer im Bild',
           'Von welchem Hersteller stammt das Gerät?', 'hard'::difficulty,
           'Heimcomputer', 'https://de.wikipedia.org/wiki/Heimcomputer', 'image', 'seed'
      from subjects s
     where s.slug = 'technik'
       and not exists (select 1 from quizzes q where q.slug = 'bild-heimcomputer-hersteller')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Commodore 64', 'Commodore', 'Meistverkaufter Heimcomputer aller Zeiten.',
     'Commodore-64-Computer-FL.jpg', 'Evan-Amos',
     'Public domain', null, 1),
    ('Sinclair ZX Spectrum', 'Sinclair', 'Gummitastatur und Farbe auf dem Fernseher.',
     'ZXSpectrum48k.jpg', 'Bill Bertram',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 2),
    ('Apple II', 'Apple', 'Mit VisiCalc im Büro angekommen.',
     'Apple II IMG 4212.jpg', 'Rama &amp; Musée Bolo',
     'CC BY-SA 2.0 fr', 'https://creativecommons.org/licenses/by-sa/2.0/fr/deed.en', 3),
    ('IBM Personal Computer', 'IBM', 'Der offene Aufbau ermöglichte die Nachbauten.',
     'IBM PC-IMG 7271 (transparent).png', 'Rama &amp; Musée Bolo',
     'CC BY-SA 2.0 fr', 'https://creativecommons.org/licenses/by-sa/2.0/fr/deed.en', 4),
    ('Atari 2600', 'Atari', 'Machte Steckmodule zum Standard.',
     'Atari-2600-Light-Sixer-FL.jpg', 'Evan-Amos',
     'Public domain', null, 5),
    ('Nintendo Entertainment System', 'Nintendo', 'Rettete den Konsolenmarkt nach 1983.',
     'Wikipedia NES PAL.jpg', 'JCD1981NL',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 6),
    ('Sega Mega Drive', 'Sega', 'Der große Rivale des Super Nintendo.',
     'Sega-Genesis-NA-Mk2-Console-Set.png', 'Evan-Amos',
     'Public domain', null, 7),
    ('PlayStation', 'Sony', 'Setzte auf CD statt auf Module.',
     'PSX-Console-wController.jpg', 'Evan-Amos',
     'Public domain', null, 8),
    ('Xbox', 'Microsoft', 'Erste Konsole mit Festplatte serienmäßig.',
     'Xbox-console.jpg', 'Evan-Amos',
     'Public domain', null, 9),
    ('Amstrad CPC', 'Amstrad', 'In Deutschland als Schneider CPC verkauft.',
     'Amstrad CPC464.jpg', 'Bill Bertram',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 10),
    ('Amiga 500', 'Commodore International', 'Grafik und Ton weit über dem Zeitüblichen.',
     'Amiga500 system.jpg', 'Bill Bertram',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 11)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-getraenke-laender', 'Getränke im Bild',
           'Aus welchem Land stammt das Getränk?', 'medium'::difficulty,
           'Spirituose', 'https://de.wikipedia.org/wiki/Spirituose', 'image', 'seed'
      from subjects s
     where s.slug = 'essen-trinken'
       and not exists (select 1 from quizzes q where q.slug = 'bild-getraenke-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Sake', 'Japan', 'Aus Reis gebraut, nicht gebrannt.',
     'Sake set.jpg', 'The Epopt',
     'Public domain', null, 1),
    ('Tequila', 'Mexiko', 'Aus blauer Agave, mit geschützter Herkunft.',
     'Tequilas.JPG', 'Photomag',
     'Public domain', null, 2),
    ('Scotch Whisky', 'Schottland', 'Muss mindestens drei Jahre reifen.',
     'A Glass of Whiskey on the Rocks.jpg', 'Benjamin Thompson',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 3),
    ('Grappa', 'Italien', 'Aus Traubentrester gebrannt.',
     'Grappa Tradizione Nonino 41 deg.jpg', 'Marie-Lan Nguyen',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 4),
    ('Ouzo', 'Griechenland', 'Anisschnaps, der sich mit Wasser trübt.',
     'Пляшка узо.JPG', 'The original uploader was Turzh at Ukrainian Wikipedia.',
     'Public domain', null, 5),
    ('Wodka', 'Russland', 'Aus Getreide oder Kartoffeln gebrannt.',
     'Monopolowa Baczewski.JPG', 'Gryffindor',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('Cachaça', 'Brasilien', 'Grundlage der Caipirinha.',
     'Cachaca.JPG', 'Tom Tom at German Wikipedia',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 7),
    ('Soju', 'Südkorea', 'Meistverkaufte Spirituose der Welt.',
     'Cheers! (5618584428).jpg', 'Matt @ PEK from Taipei, Taiwan',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 8),
    ('Portwein', 'Portugal', 'Die Gärung wird mit Weinbrand gestoppt.',
     'Port wine.jpg', 'Jon Sullivan',
     'Public domain', null, 9),
    ('Mate-Tee', 'Argentinien', 'Wird aus einer Kalebasse getrunken.',
     'Erva mate chimarrao in big cuia.jpg', 'ChimaAddicted',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 10),
    ('Baijiu', 'China', 'Aus Hirse oder Sorghum gebrannt.',
     'Jiugui.jpg', 'Badagnani',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 11)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;
