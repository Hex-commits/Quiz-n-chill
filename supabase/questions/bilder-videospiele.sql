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
    select s.id, 'bild-konsolen-hersteller', 'Konsolen im Bild',
           'Von welchem Hersteller stammt das Gerät?', 'easy'::difficulty,
           'Spielkonsole', 'https://de.wikipedia.org/wiki/Spielkonsole', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-konsolen-hersteller')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Nintendo GameCube', 'Nintendo', 'Der Würfel mit dem Tragegriff.',
     'GameCube-Set.jpg', 'Evan-Amos',
     'Public domain', null, 1),
    ('PlayStation 4', 'Sony', '2013 erschienen, über hundert Millionen Mal verkauft.',
     'PS4-Console-wDS4.jpg', 'Evan-Amos',
     'Public domain', null, 2),
    ('Xbox One', 'Microsoft', 'Zum Start noch mit Kinect im Bündel.',
     'Microsoft-Xbox-One-Console-Set-wKinect.jpg', 'Evan-Amos',
     'Public domain', null, 3),
    ('Dreamcast', 'Sega', 'Die letzte Konsole des Hauses.',
     'Dreamcast-Console-Set.jpg', 'Evan-Amos',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Neo Geo', 'SNK', 'Spielhallentechnik fürs Wohnzimmer, zum Preis eines Kleinwagens.',
     'Neo-Geo-AES-FL.jpg', 'Evan-Amos',
     'Public domain', null, 5),
    ('CD-i', 'Philips', 'Als Multimediagerät gedacht, nicht als Spielkonsole.',
     'CD-i-910-Console-Set.png', 'Evan-Amos',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('PC Engine', 'NEC', 'In Japan sehr erfolgreich, in Europa kaum bekannt.',
     'PC Engine.jpg', 'Muband',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Nokia N-Gage', 'Nokia', 'Handy und Handheld in einem Gehäuse.',
     'Nokia-NGage-LL.jpg', 'Evan-Amos',
     'Public domain', null, 8),
    ('Steam Deck', 'Valve', 'Ein Handheld, auf dem PC-Spiele laufen.',
     'Steam Deck (front).png', 'Liam Dawe/GamingOnLinux, PNG version by VulcanSphere',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Commodore 64', 'Commodore', 'Heimcomputer und Spielgerät zugleich.',
     'Commodore-64-Computer-FL.jpg', 'Evan-Amos',
     'Public domain', null, 10)
),
fakes (label, explanation, position) as (
    values
    ('Atari', 'Kein Gerät auf diesem Brett stammt von dieser Firma.', 11),
    ('Amstrad', 'Auch von dieser Firma ist hier nichts abgebildet.', 12)
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
    select s.id, 'bild-konsolen-jahrgaenge', 'Konsolen & ihre Jahrgänge',
           'Wann kam das abgebildete Gerät heraus?', 'hard'::difficulty,
           'Spielkonsole', 'https://de.wikipedia.org/wiki/Spielkonsole', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-konsolen-jahrgaenge')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Magnavox Odyssey', '1972', 'Die erste Heimkonsole, noch ganz ohne Ton.',
     'Magnavox-Odyssey-Console-Set.png', 'Evan-Amos',
     'Public domain', null, 1),
    ('Atari 2600', '1977', 'Sie machte austauschbare Module zum Standard.',
     'Atari-2600-Light-Sixer-FL.jpg', 'Evan-Amos',
     'Public domain', null, 2),
    ('Nintendo Entertainment System', '1983', 'In Japan als Famicom gestartet.',
     'Wikipedia NES PAL.jpg', 'JCD1981NL',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 3),
    ('Mega Drive', '1988', 'In Nordamerika unter dem Namen Genesis.',
     'Sega-Genesis-NA-Mk2-Console-Set.png', 'Evan-Amos',
     'Public domain', null, 4),
    ('Super Nintendo Entertainment System', '1990', 'Erst in Japan, zwei Jahre später in Europa.',
     'SNES-Mod1-Console-Set.jpg', 'Evan-Amos',
     'Public domain', null, 5),
    ('Atari Jaguar', '1993', 'Warb mit 64 Bit und floppte trotzdem.',
     'Atari-Jaguar-Console-Set.jpg', 'Evan-Amos',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('Sega Saturn', '1994', 'Gegen die erste PlayStation ohne Chance.',
     'Sega-Saturn-Console-Set-Mk1.png', 'Evan-Amos',
     'Public domain', null, 7),
    ('Nintendo 64', '1996', 'Vier Controller-Anschlüsse ab Werk.',
     'Nintendo-64-wController-L.jpg', 'Evan-Amos',
     'Public domain', null, 8),
    ('PlayStation 2', '2000', 'Die meistverkaufte Konsole überhaupt.',
     'PS2-Versions.jpg', 'Evan-Amos',
     'Public domain', null, 9),
    ('Xbox 360', '2005', 'Ein Jahr vor der PlayStation 3 im Handel.',
     'Xbox-360-Consoles-Infobox.png', 'Evan-Amos',
     'Public domain', null, 10),
    ('Wii U', '2012', 'Der Name kostete sie den Erfolg.',
     'Wii U Console and Gamepad.png', 'Takimata (edited by:Tokyoship)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 11),
    ('PlayStation 5', '2020', 'Start mitten in der Pandemie.',
     'PlayStation 5 and DualSense with transparent background.png', 'Soberian (this retouched file)Osh33m (original photograph)',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 12)
),
fakes (label, explanation, position) as (
    values
    ('1994 in Europa', 'Die Saturn kam in Japan 1994, in Europa erst 1995.', 13),
    ('2017', 'Die Switch erschien damals, und die fehlt auf diesem Brett.', 14)
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
    select s.id, 'bild-handhelds', 'Handhelds im Bild',
           'Was war das Besondere an dem Gerät?', 'medium'::difficulty,
           'Handheld-Konsole', 'https://de.wikipedia.org/wiki/Handheld-Konsole', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-handhelds')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Game Boy Color', 'Farbe im alten Gehäuse', 'Die alten Module liefen weiter.',
     'Game-Boy-FL.jpg', 'Evan-Amos',
     'Public domain', null, 1),
    ('Game Boy Advance', 'Querformat mit Schultertasten', 'Erstmals Tasten an den Kanten.',
     'Nintendo-Game-Boy-Advance-Purple-FL.jpg', 'Evan-Amos',
     'Public domain', null, 2),
    ('Nintendo DS', 'Zwei Bildschirme', 'Der untere wurde mit einem Stift bedient.',
     'Nintendo-DS-Fat-Blue.jpg', 'Evan-Amos',
     'Public domain', null, 3),
    ('Nintendo 3DS', '3D ohne Brille', 'Der Effekt ließ sich abschalten.',
     'Nintendo-3DS-AquaOpen.jpg', 'Evan-Amos',
     'Public domain', null, 4),
    ('PlayStation Portable', 'Filme auf UMD', 'Auch als mobiler Medienspieler gedacht.',
     'Psp-1000.jpg', 'Evan-Amos',
     'Public domain', null, 5),
    ('PlayStation Vita', 'Feld auf der Rückseite', 'Berührungseingabe von hinten.',
     'PlayStation-Vita-1101-FL.jpg', 'Evan-Amos',
     'Public domain', null, 6),
    ('Game Gear', 'Sechs Batterien nötig', 'Farbe kostete Laufzeit.',
     'Game-Gear-Handheld.jpg', 'Evan-Amos',
     'Public domain', null, 7),
    ('Game & Watch', 'Uhr und ein Spiel', 'Ein Gerät, ein einziger Titel.',
     'Game-and-watch-ball.png', 'masatsu',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 8),
    ('Steam Deck', 'PC-Spiele unterwegs', 'Mit einem Linux-System im Inneren.',
     'Steam Deck (front).png', 'Liam Dawe/GamingOnLinux, PNG version by VulcanSphere',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Atari Lynx', 'Umdrehbar für Linkshänder', 'Das Bild kippte per Knopfdruck mit.',
     'Atari-Lynx-I-Handheld.png', 'Evan-Amos',
     'Public domain', null, 10),
    ('WonderSwan', 'Kaum außerhalb Japans', 'Entworfen vom Erfinder des Game Boy.',
     'WonderSwan-Black-Left.jpg', 'Evan-Amos',
     'Public domain', null, 11),
    ('Tamagotchi', 'Haustier statt Spielfigur', 'Es wollte auch nachts gefüttert werden.',
     'Tamagotchi 0124 ubt.jpeg', 'Tomasz Sienicki [user: tsca, mail: tomasz.sienicki at gmail.com]',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 12)
),
fakes (label, explanation, position) as (
    values
    ('Vier Grüntöne auf dem Schirm', 'Das wäre der erste Game Boy, und der fehlt hier.', 13),
    ('Spiele über Funk empfangen', 'Kein Gerät auf diesem Brett konnte das.', 14)
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
    select s.id, 'bild-heimcomputer', 'Heimcomputer der Achtziger',
           'Wofür ist das Gerät bekannt?', 'hard'::difficulty,
           'Heimcomputer', 'https://de.wikipedia.org/wiki/Heimcomputer', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-heimcomputer')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Commodore 64', 'Meistverkaufter Heimcomputer', 'Sein Klangchip prägte eine ganze Musikszene.',
     'Commodore-64-Computer-FL.jpg', 'Evan-Amos',
     'Public domain', null, 1),
    ('Amiga 500', 'Vier Tonkanäle serienmäßig', 'Der Standard der Demoszene.',
     'Amiga500 system.jpg', 'Bill Bertram',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 2),
    ('Atari ST', 'MIDI-Anschluss ab Werk', 'Deshalb in Tonstudios beliebt.',
     'Atari 1040STf.jpg', '© Bill Bertram, 2006',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 3),
    ('Sinclair ZX Spectrum', 'Gummitasten', 'In Großbritannien allgegenwärtig.',
     'ZXSpectrum48k.jpg', 'Bill Bertram',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 4),
    ('Apple II', 'Farbe schon 1977', 'Einer der ersten Serienrechner überhaupt.',
     'Apple II IMG 4212.jpg', 'Rama &amp; Musée Bolo',
     'CC BY-SA 2.0 fr', 'https://creativecommons.org/licenses/by-sa/2.0/fr/deed.en', 5),
    ('Schneider CPC', 'Monitor im Bündel', 'In Deutschland unter anderem Namen verkauft.',
     'Amstrad CPC464.jpg', 'Bill Bertram',
     'CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5', 6),
    ('MSX', 'Standard vieler Hersteller', 'Metal Gear erschien zuerst hier.',
     'Sony HitBit HB-10P (White Background).jpg', 'Sony_hitbit_10p.jpg: Doppelgangland derivative work: User:Ubcule',
     'Public domain', null, 7),
    ('Commodore VC 20', 'Vorgänger des C64', 'Der erste Rechner mit einer Million Stück.',
     'CBMVIC20P8.jpg', 'Cbmeeks / processed by Pixel8',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 8),
    ('Atari 800', 'Steckmodule wie Konsolen', 'Spiele einfach einstecken.',
     'Atari-800-Computer-FL.jpg', 'Evan-Amos',
     'Public domain', null, 9),
    ('Acorn Archimedes', 'Früher ARM-Prozessor', 'Dieselbe Familie steckt heute in Handys.',
     'Acorn Archimedes A3000 Computer Main Unit.jpg', 'Binarysequence',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 10),
    ('IBM Personal Computer', 'Vorbild aller PCs', 'Nachbauten machten die Bauform zum Standard.',
     'IBM PC-IMG 7271 (transparent).png', 'Rama &amp; Musée Bolo',
     'CC BY-SA 2.0 fr', 'https://creativecommons.org/licenses/by-sa/2.0/fr/deed.en', 11)
),
fakes (label, explanation, position) as (
    values
    ('Erster Rechner mit Maus im Bündel', 'Das war der Macintosh, und der fehlt auf dem Brett.', 12),
    ('Nur mit Kassettenlaufwerk erhältlich', 'Auf kein Gerät in dieser Liste trifft das zu.', 13)
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
    select s.id, 'bild-menschen', 'Gesichter der Branche',
           'Wofür steht die abgebildete Person?', 'hard'::difficulty,
           'Spieleentwickler', 'https://de.wikipedia.org/wiki/Spieleentwickler', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-menschen')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Ralph Baer', 'Magnavox Odyssey', 'Er gilt als Vater der Heimkonsole.',
     'Ralph-Baer.jpg', 'Michael Schilling',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 1),
    ('Nolan Bushnell', 'Atari', 'Er gründete die Firma und die Branche gleich mit.',
     'Nolan Bushnell 2013.jpg', 'Tech Cocktail',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 2),
    ('Shigeru Miyamoto', 'Super Mario', 'Von ihm stammen auch Zelda und Donkey Kong.',
     'Shigeru Miyamoto 20150610 (cropped).jpg', 'Minister''s Secretariat Personnel Division',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 3),
    ('Satoru Iwata', 'Nintendo', 'Programmierer, der zum Firmenchef wurde.',
     'Satoru Iwata - Game Developers Conference 2011 - Day 2 (1).jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 4),
    ('Ken Kutaragi', 'PlayStation', 'Er setzte die Konsole gegen interne Widerstände durch.',
     'Ken kutaragi.jpg', 'Joi Ito',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 5),
    ('Gabe Newell', 'Valve', 'Zuvor arbeitete er bei Microsoft.',
     'Gabe Newell GDC 2010 (cropped 2).jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 6),
    ('Hideo Kojima', 'Metal Gear', 'Bekannt für filmreife Zwischensequenzen.',
     'Hideo Kojima 2025 SXSW (cropped).jpg', 'Kolby Ari',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 7),
    ('Roberta Williams', 'King’s Quest', 'Mitbegründerin von Sierra.',
     'Roberta Williams Adventure Game Fan Fair Tacoma Washington July 2024 (cropped).jpg', 'Guywelch2000',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 8),
    ('Tim Schafer', 'Grim Fandango', 'Er schrieb auch Full Throttle.',
     'Tim 120A354-crop (cropped).jpg', 'Thespaff',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Amy Hennig', 'Uncharted', 'Sie schrieb die ersten drei Teile.',
     'Amy hennig gdca 2019 cropped.jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 10),
    ('Masahiro Sakurai', 'Super Smash Bros.', 'Er erfand auch Kirby.',
     'Masahiro Sakurai 2021.jpg', 'Katsuhiro Harada',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 11),
    ('Yu Suzuki', 'OutRun', 'Sega-Legende, später Shenmue.',
     'Yu Suzuki - Game Developers Conference 2011 - Day 3.jpg', 'Yu Suzuki - Game Developers Conference 2011 - Day 3 (2).jpg: Official GDC derivative work: Masem',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 12)
),
fakes (label, explanation, position) as (
    values
    ('Tetris', 'Alexei Paschitnow steht dafür, und der ist hier nicht abgebildet.', 13),
    ('Minecraft', 'Markus Persson fehlt auf diesem Brett.', 14)
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
    select s.id, 'bild-zubehoer', 'Zubehör im Bild',
           'Zu welchem System gehört das Gerät?', 'medium'::difficulty,
           'Gamecontroller', 'https://de.wikipedia.org/wiki/Gamecontroller', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-zubehoer')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Wii-Fernbedienung', 'Wii', 'Gehalten wie eine Fernbedienung, geschwungen wie ein Schläger.',
     'Wii Remote Image.jpg', 'Greyson Orlando',
     'Public domain', null, 1),
    ('Joy-Con', 'Nintendo Switch', 'Zwei Hälften, die sich abnehmen lassen.',
     'Nintendo Switch Joy-Con Controllers.png', 'Owen1962',
     'Public domain', null, 2),
    ('DualShock', 'PlayStation', 'Zwei Sticks und Vibration als Standard.',
     'PSX-DualShock-Controller.jpg', 'Evan-Amos',
     'Public domain', null, 3),
    ('Kinect', 'Xbox 360', 'Eine Kamera erkennt den ganzen Körper.',
     'Xbox-360-Kinect-Standalone.png', 'Evan-Amos',
     'Public domain', null, 4),
    ('Oculus Rift', 'Meta', 'Aus einer Kickstarter-Kampagne entstanden.',
     'Oculus-Rift-CV1-Headset-Front with transparent background.png', 'Evan-Amos',
     'Public domain', null, 5),
    ('HTC Vive', 'HTC', 'Zusammen mit Valve entwickelt.',
     'HTC Vive Headset Front View.jpg', 'CULLEN STEBER',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Valve Index', 'Valve', 'Die Controller erfassen einzelne Finger.',
     'Air Force officer using Valve Index.jpg', 'Airman 1st Class Robyn Hunsinger',
     'Public domain', null, 7),
    ('PlayStation VR', 'PlayStation 4', 'VR-Brille für eine Konsole statt für den PC.',
     'Sony-PlayStation-4-PSVR-Headset-Mk1-FL.jpg', 'Evan-Amos',
     'Public domain', null, 8),
    ('Joystick', 'Atari 2600', 'Ein Stick, ein Knopf, mehr nicht.',
     'Atari-2600-Joystick.jpg', 'Evan-Amos',
     'Public domain', null, 9),
    ('Computermaus', 'PC', 'Sie macht das genaue Zielen erst möglich.',
     'ComputerMouseCloseup3.jpg', 'Raysonho @ Open Grid Scheduler / Grid Engine',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 10)
),
fakes (label, explanation, position) as (
    values
    ('Sega Mega Drive', 'Kein Gerät auf diesem Brett gehört dazu.', 11),
    ('Nintendo 64', 'Auch das Rumble Pak fehlt in dieser Liste.', 12)
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
    select s.id, 'bild-arcade', 'Automaten im Bild',
           'Worum geht es an diesem Automaten?', 'medium'::difficulty,
           'Arcade-Automat', 'https://de.wikipedia.org/wiki/Arcade-Automat', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-arcade')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Pong', 'Zwei Balken, ein Ball', 'Der Automat, mit dem die Branche begann.',
     'Signed Pong Cabinet.jpg', 'Chris Rand',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 1),
    ('Space Invaders', 'Aliens in Reihen', 'Sie werden schneller, je weniger übrig sind.',
     'Space Invaders - Midway''s.JPG', 'Jordiferrer',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Pac-Man', 'Punkte im Labyrinth', 'Verfolgt von vier Geistern.',
     'Pac-Man gameplay (1x pixel-perfect recreation).png', 'Bandai Namco Entertainment America',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 3),
    ('Galaga', 'Raumschiffe in Formation', 'Gefangene Schiffe lassen sich zurückholen.',
     'Galaga.jpg', 'George Hotelling from Plymouth, MI, United States',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 4),
    ('Frogger', 'Frosch überquert Straßen', 'Danach wartet noch der Fluss.',
     'Vglfrogger.jpg', 'Ian Muttoo from Mississauga, Canada',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 5),
    ('Street Fighter II', 'Zweikampf von der Seite', 'Spezialattacken über Tastenfolgen.',
     'Street Fighter II arcade-20061027.jpg', 'Jonathan Sloan from Burnaby, Canada',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 6),
    ('Tetris', 'Fallende Steine stapeln', 'Volle Reihen verschwinden.',
     'Emacs Tetris vector based detail.svg', 'For the implementation of Tetris for Emacs, Glynn Clements. For the original screenshot of the game, User:Eldred. For the SVG version, FedericoMP',
     'GPL', 'http://www.gnu.org/licenses/gpl.html', 7),
    ('Sega Rally Championship', 'Rallye im Automaten', 'Mit Lenkrad und Schaltung im Gehäuse.',
     'Sega Rally Twin - Japanese Cabinet.jpg', 'Brettv8',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Dance Dance Revolution', 'Tanzen auf Pfeilen', 'Gespielt wird mit den Füßen.',
     'Dance Dance Revolution North American arcade machine 3.jpg', 'Poiuyt Man at English Wikipedia',
     'Public domain', null, 9),
    ('Arcade-Automat', 'Gehäuse mit Münzschlitz', 'Eine Partie kostet eine Münze.',
     'Fliperama.jpg', 'Andrevruas',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 10)
),
fakes (label, explanation, position) as (
    values
    ('Fässern auf Gerüsten ausweichen', 'Das wäre Donkey Kong, und der fehlt auf dem Brett.', 11),
    ('Auf einem Motorrad durch Kurven', 'Kein Automat in dieser Liste ist das.', 12)
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
