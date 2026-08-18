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
    select s.id, 'bild-entwickler-zwei', 'Gesichter hinter den Reihen',
           'Wofür ist die abgebildete Person bekannt?', 'hard'::difficulty,
           'Spieleentwickler', 'https://de.wikipedia.org/wiki/Spieleentwickler', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-entwickler-zwei')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Todd Howard', 'Skyrim', 'Er leitet die Rollenspiele von Bethesda.',
     'Todd Howard, SXSW 2024.jpg', 'Vbrunophotog',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 1),
    ('Peter Molyneux', 'Populous', 'Bekannt für große Versprechen vor jedem Start.',
     'Peter Molyneux 20080927 Festival du jeu video 02.jpg', 'Georges Seguin (Okki)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Richard Garriott', 'Ultima', 'Er nennt sich selbst Lord British.',
     'Richard garriott july 2008.jpg', 'NASA',
     'Public domain', null, 3),
    ('Warren Spector', 'Deus Ex', 'Ein Spiel, drei Lösungswege für jede Tür.',
     'Warren Spector GDC 2023 (cropped).jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 4),
    ('Cliff Bleszinski', 'Gears of War', 'Deckung als Kern des Shooters.',
     'CIiffyB.jpg', 'Michael Tianhui ("Thomas") Li',
     'Public domain', null, 5),
    ('Jane Jensen', 'Gabriel Knight', 'Adventures mit ernster Handlung.',
     'Jane Jensen Adventure Game Fan Fair Tacoma Washington July 2024.jpg', 'Guywelch2000',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 6),
    ('Brenda Romero', 'Wizardry', 'Sie arbeitete schon an den frühen Teilen mit.',
     'Brenda Romero at 2015 IGF Awards-GDCA (16102142533) (cropped).jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 7),
    ('Rand Miller', 'Myst', 'Er spielt auch selbst eine Rolle darin.',
     'RandMiller2014.jpg', 'Jeff Hitchcock',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 8),
    ('Sam Houser', 'Grand Theft Auto', 'Mitgründer von Rockstar Games.',
     'Sam Houser at Rockstar Games.png', 'Anthony Parello',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Fumito Ueda', 'Shadow of the Colossus', 'Sechzehn Bosse, sonst fast nichts.',
     'Fumito Ueda.jpg', 'kandinski',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 10),
    ('David Cage', 'Heavy Rain', 'Erzählung mit Entscheidungen statt Kämpfen.',
     'David Cage 20080927 Festival du jeu video 05.jpg', 'Georges Seguin (Okki)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 11),
    ('Jonathan Blow', 'Braid', 'Es machte kleine Spiele wieder ernst.',
     'Jonathan Blow Gamelab 2018 crop 1.jpg', 'Gamelab Congreso Videojuegos',
     'Public domain', null, 12)
),
fakes (label, explanation, position) as (
    values
    ('Metal Gear', 'Das wäre Hideo Kojima, und der ist hier nicht abgebildet.', 13),
    ('Minecraft', 'Markus Persson steht auf diesem Brett nicht.', 14)
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
    select s.id, 'bild-komponisten', 'Wer schrieb die Musik?',
           'Für welches Spiel oder welche Reihe schrieb die Person die Musik?', 'hard'::difficulty,
           'Videospielmusik', 'https://de.wikipedia.org/wiki/Videospielmusik', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-komponisten')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Kōji Kondō', 'Super Mario', 'Die bekannteste Melodie der Branche.',
     'Koji Kondo E3 2006 (3x4 cropped).jpg', 'Vincent Diamante from Los Angeles, CA, USA',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 1),
    ('Nobuo Uematsu', 'Final Fantasy', 'Seine Stücke füllen Konzertsäle.',
     'Nobuo Uematsu.jpg', 'Christoffer Blomqvist from There is no city on this Island, Finland',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 2),
    ('Yoko Shimomura', 'Kingdom Hearts', 'Zuvor bei Capcom und Square.',
     'Game Developers Choice Awards 2024 - Yoko Shimomura - 03 (cropped).jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 3),
    ('Jesper Kyd', 'Hitman', 'Chorgesang zum lautlosen Töten.',
     'JesperKyd.jpg', 'Miguel Mendez',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 4),
    ('Austin Wintory', 'Journey', 'Erste Spielmusik mit Grammy-Nominierung.',
     'Austin Wintory, GDC 2024 (D3 KT2 3297) (cropped 2).jpg', 'Official GDC',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 5),
    ('Martin O’Donnell', 'Halo', 'Mönchsgesang über Streichern.',
     'Martin O’Donnell at Snooker German Masters (DerHexer) 2013-01-30 12.jpg', 'DerHexer, Wikimedia Commons',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Yuzo Koshiro', 'Streets of Rage', 'Clubmusik auf dem Mega Drive.',
     'Yūzō Koshiro.jpg', 'The original uploader was PyroGamer at English Wikipedia.',
     'Attribution', null, 7),
    ('Jeremy Soule', 'The Elder Scrolls', 'Hörner und weite Chöre.',
     'JeremySouleByAE2011.jpg', 'Artistry Entertainment and Julian Soule',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 8),
    ('Christopher Tin', 'Civilization IV', 'Das Titellied gewann einen Grammy.',
     'ChristopherTin 2016Shoot 06.jpg', 'CTW-PR',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Junichi Masuda', 'Pokémon', 'Er komponierte und leitete zugleich.',
     'JunichiMasudaJI2 (cropped).jpg', 'Joi Ito',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 10),
    ('Hans Zimmer', 'Call of Duty', 'Der Filmkomponist schrieb ein Hauptthema.',
     'Hans-Zimmer-profile.jpg', 'ColliderVideo. Uploader cropped.',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 11),
    ('Olivier Deriviere', 'A Plague Tale', 'Streicher und Chor für das Mittelalter.',
     'Olivier Derivière GDC 2025.jpg', 'Alecto Chardon',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 12)
),
fakes (label, explanation, position) as (
    values
    ('Doom', 'Mick Gordon schrieb sie, und der fehlt auf diesem Brett.', 13),
    ('Minecraft', 'Die Musik stammt von C418, der hier nicht abgebildet ist.', 14)
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
    select s.id, 'bild-hauptsitze', 'Hauptsitze der Branche',
           'In welcher Stadt steht das Gebäude?', 'hard'::difficulty,
           'Spieleentwickler', 'https://de.wikipedia.org/wiki/Spieleentwickler', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-hauptsitze')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Nintendo', 'Kyoto', 'Die Firma sitzt seit ihrer Gründung dort.',
     'Headquarters of Nintendo Co., Ltd.jpg', 'Tokumeigakarinoaoshima',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 1),
    ('Capcom', 'Osaka', 'Resident Evil und Street Fighter entstehen hier.',
     'CAPCOM本社.jpg', 'Tokumeigakarinoaoshima',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 2),
    ('Square Enix', 'Tokio', 'Im Stadtteil Shinjuku.',
     'Square Enix HQ (Shinjuku Eastside Square).jpg', 'Wirtz',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 3),
    ('Blizzard Entertainment', 'Irvine', 'Vor dem Eingang steht ein Orc aus Bronze.',
     'BlizzardIrvine.jpg', 'KennethHan',
     'Public domain', null, 4),
    ('Electronic Arts', 'Redwood City', 'Zwischen San Francisco und San José.',
     'EA Building RedwoodShores.JPG', 'Eliot Lash',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 5),
    ('Epic Games', 'Cary', 'In North Carolina, nicht im Silicon Valley.',
     'Epic Games office.jpg', 'Sergey Galyonkin from Berlin, Germany',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 6),
    ('Riot Games', 'Los Angeles', 'An der Olympic Boulevard.',
     '12333 Olympic Boulevard.jpg', 'Coolcaesar',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 7),
    ('Valve', 'Bellevue', 'Gegenüber von Seattle.',
     'Valve Lobby 2016.jpg', 'Tim Eulitz',
     'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0', 8),
    ('Ubisoft', 'Paris', 'Der Sitz liegt in Saint-Mandé am Stadtrand.',
     'Bureaux Floresco - Saint-Mandé (FR94) - 2022-05-13 - 2.jpg', 'Chabe01',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Mojang Studios', 'Stockholm', 'Minecraft entstand hier.',
     'Mojang Studios 2022.jpg', 'TheBrickGraphic',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 10)
),
fakes (label, explanation, position) as (
    values
    ('Montreal', 'Ubisofts größtes Studio steht dort, gefragt ist hier der Hauptsitz.', 11),
    ('Seattle', 'Kein Gebäude auf diesem Brett steht dort.', 12)
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
    select s.id, 'bild-kuriose-hardware', 'Kuriose Hardware',
           'Was ist das Besondere an dem Gerät?', 'hard'::difficulty,
           'Spielkonsole', 'https://de.wikipedia.org/wiki/Spielkonsole', 'image', 'seed'
      from subjects s
     where s.slug = 'videospiele'
       and not exists (select 1 from quizzes q where q.slug = 'bild-kuriose-hardware')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Virtual Boy', 'Rot-schwarzes 3D', 'Nach kurzer Zeit wieder eingestellt.',
     'Virtual-Boy-Set.png', 'Evan-Amos',
     'Public domain', null, 1),
    ('Power Glove', 'Handschuh fürs NES', 'Berühmter als er funktionierte.',
     'NES-Power-Glove.jpg', 'Evan-Amos',
     'Public domain', null, 2),
    ('Sega 32X', 'Aufsatz auf die Konsole', 'Er steckte im Modulschacht.',
     'Sega-Genesis-32X-01.jpg', 'Evan-Amos',
     'Public domain', null, 3),
    ('Ouya', 'Aus dem Crowdfunding', 'Millionen gesammelt, kaum Spiele.',
     'OUYA-Console-set-h.png', '.mw-parser-output .hlist dl,.mw-parser-output .hlist ol,.mw-parser-output .hlist ul{margin:0;padding:0}.mw-parser-output .hlist dd,.mw-parser-output .hlist dt,.mw-parser-output .hlist li{margin:0;display:inline}.mw-parser-output .hlist.inline,.mw-parser-output .hlist.inline dl,.mw-parser-output .hlist.inline ol,.mw-parser-output .hlist.inline ul,.mw-parser-output .hlist dl dl,.mw-parser-output .hlist dl ol,.mw-parser-output .hlist dl ul,.mw-parser-output .hlist ol dl,.mw-parser-output .hlist ol ol,.mw-parser-output .hlist ol ul,.mw-parser-output .hlist ul dl,.mw-parser-output .hlist ul ol,.mw-parser-output .hlist ul ul{display:inline}.mw-parser-output .hlist .mw-empty-li,.mw-parser-output .hlist .mw-empty-elt{display:none}.mw-parser-output .hlist dt:after{content:": "}.mw-parser-output .hlist dd:after,.mw-parser-output .hlist li:after{content:" · ";font-weight:bold}.mw-parser-output .hlist dd:last-child:after,.mw-parser-output .hlist dt:last-child:after,.mw-parser-output .hlist li:last-child:after{content:none}.mw-parser-output .hlist dd dd:first-child:before,.mw-parser-output .hlist dd dt:first-child:before,.mw-parser-output .hlist dd li:first-child:before,.mw-parser-output .hlist dt dd:first-child:before,.mw-parser-output .hlist dt dt:first-child:before,.mw-parser-output .hlist dt li:first-child:before,.mw-parser-output .hlist li dd:first-child:before,.mw-parser-output .hlist li dt:first-child:before,.mw-parser-output .hlist li li:first-child:before{content:" (";font-weight:normal}.mw-parser-output .hlist dd dd:last-child:after,.mw-parser-output .hlist dd dt:last-child:after,.mw-parser-output .hlist dd li:last-child:after,.mw-parser-output .hlist dt dd:last-child:after,.mw-parser-output .hlist dt dt:last-child:after,.mw-parser-output .hlist dt li:last-child:after,.mw-parser-output .hlist li dd:last-child:after,.mw-parser-output .hlist li dt:last-child:after,.mw-parser-output .hlist li li:last-child:after{content:")";font-weight:normal}.mw-parser-output .hlist ol{counter-reset:listitem}.mw-parser-output .hlist olli{counter-increment:listitem}.mw-parser-output .hlist olli:before{content:" "counter(listitem)"\a0 "}.mw-parser-output .hlist dd olli:first-child:before,.mw-parser-output .hlist dt olli:first-child:before,.mw-parser-output .hlist li olli:first-child:before{content:" ("counter(listitem)"\a0 "} Original: Evan-Amos Derivative work: Alhadis',
     'Public domain', null, 4),
    ('Nintendo Labo', 'Zubehör aus Pappe', 'Zusammengefaltet und dann gespielt.',
     'Nintendo Labo construction.jpeg', 'Tinh tế Photo',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 5),
    ('Paddle (Eingabegerät)', 'Drehregler statt Stick', 'Für Schläger, die nur seitwärts fahren.',
     'Atari-2600-Paddle-Controller-FR.jpg', 'Evan-Amos',
     'Public domain', null, 6),
    ('Steam Controller', 'Zwei Tastfelder', 'Ersatz für die Maus im Wohnzimmer.',
     'Steam Controller (25483452893).png', 'Kenming Wang from Taipei, Taiwan',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 7),
    ('DualSense', 'Widerstand in den Triggern', 'Der Bogen spannt sich spürbar.',
     'Playstation DualSense Controller.png', 'Alex Cochrane',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Sega Master System', 'Mit 3D-Brille erhältlich', 'Lange vor der heutigen VR-Welle.',
     'Sega-Master-System-Set.png', 'Evan-Amos',
     'Public domain', null, 9),
    ('Wii', 'Steuerung durch Schwingen', 'Sie holte Leute an die Konsole, die nie spielten.',
     'Wii-console.jpg', 'Evan-Amos',
     'Public domain', null, 10),
    ('PlayStation 3', 'Cell-Prozessor', 'Berüchtigt schwer zu programmieren.',
     'PS3Versions.png', 'PS3-Fat-Console-Vert.png: Evan-Amos PS3-Slim-Console-Vert.png: Evan-Amos',
     'Public domain', null, 11)
),
fakes (label, explanation, position) as (
    values
    ('Bildschirm zum Aufklappen', 'Der Nintendo DS wäre das, und der fehlt auf dem Brett.', 12),
    ('Spiele auf Kassette laden', 'Kein Gerät in dieser Liste tut das.', 13)
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
