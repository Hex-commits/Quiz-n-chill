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
    select s.id, 'bild-flaggen-hauptstaedte', 'Flaggen & Hauptstädte',
           'Welche Stadt ist die Hauptstadt zu dieser Flagge?', 'medium'::difficulty,
           'Flagge', 'https://de.wikipedia.org/wiki/Flagge', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-flaggen-hauptstaedte')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Japan', 'Tokio', 'Die rote Scheibe steht für die Sonne.',
     'Flag of Japan.svg', 'Various',
     'Public domain', null, 1),
    ('Brasilien', 'Brasília', 'Der Sternenhimmel zeigt einen Novemberabend 1889.',
     'Flag of Brazil.svg', 'Raimundo Teixeira Mendes',
     'Public domain', null, 2),
    ('Kanada', 'Ottawa', 'Das Ahornblatt hat elf Zacken.',
     'Flag of Canada (Pantone).svg', 'Original: George F. G. Stanley Modified by: The original uploader was Illegitimate Barrister at Wikimedia Commons. The current SVG encoding is a rewrite performed by MapGrid.',
     'Public domain', null, 3),
    ('Ägypten', 'Kairo', 'In der Mitte der Adler des Saladin.',
     'Flag of Egypt.svg', 'See File history below for details.',
     'Public domain', null, 4),
    ('Norwegen', 'Oslo', 'Ein blaues Kreuz im weißen Kreuz.',
     'Flag of Norway.svg', 'Original: Fredrik Meltzer Vector: Gutten på Hemsen',
     'Public domain', null, 5),
    ('Portugal', 'Lissabon', 'Die Armillarsphäre erinnert an die Seefahrt.',
     'Flag of Portugal (official).svg', 'Original: Columbano Bordalo Pinheiro Vector: Vítor Luís Rodrigues, António Martins-Tuválkin',
     'Public domain', null, 6),
    ('Griechenland', 'Athen', 'Neun Streifen für die Silben eines Freiheitsrufs.',
     'Flag of Greece.svg', 'Unknown authorUnknown author',
     'Public domain', null, 7),
    ('Südkorea', 'Seoul', 'In der Mitte das Yin-und-Yang-Zeichen.',
     'Flag of South Korea.svg', 'Original: Government of the Republic of Korea Vector: Great Brightstar and others',
     'Public domain', null, 8),
    ('Mexiko', 'Mexiko-Stadt', 'Ein Adler mit Schlange auf einem Kaktus.',
     'Flag of Mexico.svg', 'Alex Covarrubias, 9 April 2006. Based on the arms by Juan Manuel Gabino Villascán.',
     'Public domain', null, 9),
    ('Kenia', 'Nairobi', 'Ein Massai-Schild mit zwei Speeren.',
     'Flag of Kenya.svg', 'User:Pumbaa80',
     'Public domain', null, 10),
    ('Vietnam', 'Hanoi', 'Ein gelber Stern auf rotem Grund.',
     'Flag of Vietnam.svg', 'See File history below for details.',
     'Public domain', null, 11),
    ('Argentinien', 'Buenos Aires', 'Die Sonne des Mai in der Mitte.',
     'Flag of Argentina.svg', 'Manuel Belgrano',
     'Public domain', null, 12)
),
fakes (label, explanation, position) as (
    values
    ('Bangkok', 'Die Hauptstadt Thailands, dessen Flagge hier fehlt.', 13),
    ('Rio de Janeiro', 'Bis 1960 Hauptstadt Brasiliens, heute ist es Brasília.', 14)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-flaggen-waehrungen', 'Flaggen & Währungen',
           'Womit wird in diesem Land bezahlt?', 'hard'::difficulty,
           'Flagge', 'https://de.wikipedia.org/wiki/Flagge', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-flaggen-waehrungen')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Schweiz', 'Franken', 'Eine der beiden quadratischen Nationalflaggen.',
     'Flag of Switzerland.svg', 'Original: Unknown Vector: User:Marc Mongenet Credits: User:-xfi- User:Zscout370',
     'Public domain', null, 1),
    ('Polen', 'Złoty', 'Der Name der Währung bedeutet golden.',
     'Flag of Poland.svg', 'See below.',
     'Public domain', null, 2),
    ('Indien', 'Rupie', 'Das Rad in der Mitte heißt Ashoka-Chakra.',
     'Flag of India.svg', 'Government of India',
     'Public domain', null, 3),
    ('Russland', 'Rubel', 'Eine der ältesten noch genutzten Währungen.',
     'Flag of Russia.svg', 'Peter the Great',
     'Public domain', null, 4),
    ('Dänemark', 'Dänische Krone', 'Gilt als älteste durchgehend genutzte Flagge.',
     'Flag of Denmark.svg', 'Madden and others',
     'Public domain', null, 5),
    ('Vereinigtes Königreich', 'Pfund Sterling', 'Drei Kreuze in einer Flagge vereint.',
     'Flag of the United Kingdom (3-5).svg', 'Original: Acts of Union 1800 Vector: Yaddah',
     'Public domain', null, 6),
    ('Südafrika', 'Rand', 'Sechs Farben, mehr als jede andere Nationalflagge.',
     'Flag of South Africa.svg', 'Flag design by Frederick Brownell, image by Wikimedia Commons users',
     'Public domain', null, 7),
    ('Thailand', 'Baht', 'Fünf Streifen für Nation, Religion und König.',
     'Flag of Thailand.svg', 'Zscout370',
     'Public domain', null, 8),
    ('Israel', 'Schekel', 'Der Davidstern zwischen zwei Streifen.',
     'Flag of Israel.svg', 'Israel Belkind and Fanny Abramovitch (original) “The Provisional Council of State Proclamation of the Flag of the State of Israel” of 25 Tishrei 5709 (28 October 1948) provides the official specification for the design of the Israeli flag. The color of the Magen David and the stripes of the Israeli flag is not precisely specified by the above legislation. The color depicted in the current version of the image is typical of flags used in Israel today, although individual flags can and do vary. The flag legislation officially specifies dimensions of 220 cm × 160 cm. However, the sizes of actual flags vary (although the aspect ratio is usually retained).',
     'Public domain', null, 9),
    ('Türkei', 'Türkische Lira', 'Halbmond und Stern auf Rot.',
     'Flag of Turkey.svg', 'David Benbennick (original author)',
     'Public domain', null, 10),
    ('Schweden', 'Schwedische Krone', 'Gelbes Kreuz auf blauem Grund.',
     'Flag of Sweden.svg', 'Jon Harald Søby and others.',
     'Public domain', null, 11),
    ('Japan', 'Yen', 'Die Sonne ohne jedes weitere Zeichen.',
     'Flag of Japan.svg', 'Various',
     'Public domain', null, 12)
),
fakes (label, explanation, position) as (
    values
    ('Forint', 'Damit zahlt man in Ungarn, dessen Flagge auf dem Brett fehlt.', 13),
    ('Euro', 'Kein Land in dieser Liste bezahlt damit.', 14)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-umrisse-groesste-staedte', 'Länder auf der Karte',
           'Welche Stadt ist die größte des Landes — die Hauptstadt ist es nicht?', 'hard'::difficulty,
           'Landkarte', 'https://de.wikipedia.org/wiki/Landkarte', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-umrisse-groesste-staedte')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Türkei', 'Istanbul', 'Ankara regiert, doch Istanbul ist weit größer.',
     'Turkey (orthographic projection).svg', 'The Emirr',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 1),
    ('USA', 'New York', 'Washington ist nur Regierungssitz.',
     'United States - Location Map (2013) - USA - UNOCHA.svg', 'UN Office for the Coordination of Humanitarian Affairs (OCHA)',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 2),
    ('Kanada', 'Toronto', 'Ottawa wurde 1857 als Kompromiss gewählt.',
     'CAN orthographic.svg', 'Addicted04',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 3),
    ('Australien', 'Sydney', 'Canberra entstand als Kompromiss zu Melbourne.',
     'AUS orthographic.svg', 'David Ayala',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Brasilien', 'São Paulo', 'Größte Stadt der Südhalbkugel.',
     'BRA orthographic.svg', 'David Ayala',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 5),
    ('Indien', 'Mumbai', 'Finanzzentrum des Landes, früher Bombay.',
     'India (orthographic projection).svg', 'Ssolbergj (talk)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('Schweiz', 'Zürich', 'Bern ist lediglich Bundesstadt.',
     'Switzerland on the globe (Europe centered).svg', 'TUBS',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Marokko', 'Casablanca', 'Wirtschaftszentrum an der Atlantikküste.',
     'Morocco WS-excluded (orthographic projection).svg', 'Flad',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 8),
    ('Vietnam', 'Ho-Chi-Minh-Stadt', 'Früher Saigon, größer als Hanoi.',
     'Vietnam on the globe (Asia centered).svg', 'TUBS',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Neuseeland', 'Auckland', 'Rund ein Drittel des Landes lebt hier.',
     'NZL orthographic.svg', 'Addicted04',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 10),
    ('Nigeria', 'Lagos', 'Eine der größten Städte Afrikas.',
     'Nigeria (orthographic projection).svg', 'Ukabia',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 11),
    ('Pakistan', 'Karatschi', 'Hafenstadt, bis 1959 Hauptstadt.',
     'Pakistan on the globe (de-facto and claimed hatched) (Afro-Eurasia centered).svg', 'TUBS',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 12)
),
fakes (label, explanation, position) as (
    values
    ('Melbourne', 'Die zweitgrößte Stadt Australiens, nicht die größte.', 13),
    ('Rio de Janeiro', 'Nach São Paulo die zweitgrößte Stadt Brasiliens.', 14)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-wappen-landeshauptstaedte', 'Wappen der Bundesländer',
           'Welche Stadt ist die Landeshauptstadt?', 'hard'::difficulty,
           'Wappen', 'https://de.wikipedia.org/wiki/Wappen', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-wappen-landeshauptstaedte')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Bayern', 'München', 'Die weiß-blauen Rauten in der Mitte.',
     'Coat of arms of Bavaria.svg', 'Bayerisches Staatsministerium für Unterricht und Kultus: G8. Das neue Gymnasium in Bayern (PDF-Broschüre)',
     'Public domain', null, 1),
    ('Sachsen', 'Dresden', 'Ein Rautenkranz quert die Balken.',
     'Coat of arms of Saxony.svg', 'Das Erscheinungsbild des Freistaates Sachsen (Markenhandbuch Version 2.0 vom 8.2.2013 [PDF-Datei, 23,89 MB]) 2015-03-20 von ludger1961 aus PDF extrahiert und bearbeitet Earlier versions Wappen entnommen aus dem Landessignet Sachsens - Variante 2 - von der offiziellen Internetseite. Siehe sachsen.de - Geschichte (2006-Feb-25) Verordnung der Sächsischen Staatsregierung über die Verwendung des Wappens des Freistaates Sachsen (Wappenverordnung - WappenVO). Vom 4. März 2005 Offizielles Video',
     'Public domain', null, 2),
    ('Hessen', 'Wiesbaden', 'Der rot-weiß gestreifte Löwe.',
     'Coat of arms of Hesse.svg', 'Vectorization from PDF-flyer "Stand der Reform der Landesverwaltung" direct link to file, link to 1948 law, link to 1949 image',
     'Public domain', null, 3),
    ('Thüringen', 'Erfurt', 'Ein Löwe mit acht Sternen.',
     'Coat of arms of Thuringia.svg', 'Wappen (EPS) auf Landespräsenz (thueringen.de)',
     'Public domain', null, 4),
    ('Saarland', 'Saarbrücken', 'Vier Felder für vier historische Gebiete.',
     'Wappen des Saarlands.svg', 'Fahnen Kössinger: Flaggenkatalog 2012, Seite 37 2012-06-30 von ludger1961 (talk) mit INKSCAPE aus PDF extrahiert und bearbeitet',
     'Public domain', null, 5),
    ('Brandenburg', 'Potsdam', 'Der rote Adler auf Weiß.',
     'DEU Brandenburg COA.svg', 'Unknown authorUnknown author',
     'Public domain', null, 6),
    ('Niedersachsen', 'Hannover', 'Das weiße Ross auf Rot.',
     'Coat of arms of Lower Saxony.svg', 'Gustav Völker',
     'Public domain', null, 7),
    ('Schleswig-Holstein', 'Kiel', 'Zwei Löwen und ein Nesselblatt.',
     'DEU Schleswig-Holstein COA.svg', 'Schleswig Holstein - Landeswappen',
     'Public domain', null, 8),
    ('Mecklenburg-Vorpommern', 'Schwerin', 'Stierkopf und Greif in einem Schild.',
     'Coat of arms of Mecklenburg-Western Pomerania (great).svg', 'PDF file',
     'Public domain', null, 9),
    ('Rheinland-Pfalz', 'Mainz', 'Rad, Kreuz und Löwe nebeneinander.',
     'Coat of arms of Rhineland-Palatinate.svg', 'PDF file',
     'Public domain', null, 10),
    ('Baden-Württemberg', 'Stuttgart', 'Drei schwarze Löwen auf Gold.',
     'Greater coat of arms of Baden-Württemberg.svg', 'Bedřich Meinhard',
     'Public domain', null, 11),
    ('Sachsen-Anhalt', 'Magdeburg', 'Geteilt zwischen Adler und Bär.',
     'Wappen Sachsen-Anhalt.svg', 'PDF-Broschüre „Das Wappen des Landes Sachsen-Anhalt“',
     'Public domain', null, 12)
),
fakes (label, explanation, position) as (
    values
    ('Düsseldorf', 'Die Landeshauptstadt Nordrhein-Westfalens, dessen Wappen hier fehlt.', 13),
    ('Bremen', 'Ein Stadtstaat, und er steht nicht auf diesem Brett.', 14)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-elemente-symbole', 'Elemente im Bild',
           'Welches Symbol steht für dieses Element?', 'hard'::difficulty,
           'Chemisches Element', 'https://de.wikipedia.org/wiki/Chemisches_Element', 'image', 'seed'
      from subjects s
     where s.slug = 'naturwissenschaft'
       and not exists (select 1 from quizzes q where q.slug = 'bild-elemente-symbole')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Gold', 'Au', 'Vom lateinischen aurum.',
     'Gold-crystals.jpg', 'Alchemist-hp (talk) www.pse-mendelejew.de',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 1),
    ('Schwefel', 'S', 'Gelbe Kristalle, brennt mit blauer Flamme.',
     'Sulfur - El Desierto mine, San Pablo de Napa, Daniel Campos Province, Potosí, Bolivia.jpg', 'Ivar Leidus',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 2),
    ('Kupfer', 'Cu', 'Vom lateinischen cuprum, nach Zypern.',
     'Cuivre Michigan.jpg', 'Didier Descouens',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Quecksilber', 'Hg', 'Einziges bei Raumtemperatur flüssiges Metall.',
     'Mercury-element.jpg', null,
     'Public domain', null, 4),
    ('Eisen', 'Fe', 'Vom lateinischen ferrum.',
     'Iron electrolytic and 1cm3 cube.jpg', 'Alchemist-hp (talk) (www.pse-mendelejew.de)',
     'FAL', 'http://artlibre.org/licence/lal/en', 5),
    ('Blei', 'Pb', 'Vom lateinischen plumbum.',
     'Lead electrolytic and 1cm3 cube.jpg', 'Alchemist-hp (talk) (www.pse-mendelejew.de)',
     'FAL', 'http://artlibre.org/licence/lal/en', 6),
    ('Zink', 'Zn', 'Schützt als Überzug den Stahl vor Rost.',
     'Zinc fragment sublimed and 1cm3 cube.jpg', 'Alchemist-hp (talk) (www.pse-mendelejew.de)',
     'FAL', 'http://artlibre.org/licence/lal/en', 7),
    ('Silber', 'Ag', 'Bester elektrischer Leiter aller Metalle.',
     'Silver crystal.jpg', 'Alchemist-hp (talk) (www.pse-mendelejew.de)',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 8),
    ('Aluminium', 'Al', 'War vor der Elektrolyse teurer als Gold.',
     'Aluminium-4.jpg', 'Unknown authorUnknown author',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 9),
    ('Iod', 'I', 'Sublimiert zu violettem Dampf.',
     'Sample of iodine.jpg', 'LHcheM',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 10),
    ('Kohlenstoff', 'C', 'Als Diamant und als Graphit dasselbe Element.',
     'Coal anthracite.jpg', 'http://resourcescommittee.house.gov/subcommittees/emr/usgsweb/photogallery/images/Coal,%20anthracite_jpg',
     'Public domain', null, 11)
),
fakes (label, explanation, position) as (
    values
    ('Sn', 'Das Symbol für Zinn, und das Element fehlt auf diesem Brett.', 12),
    ('Na', 'Natrium trägt es, und das steht nicht in dieser Liste.', 13)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-persoenlichkeiten-wirken', 'Porträts der Geschichte',
           'Wofür steht diese Person?', 'hard'::difficulty,
           'Porträt', 'https://de.wikipedia.org/wiki/Portr%C3%A4t', 'image', 'seed'
      from subjects s
     where s.slug = 'geschichte'
       and not exists (select 1 from quizzes q where q.slug = 'bild-persoenlichkeiten-wirken')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Albert Einstein', 'Relativitätstheorie', 'Den Nobelpreis erhielt er für etwas anderes.',
     'Albert Einstein Head cleaned.jpg', 'Oren Jack Turner',
     'Public domain', null, 1),
    ('Marie Curie', 'Radioaktivität', 'Zwei Nobelpreise in zwei Fächern.',
     'Marie Curie (1900) (cropped).jpg', 'Unknown authorUnknown author',
     'Public domain', null, 2),
    ('Charles Darwin', 'Evolutionstheorie', 'Fünf Jahre an Bord der Beagle.',
     'Charles Darwin portrait.jpg', 'Herbert Rose Barraud',
     'Public domain', null, 3),
    ('Nikola Tesla', 'Wechselstrom', 'Setzte sich gegen Edisons Gleichstrom durch.',
     'Tesla circa 1890.jpeg', 'Napoleon Sarony',
     'Public domain', null, 4),
    ('Mahatma Gandhi', 'Gewaltloser Widerstand', 'Der Salzmarsch als bekannteste Aktion.',
     'Mahatma-Gandhi, studio, 1931.jpg', 'Elliott &amp; Fry',
     'Public domain', null, 5),
    ('Rosa Parks', 'Busboykott von Montgomery', 'Sie blieb 1955 einfach sitzen.',
     'Rosa Parks 1997.jpg', 'John Mathew Smith &amp; www.celebrity-photos.com from Laurel Maryland, USA',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 6),
    ('Alan Turing', 'Turingmaschine', 'Modell dessen, was berechenbar ist.',
     'Alan Turing (1951) (crop).jpg', 'Elliott &amp; Fry',
     'Public domain', null, 7),
    ('Ada Lovelace', 'Erstes Computerprogramm', 'Für eine Maschine, die nie gebaut wurde.',
     'Ada Byron daguerreotype by Antoine Claudet 1843 or 1850 - cropped.png', 'Antoine Claudet',
     'Public domain', null, 8),
    ('Ludwig van Beethoven', 'Neunte Sinfonie', 'Komponiert, als er längst taub war.',
     'Beethoven.jpg', 'Joseph Karl Stieler',
     'Public domain', null, 9),
    ('Frida Kahlo', 'Selbstbildnisse', 'Ein Großteil ihres Werks zeigt sie selbst.',
     'Frida Kahlo, by Guillermo Kahlo (cropped).jpg', 'Guillermo Kahlo',
     'Public domain', null, 10),
    ('Nelson Mandela', 'Ende der Apartheid', '27 Jahre Haft, dann Präsident.',
     'Nelson Mandela 1994.jpg', 'Kingkongphoto &amp; www.celebrity-photos.com from Laurel',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 11),
    ('Johannes Gutenberg', 'Buchdruck mit Lettern', 'Bewegliche Metalllettern, um 1450.',
     'Gutenberg.jpg', 'http://www.sru.edu/depts/cisba/compsci/dailey/217students/sgm8660/Final/',
     'Public domain', null, 12)
),
fakes (label, explanation, position) as (
    values
    ('Erste Frau im Weltall', 'Walentina Tereschkowa steht dafür, und die fehlt hier.', 13),
    ('Penicillin', 'Alexander Fleming ist auf diesem Brett nicht abgebildet.', 14)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-sakralbauten-religionen', 'Sakralbauten & Religionen',
           'Zu welcher Religion gehört der Bau?', 'hard'::difficulty,
           'Sakralbau', 'https://de.wikipedia.org/wiki/Sakralbau', 'image', 'seed'
      from subjects s
     where s.slug = 'kunst-kultur'
       and not exists (select 1 from quizzes q where q.slug = 'bild-sakralbauten-religionen')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Kölner Dom', 'Christentum', 'Gotische Kathedrale, 1880 vollendet.',
     'Kölner Dom von Osten.jpg', 'Thomas Wolf, www.foto-tw.de',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 1),
    ('Sultan-Ahmed-Moschee', 'Islam', 'Wegen der Fliesen Blaue Moschee genannt.',
     'Exterior of Sultan Ahmed I Mosque in Istanbul, Turkey 002.jpg', 'Moonik',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Harmandir Sahib', 'Sikhismus', 'Der Goldene Tempel von Amritsar.',
     'Hamandir Sahib (Golden Temple).jpg', 'This picture has been taken by Oleg Yunakov. Contact e-mail: yunakovgmail.com. Image can be used in accordance with the terms of the СС-BY-SA license. Other photos can be seen here.',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 3),
    ('Borobudur', 'Buddhismus', 'Größte buddhistische Tempelanlage der Welt.',
     'Borobudur-Nothwest-view.jpg', 'Gunawan Kartapranata',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Meenakshi-Tempel', 'Hinduismus', 'Türme voller bunt bemalter Figuren.',
     'Meenakshi Temple, Gopuram, Madurai, India.jpg', 'Vyacheslav Argenberg',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 5),
    ('Große Synagoge (Budapest)', 'Judentum', 'Größte Synagoge Europas.',
     'Synagogue-Budapest.jpg', 'The original uploader was OsvátA at Hungarian Wikipedia.',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 6),
    ('Ise-jingū', 'Shintō', 'Wird alle zwanzig Jahre neu errichtet.',
     'Ise-Shrine Itagaki-minami-gomon.jpg', 'MaedaAkihiko',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 7),
    ('Lotustempel', 'Bahaitum', 'Neun Seiten, allen Religionen offen.',
     'Lotus temple daytime.jpg', 'Muhammad Mahdi Karim',
     'GFDL 1.2', 'http://www.gnu.org/licenses/old-licenses/fdl-1.2.html', 8),
    ('Himmelstempel', 'Daoismus', 'Hier beteten die Kaiser um gute Ernten.',
     'Temple of Heaven 20160323 01.jpg', 'Shujianyang',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Dilwara-Tempel', 'Jainismus', 'Marmorarbeiten von außerordentlicher Feinheit.',
     'Delwada.jpg', 'Malaiya at en.wikipedia',
     'GFDL', 'http://www.gnu.org/copyleft/fdl.html', 10)
),
fakes (label, explanation, position) as (
    values
    ('Zoroastrismus', 'Kein Bau auf diesem Brett gehört dazu.', 11),
    ('Konfuzianismus', 'Auch dafür steht in dieser Liste kein Bauwerk.', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-katzenrassen-herkunft', 'Katzenrassen & Herkunft',
           'Aus welchem Land stammt die Rasse?', 'hard'::difficulty,
           'Katzenrassen', 'https://de.wikipedia.org/wiki/Katzenrassen', 'image', 'seed'
      from subjects s
     where s.slug = 'naturwissenschaft'
       and not exists (select 1 from quizzes q where q.slug = 'bild-katzenrassen-herkunft')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Siamkatze', 'Thailand', 'Die dunklen Abzeichen entstehen durch Wärme.',
     'Gatosiames.jpg', 'Ulics676767',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 1),
    ('Perserkatze', 'Iran', 'Langes Fell, kurze Nase.',
     'Chocolate Persian.jpg', 'Cindy See',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 2),
    ('Maine Coon', 'USA', 'Eine der größten Hauskatzenrassen.',
     'Фото кунов.jpg', 'Ankord',
     'Public domain', null, 3),
    ('Norwegische Waldkatze', 'Norwegen', 'Dichtes Fell gegen den Winter.',
     'Noorse-boskat wikipedia 1.JPG', 'Wieke de Rijk, Netherlands at nl.wikipedia',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 4),
    ('Russisch Blau', 'Russland', 'Silbrig schimmerndes Doppelfell.',
     'Ruskis dimka 3 (cropped).jpg', 'ruskis',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 5),
    ('Britisch Kurzhaar', 'Vereinigtes Königreich', 'Rundes Gesicht, plüschiges Fell.',
     'Mystica from British Empire Cattery.jpg', 'BritishEmpire',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('Türkisch Angora', 'Türkei', 'Eine der ältesten bekannten Rassen.',
     'Fantine de l''Empire Ottoman.jpg', 'Empire.ottoman',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Abessinierkatze', 'Äthiopien', 'Getickte Haare wie bei einem Wildkaninchen.',
     'Abessinierkater1.jpg', 'Martin Bahmann',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 8),
    ('Chartreux', 'Frankreich', 'Der Sage nach von Mönchen gezüchtet.',
     'CertosinoFemmina.JPG', 'Fureur Bleu',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Japanese Bobtail', 'Japan', 'Kurzer, geknickter Schwanz.',
     'JapaneseBobtailBlueEyedMi-ke.JPG', 'ようてい',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 10)
),
fakes (label, explanation, position) as (
    values
    ('Ägypten', 'Die Ägyptische Mau käme von dort, und die fehlt auf dem Brett.', 11),
    ('Kanada', 'Die Sphynx stammt von dort, sie steht nicht in dieser Liste.', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-wasserfaelle-laender', 'Wasserfälle im Bild',
           'In welchem Land stürzt der Wasserfall?', 'hard'::difficulty,
           'Wasserfall', 'https://de.wikipedia.org/wiki/Wasserfall', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-wasserfaelle-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Salto Ángel', 'Venezuela', 'Höchster freifallender Wasserfall der Erde.',
     'SaltoAngel4.jpg', 'Paulo Capiotti',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 1),
    ('Gullfoss', 'Island', 'Der goldene Wasserfall im Süden der Insel.',
     'GullfossOverview.jpg', 'Andreas Tille',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 2),
    ('Rheinfall', 'Schweiz', 'Größter Wasserfall Europas nach Wassermenge.',
     'Chutes du Rhin - Octobre 2021.jpg', 'Christian David',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Krimmler Wasserfälle', 'Österreich', '385 Meter in drei Stufen.',
     '1444 - Nationalpark Hohe Tauern - Krimmler Wasserfälle.JPG', 'Andrew Bossi',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 4),
    ('Yosemite Falls', 'USA', 'Höchster Wasserfall Nordamerikas.',
     'Yosemite falls winter 2010.JPG', 'chensiyuan',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Kaieteur-Fälle', 'Guyana', 'Einstufig, mitten im Regenwald.',
     'GuyanaKaieteurFalls2004.jpg', 'Sorenriise at English Wikipedia',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('Tugela Falls', 'Südafrika', 'Stürzt von den Drakensbergen.',
     'Tugela Falls.jpg', 'PhilippN',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 7),
    ('Jog Falls', 'Indien', 'Fällt in vier getrennten Strahlen.',
     'Jog Falls at Shimoga.jpg', 'Arkadeep Meta',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Sutherland Falls', 'Neuseeland', '580 Meter im Fiordland.',
     'Sutherland Falls.jpg', 'Original uploader was Ozhiker at en.wikipedia',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 9),
    ('Ban Gioc', 'Vietnam', 'Terrassenfall an der Grenze zu China.',
     'Ban Gioc - Detian Falls2.jpg', 'jankgo',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 10)
),
fakes (label, explanation, position) as (
    values
    ('Simbabwe', 'Die Victoriafälle stürzten dort, und die fehlen auf dem Brett.', 11),
    ('Argentinien', 'Die Iguazú-Fälle stehen nicht in dieser Liste.', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-autos-marken', 'Klassische Autos',
           'Von welcher Marke stammt das Auto?', 'hard'::difficulty,
           'Automobil', 'https://de.wikipedia.org/wiki/Automobil', 'image', 'seed'
      from subjects s
     where s.slug = 'technik'
       and not exists (select 1 from quizzes q where q.slug = 'bild-autos-marken')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('VW Käfer', 'Volkswagen', 'Über 21 Millionen Mal gebaut.',
     'VW Käfer Baujahr 1966.jpg', 'Vwexport1300',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 1),
    ('Citroën 2CV', 'Citroën', 'Die Ente, gebaut für schlechte Landstraßen.',
     'Paris - Bonhams 2013 - Citroën 2CV A - 1950 - 002.jpg', 'Thesupermat',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Fiat Nuova 500', 'Fiat', 'Der Cinquecento motorisierte Italien.',
     '1970 Fiat 500 L -- 2011 DC 1.jpg', 'IFCAR',
     'Public domain', null, 3),
    ('Ford Modell T', 'Ford', 'Erstes Auto vom Fließband.',
     'Ford T Jon Sullivan.jpg', 'Jon Sullivan',
     'Public domain', null, 4),
    ('Porsche 911', 'Porsche', 'Der Motor sitzt hinter der Hinterachse.',
     '2025 Porsche 992 Carrera convertible Auto Zuerich 2024 DSC 6527.jpg', 'Alexander-93',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Jaguar E-Type', 'Jaguar', 'Von Enzo Ferrari als schönstes Auto gelobt.',
     'Ol car06a.JPG', 'Tedmek',
     'Public domain', null, 6),
    ('Chevrolet Corvette', 'Chevrolet', 'Karosserie aus Kunststoff.',
     '2023 Chevrolet Corvette Z06 3LZ Convertible (52803363083).jpg', 'Greg Gjerdingen from Willmar, USA',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 7),
    ('Trabant 601', 'Sachsenring', 'Karosserie aus Duroplast.',
     'AWZ Trabant 601S, Verkehrszentrum des Deutschen Museums.JPG', 'High Contrast',
     'CC BY 3.0 de', 'https://creativecommons.org/licenses/by/3.0/de/deed.en', 8),
    ('Lada Niva', 'Lada', 'Geländewagen mit selbsttragender Karosserie.',
     'VAZ-2121 Niva.jpg', 'w:ru:Sah68 (talk | contribs)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('DeLorean DMC-12', 'DeLorean Motor Company', 'Flügeltüren und blanke Edelstahlhaut.',
     'Delorean DMC-12 side.jpg', 'Kevin Abato, www.grenexmedia.com',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 10)
),
fakes (label, explanation, position) as (
    values
    ('Renault', 'Die R4 käme von dort, und sie fehlt auf diesem Brett.', 11),
    ('Mini', 'Der klassische Mini steht nicht in dieser Liste.', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-kaese-laender', 'Käse im Bild',
           'Aus welchem Land stammt der Käse?', 'hard'::difficulty,
           'Käse', 'https://de.wikipedia.org/wiki/K%C3%A4se', 'image', 'seed'
      from subjects s
     where s.slug = 'essen-trinken'
       and not exists (select 1 from quizzes q where q.slug = 'bild-kaese-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Roquefort (Käse)', 'Frankreich', 'Reift in Kalkhöhlen der Causses.',
     'Wikicheese - Roquefort - 20150417 - 002.jpg', 'Thesupermat',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 1),
    ('Manchego', 'Spanien', 'Schafskäse aus La Mancha.',
     'Flickr - cyclonebill - Manchego.jpg', 'cyclonebill',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 2),
    ('Gouda (Käse)', 'Niederlande', 'Benannt nach der Marktstadt.',
     'Chesses gouda affinage.JPG', 'No machine-readable author provided. Alpha.prim~commonswiki assumed (based on copyright claims).',
     'Public domain', null, 3),
    ('Cheddar (Käse)', 'England', 'Benannt nach einem Dorf in Somerset.',
     'Somerset-Cheddar.jpg', 'J.P.Lon',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 4),
    ('Emmentaler', 'Schweiz', 'Bekannt für seine großen Löcher.',
     'Emmental (fromage) 01.jpg', 'Coyau',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 5),
    ('Halloumi', 'Zypern', 'Bleibt beim Braten in Form.',
     'Halloumi-1.jpg', 'Rainer Zenz',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 6),
    ('Danablu', 'Dänemark', 'In den 1920er Jahren entwickelt.',
     'Danish Blue cheese.jpg', 'No machine-readable author provided. Brookie assumed (based on copyright claims).',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 7),
    ('Oscypek', 'Polen', 'Geräucherter Schafskäse aus der Tatra.',
     'Oscypki.jpg', 'Pawel Swiegoda (Paberu)',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 8),
    ('Harzer Käse', 'Deutschland', 'Sauermilchkäse, fast ohne Fett.',
     'Harzer Käse 13 WikiCheese Lokal K.jpg', 'Elke Wetzig',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Graviera', 'Griechenland', 'Hartkäse, meist aus Schafmilch.',
     'Graviera Kritis Kraounaki Rethymnou.jpg', 'Catlemur',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 10)
),
fakes (label, explanation, position) as (
    values
    ('Italien', 'Der Gorgonzola käme von dort, und der fehlt auf dem Brett.', 11),
    ('Österreich', 'Der Tiroler Bergkäse steht nicht in dieser Liste.', 12)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;

with new_quiz as (
    insert into quizzes (subject_id, slug, title, description, difficulty,
                         source_title, source_url, category_kind, origin)
    select s.id, 'bild-instrumente-herkunft', 'Instrumente im Bild',
           'Woher stammt das Instrument?', 'medium'::difficulty,
           'Musikinstrument', 'https://de.wikipedia.org/wiki/Musikinstrument', 'image', 'seed'
      from subjects s
     where s.slug = 'musik'
       and not exists (select 1 from quizzes q where q.slug = 'bild-instrumente-herkunft')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Sitar', 'Indien', 'Mitschwingende Resonanzsaiten geben den Klang.',
     'Sitar3.jpg', 'Sathyadeep',
     'Public domain', null, 1),
    ('Balalaika', 'Russland', 'Dreieckiger Korpus, drei Saiten.',
     'Balalajka, druga polovina 20. veka.jpg', 'Miloš Jurišić',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Dudelsack', 'Schottland', 'Der Luftsack hält den Ton beim Atmen.',
     'Scotland Independence March, 28 March 2026 (32).jpg', 'Lucas Kendall',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Alphorn', 'Schweiz', 'Bis zu vier Meter lang, ohne Ventile.',
     'Alphorn player in Wallis.jpg', 'Hans Hillewaert',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Koto', 'Japan', 'Wölbbrettzither mit verschiebbaren Stegen.',
     'Koto by Fumie Hihara 2016.png', 'Jean-Pierre Dalbéra',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 5),
    ('Erhu', 'China', 'Zweisaitige Fiedel, Bogen zwischen den Saiten.',
     'Erhu.png', 'LDHan',
     'Public domain', null, 6),
    ('Ukulele', 'Hawaii', 'Aus einem portugiesischen Instrument entstanden.',
     'Ukulele4.png', 'Kollektives Schreiben',
     'Public domain', null, 7),
    ('Djembe', 'Mali', 'Bechertrommel, mit bloßen Händen gespielt.',
     'Djembé''s.jpg', 'Edwin1971 at Dutch Wikipedia',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 8),
    ('Panflöte', 'Peru', 'Rohre unterschiedlicher Länge nebeneinander.',
     'Pan flute Gibonus FP-12.jpg', 'ПростоУчастник',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 9),
    ('Charango', 'Bolivien', 'Kleine Laute, früher aus einem Gürteltierpanzer.',
     'Bolivian charango 001.jpg', 'Photo taken by Villanueva',
     'Public domain', null, 10),
    ('Nyckelharpa', 'Schweden', 'Tasten verkürzen die Saiten statt der Finger.',
     '2022-07-28 Nyckelharpa-Spielerin in der Schillerstraße Ecke Rosenstraße in Hannover.jpg', 'Bernd Schwabe in Hannover',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11)
),
fakes (label, explanation, position) as (
    values
    ('Australien', 'Das Didgeridoo käme von dort, und das fehlt auf dem Brett.', 12),
    ('Argentinien', 'Das Bandoneon steht nicht in dieser Liste.', 13)
),
new_categories as (
    insert into categories (quiz_id, label, position, image_file,
                            image_credit, image_licence, image_licence_url)
    select q.id, p.label, p.position, p.image_file,
           p.image_credit, p.image_licence, p.image_licence_url
      from new_quiz q cross join pairs p
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;
