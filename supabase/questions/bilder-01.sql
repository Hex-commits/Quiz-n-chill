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
    select s.id, 'bild-wahrzeichen-laender', 'Wahrzeichen der Welt',
           'In welchem Land steht dieses Bauwerk?', 'medium'::difficulty,
           'Wahrzeichen', 'https://de.wikipedia.org/wiki/Wahrzeichen', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-wahrzeichen-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Eiffelturm', 'Frankreich', 'Für die Weltausstellung 1889 gebaut.',
     'Tour Eiffel Wikimedia Commons.jpg', 'Benh LIEU SONG',
     'Public domain', null, 1),
    ('Kolosseum', 'Italien', 'Amphitheater für rund 50000 Zuschauer.',
     'Colosseo 2020.jpg', 'FeaturedPics',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 2),
    ('Freiheitsstatue', 'USA', 'Ein Geschenk Frankreichs zum Unabhängigkeitsjubiläum.',
     'Statue of Liberty and a sightseeing boat, Liberty Island, New York.jpg', 'Christian David',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Taj Mahal', 'Indien', 'Grabmal aus weißem Marmor in Agra.',
     'Taj Mahal, Agra, India edit3.jpg', 'Taj_Mahal,_Agra,_India_edit2.jpg: Yann; edited by King of Hearts derivative work: Jbarta (talk)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Sagrada Família', 'Spanien', 'Seit 1882 im Bau, Entwurf von Gaudí.',
     'SF maig 2026.jpg', 'Canaan',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Big Ben', 'Vereinigtes Königreich', 'Eigentlich der Name der Glocke, nicht des Turms.',
     'Elizabeth Tower and the north front of the Palace of Westminster, London.jpg', 'Christian David',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Brandenburger Tor', 'Deutschland', 'Nach dem Vorbild der Athener Propyläen.',
     'Brandenburger Tor morgens.jpg', 'Thomas Wolf, www.foto-tw.de',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Atomium', 'Belgien', 'Eine Eisenzelle, milliardenfach vergrößert.',
     'Laeken Atomium 06.jpg', 'Zairon',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Chinesische Mauer', 'China', 'Über Jahrhunderte in Abschnitten errichtet.',
     'The Great Wall of China at Jinshanling-edit.jpg', 'Severin.stalder',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Opernhaus von Sydney', 'Australien', 'Die Schalendächer wirken wie geblähte Segel.',
     'Sydney Opera House Sails.jpg', 'No machine-readable author provided. Roybb95~commonswiki assumed (based on copyright claims).',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 10),
    ('Machu Picchu', 'Peru', 'Inkastadt auf 2400 Metern Höhe.',
     'Machu Picchu, 2023 (012).jpg', 'Draceane',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11),
    ('Burj Khalifa', 'Vereinigte Arabische Emirate', 'Mit 828 Metern das höchste Bauwerk der Welt.',
     'Dubai skyline 2015 (crop).jpg', 'Tim.Reckmann',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 12),
    ('Petra (Stadt)', 'Jordanien', 'In roten Sandstein geschlagene Nabatäerstadt.',
     'The Treasury, Petra, Jordan5.jpg', 'Diego Delso',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 13)
),
fakes (label, explanation, position) as (
    values
    ('Ägypten', 'Die Pyramiden von Gizeh stünden dort, und die fehlen auf dem Brett.', 14),
    ('Griechenland', 'Die Akropolis steht nicht in dieser Liste.', 15)
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
    select s.id, 'bild-bruecken-laender', 'Brücken der Welt',
           'In welchem Land steht die Brücke?', 'hard'::difficulty,
           'Brücke', 'https://de.wikipedia.org/wiki/Br%C3%BCcke', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-bruecken-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Golden Gate Bridge', 'USA', 'Ihr Rot heißt offiziell International Orange.',
     'GoldenGateBridge-001.jpg', 'Rich Niewiroski Jr.',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 1),
    ('Tower Bridge', 'Vereinigtes Königreich', 'Eine Klappbrücke, keine Hängebrücke.',
     'London - London Tower Bridge - 140806 171049.jpg', 'Barcex',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Karlsbrücke', 'Tschechien', 'Über die Moldau, gesäumt von Heiligenfiguren.',
     'Prague 07-2016 View from Petrinska Tower img2.jpg', 'A.Savin',
     'FAL', 'http://artlibre.org/licence/lal/en', 3),
    ('Rialtobrücke', 'Italien', 'Älteste der Brücken über den Canal Grande.',
     'Rialto 2025 4.jpg', 'kallerna',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 4),
    ('Kapellbrücke', 'Schweiz', 'Überdachte Holzbrücke mit Wasserturm.',
     'Luzern asv2022-10 Kapellbrücke img3.jpg', 'A.Savin',
     'FAL', 'http://artlibre.org/licence/lal/en', 5),
    ('Erasmusbrücke', 'Niederlande', 'Wegen ihrer Form der Schwan genannt.',
     'Rotterdam erasmusbrug.jpg', 'F.Eveleens',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 6),
    ('Vasco-da-Gama-Brücke', 'Portugal', 'Über zwölf Kilometer lang, über den Tejo.',
     'Vasco da Gama Bridge 03.JPG', 'Osvaldo Gago (OsvaldoGago)',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 7),
    ('Sydney Harbour Bridge', 'Australien', 'Wegen ihrer Form Kleiderbügel genannt.',
     'SydneyHarbourBridge1 gobeirne.jpg', 'Photograph by Greg O''Beirne',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 8),
    ('Akashi-Kaikyō-Brücke', 'Japan', 'Ein Erdbeben verlängerte sie während des Baus.',
     'Akashi Bridge.JPG', 'Tysto',
     'Public domain', null, 9),
    ('Viadukt von Millau', 'Frankreich', 'Höher als der Eiffelturm.',
     '00 0237 Millau - Département Aveyron.jpg', 'W. Bulach',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 10),
    ('Stari Most', 'Bosnien und Herzegowina', '1993 zerstört, 2004 wieder aufgebaut.',
     'Mostar Old Town Panorama 2007.jpg', 'Ramirez',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11),
    ('Chengyang-Brücke', 'China', 'Holzbrücke mit Pagodentürmen, ohne Nägel gebaut.',
     '程阳永济桥3 (cropped).jpg', '三猎',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 12)
),
fakes (label, explanation, position) as (
    values
    ('Dänemark', 'Die Öresundbrücke stünde dort, und die fehlt auf dem Brett.', 13),
    ('Türkei', 'Die Bosporus-Brücke steht nicht in dieser Liste.', 14)
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
    select s.id, 'bild-gemaelde-maler', 'Gemälde & ihre Maler',
           'Wer hat dieses Bild gemalt?', 'hard'::difficulty,
           'Malerei', 'https://de.wikipedia.org/wiki/Malerei', 'image', 'seed'
      from subjects s
     where s.slug = 'kunst-kultur'
       and not exists (select 1 from quizzes q where q.slug = 'bild-gemaelde-maler')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Mona Lisa', 'Leonardo da Vinci', 'Um 1503 entstanden, heute im Louvre.',
     'Mona Lisa, by Leonardo da Vinci, from C2RMF natural color.jpg', 'Leonardo da Vinci',
     'Public domain', null, 1),
    ('Die Nachtwache', 'Rembrandt', 'Eine Schützengilde, dramatisch beleuchtet.',
     'La ronda de noche, por Rembrandt van Rijn.jpg', 'Rembrandt',
     'Public domain', null, 2),
    ('Der Schrei', 'Edvard Munch', 'Es existieren mehrere Fassungen.',
     'Edvard Munch, 1893, The Scream, oil, tempera and pastel on cardboard, 91 x 73 cm, National Gallery of Norway.jpg', 'Edvard Munch',
     'Public domain', null, 3),
    ('Sternennacht', 'Vincent van Gogh', 'Gemalt aus dem Fenster einer Heilanstalt.',
     'Van Gogh - Starry Night - Google Art Project.jpg', 'Vincent van Gogh',
     'Public domain', null, 4),
    ('Der Kuss (Klimt)', 'Gustav Klimt', 'Höhepunkt seiner Goldenen Periode.',
     'The Kiss - Gustav Klimt - Google Cultural Institute.jpg', 'Gustav Klimt',
     'Public domain', null, 5),
    ('Die Geburt der Venus (Botticelli)', 'Sandro Botticelli', 'Venus steht auf einer Muschel.',
     'Sandro Botticelli - La nascita di Venere - Google Art Project - edited.jpg', 'Sandro Botticelli',
     'Public domain', null, 6),
    ('Das Mädchen mit dem Perlenohrgehänge', 'Jan Vermeer', 'Ein Blick über die Schulter.',
     '1665 Girl with a Pearl Earring.jpg', 'Johannes Vermeer',
     'Public domain', null, 7),
    ('Der Wanderer über dem Nebelmeer', 'Caspar David Friedrich', 'Rückenfigur über der Wolkendecke.',
     'Friedrich, Caspar David - Wanderer über dem Nebelmeer.jpg', 'Caspar David Friedrich',
     'Public domain', null, 8),
    ('Die Erschaffung Adams', 'Michelangelo', 'Deckenfresko der Sixtinischen Kapelle.',
     'The Creation of Adam perspective fix.jpg', 'Michelangelo',
     'Public domain', null, 9),
    ('Impression, Sonnenaufgang', 'Claude Monet', 'Gab dem Impressionismus den Namen.',
     'Monet - Impression, Sunrise.jpg', 'Claude Monet',
     'Public domain', null, 10),
    ('Die Schule von Athen', 'Raffael', 'Platon und Aristoteles in der Bildmitte.',
     '"The School of Athens" by Raffaello Sanzio da Urbino.jpg', 'Raphael',
     'Public domain', null, 11),
    ('Die Freiheit führt das Volk', 'Eugène Delacroix', 'Sinnbild der Julirevolution von 1830.',
     'La Liberté guidant le peuple - Eugène Delacroix - Musée du Louvre Peintures RF 129 - après restauration 2024.jpg', 'Eugène Delacroix',
     'Public domain', null, 12)
),
fakes (label, explanation, position) as (
    values
    ('Salvador Dalí', 'Die zerfließenden Uhren wären das Bild dazu, und die fehlen hier.', 13),
    ('Pablo Picasso', 'Guernica steht nicht auf diesem Brett.', 14)
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
    select s.id, 'bild-hunderassen-herkunft', 'Hunderassen & Herkunft',
           'Aus welchem Land stammt die Rasse?', 'hard'::difficulty,
           'Hunderassen', 'https://de.wikipedia.org/wiki/Hunderassen', 'image', 'seed'
      from subjects s
     where s.slug = 'naturwissenschaft'
       and not exists (select 1 from quizzes q where q.slug = 'bild-hunderassen-herkunft')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Dackel', 'Deutschland', 'Als Erdhund für den Bau gezüchtet.',
     'MiniDachshund1 wb.jpg', 'Ellen Levy Finch (Elf)',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 1),
    ('Chihuahua (Hunderasse)', 'Mexiko', 'Kleinste Hunderasse der Welt.',
     'Chihuahuas- Holly, Nina, Doralice.jpg', 'Caterinarufo',
     'Public domain', null, 2),
    ('Akita (Hunderasse)', 'Japan', 'Hachiko war ein Vertreter dieser Rasse.',
     'Akita inu criado por Tsutsui Kennel.jpg', 'TsutsuiKennel',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 3),
    ('Siberian Husky', 'Russland', 'Als Schlittenhund in Sibirien gezüchtet.',
     'Siberian Husky - Mika.jpg', 'ShonMichaeli',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 4),
    ('Labrador Retriever', 'Kanada', 'Ursprünglich Helfer der Fischer in Neufundland.',
     'Yellow Labrador Retriever 2.jpg', 'SixtyWeb',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 5),
    ('Berner Sennenhund', 'Schweiz', 'Früher Zughund auf Bauernhöfen.',
     'Bouviers Bernois Ganjo.jpg', 'Ganjo http://fr.wikipedia.org/wiki/Utilisateur:Ganjo',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 6),
    ('Pudel', 'Frankreich', 'Ursprünglich ein Wasserapportierhund.',
     'Miniature Poodle (Hungary).jpg', 'UszkarFoto92',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 7),
    ('Chow-Chow', 'China', 'Auffällig ist die blauschwarze Zunge.',
     '01 Chow Chow.jpg', 'Prayitno/more than 2.5 millions views: thank you!',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 8),
    ('Afghanischer Windhund', 'Afghanistan', 'Langes Fell schützt im Gebirge.',
     'Afghan Hound in Tallinn.JPG', 'Томасина',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Basenji', 'Demokratische Republik Kongo', 'Bellt nicht, sondern jodelt.',
     'Басенджи (Basenji) 02.jpg', 'Novoklimov',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 10),
    ('Border Collie', 'Schottland', 'Treibt Schafe durch bloßen Blick.',
     'Argentine border collie.jpg', 'Horacio Cambeiro',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11)
),
fakes (label, explanation, position) as (
    values
    ('Ungarn', 'Der Puli käme von dort, und die Rasse fehlt auf dem Brett.', 12),
    ('Australien', 'Der Australian Shepherd steht nicht in dieser Liste.', 13)
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
    select s.id, 'bild-berge-laender', 'Berge im Bild',
           'In welchem Land steht der Berg?', 'medium'::difficulty,
           'Berg', 'https://de.wikipedia.org/wiki/Berg', 'image', 'seed'
      from subjects s
     where s.slug = 'geografie'
       and not exists (select 1 from quizzes q where q.slug = 'bild-berge-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Matterhorn', 'Schweiz', 'Pyramide über Zermatt, 1865 erstbestiegen.',
     'Cervino cloud.jpg', 'Gianluca Miscione',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 1),
    ('Kilimanjaro', 'Tansania', 'Höchster Berg Afrikas.',
     'Mt. Kilimanjaro 12.2006.jpg', 'Chris 73 / Wikimedia Commons',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Denali', 'USA', 'Höchster Berg Nordamerikas, in Alaska.',
     'Wonder Lake and Denali.jpg', 'Denali National Park and Preserve',
     'Public domain', null, 3),
    ('Uluru', 'Australien', 'Heiliger Berg der Anangu.',
     'Sunset at Uluru on July 30, 2005.jpg', 'Thomas Schoch',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 4),
    ('Mount Everest', 'Nepal', '8849 Meter, höchster Berg der Erde.',
     'Mount Everest as seen from Drukair2 PLW edit.jpg', 'Mount_Everest_as_seen_from_Drukair2.jpg: shrimpo1967 derivative work: Papa Lima Whiskey 2 (talk)',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 5),
    ('Aconcagua', 'Argentinien', 'Höchster Berg außerhalb Asiens.',
     'Aconcagua2016.jpg', 'Bjørn Christian Tørrissen',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Zugspitze', 'Deutschland', 'Höchster Berg des Landes, 2962 Meter.',
     'Zugspitzmassiv-von-Almkopf-2024.jpg', 'Tuxyso',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 7),
    ('Großglockner', 'Österreich', 'Höchster Berg des Landes, mit der Pasterze.',
     'Großglockner1.jpg', 'DennisPeeters',
     'Public domain', null, 8),
    ('Olymp', 'Griechenland', 'Sitz der Götter der antiken Mythologie.',
     'Mt Olympus aerial 2.jpg', 'kallerna',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 9),
    ('Ben Nevis', 'Schottland', 'Höchster Berg der Britischen Inseln.',
     'Ben nevis.jpg', 'Loek037 at Dutch Wikipedia',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 10),
    ('Fudschi', 'Japan', 'Vulkankegel und Wahrzeichen des Landes.',
     'Kodaki fuji frm shojinko refurb.jpg', '名古屋太郎, (edited by Hannes_24)',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 11),
    ('Tafelberg (Südafrika)', 'Südafrika', 'Flache Bergkulisse über Kapstadt.',
     'Table Mountain DanieVDM.jpg', 'Danie van der Merwe from Cape Town, South Africa',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 12),
    ('Cotopaxi', 'Ecuador', 'Einer der höchsten aktiven Vulkane der Erde.',
     'Vólcan Cotopaxi.jpg', 'camilogaleano.com',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 13)
),
fakes (label, explanation, position) as (
    values
    ('Italien', 'Der Gran Sasso stünde dort, und der fehlt auf dem Brett.', 14),
    ('Chile', 'Der Ojos del Salado steht nicht in dieser Liste.', 15)
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
    select s.id, 'bild-gerichte-laender', 'Gerichte im Bild',
           'Aus welchem Land stammt das Gericht?', 'medium'::difficulty,
           'Nationalgericht', 'https://de.wikipedia.org/wiki/Nationalgericht', 'image', 'seed'
      from subjects s
     where s.slug = 'essen-trinken'
       and not exists (select 1 from quizzes q where q.slug = 'bild-gerichte-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Sushi', 'Japan', 'Gesäuerter Reis, meist mit rohem Fisch.',
     'Various sushi, beautiful October night at midnight.jpg', 'Yumi Kimura',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 1),
    ('Paella', 'Spanien', 'Reisgericht aus Valencia, in flacher Pfanne.',
     'Cooking a paella.jpg', 'Jebulon',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 2),
    ('Pizza Margherita', 'Italien', '1889 nach der Königin benannt.',
     'Eq it-na pizza-margherita sep2005 sml.jpg', 'Valerio Capello at English Wikipedia',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 3),
    ('Wiener Schnitzel', 'Österreich', 'Die Bezeichnung ist rechtlich geschützt.',
     '2022-12-29 Wiener Schnitzel im Hotel Kaiserin Elisabeth.jpg', 'Burkhard Mücke',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 4),
    ('Moussaka', 'Griechenland', 'Auflauf aus Auberginen und Hackfleisch.',
     'Mousakas.jpg', 'Fotograf: Dieter Mueller (dino1948) Kamera: de:Nikon 885',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 5),
    ('Taco', 'Mexiko', 'Gefaltete Maistortilla mit Füllung.',
     '001 Tacos de carnitas, carne asada y al pastor.jpg', 'Larry Miller',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 6),
    ('Borschtsch', 'Ukraine', 'Rote Bete gibt die Farbe.',
     'Borscht with bread.jpg', 'Juerg Vollmer from Zürich, Schweiz',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 7),
    ('Currywurst', 'Deutschland', 'Angeblich 1949 in Berlin erfunden.',
     'Currywurst-1.jpg', 'Rainer Z ...',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 8),
    ('Poutine', 'Kanada', 'Pommes mit Bratensauce und Käsebruch.',
     'Poutine.JPG', 'Jonathunder',
     'GFDL 1.2', 'http://www.gnu.org/licenses/old-licenses/fdl-1.2.html', 9),
    ('Ceviche', 'Peru', 'Roher Fisch, in Limettensaft mariniert.',
     'Ceviche del Perú.jpg', 'No machine-readable author provided. Manuel González Olaechea assumed (based on copyright claims).',
     'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0', 10),
    ('Bibimbap', 'Südkorea', 'Alles wird vor dem Essen verrührt.',
     'Korean.food-Bibimbap-02.jpg', 'abex (a flickr user)',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 11),
    ('Phở', 'Vietnam', 'Nudelsuppe mit lange gezogener Brühe.',
     'Món ăn Đông Hà, Tết 2022 (phở Lý Quốc sư ở công viên Cọ Dầu) (2).jpg', 'Phương Huy',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 12),
    ('Käsefondue', 'Schweiz', 'Wer das Brot verliert, gibt eine Runde aus.',
     'Full cheese fondue set - in Switzerland.JPG', 'EquatorialSky at English Wikipedia',
     'Public domain', null, 13)
),
fakes (label, explanation, position) as (
    values
    ('Thailand', 'Pad Thai käme von dort, und das Gericht fehlt auf dem Brett.', 14),
    ('Indien', 'Das Curry steht nicht in dieser Liste.', 15)
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
    select s.id, 'bild-schloesser-laender', 'Schlösser & Burgen im Bild',
           'In welchem Land steht der Bau?', 'medium'::difficulty,
           'Schloss (Architektur)', 'https://de.wikipedia.org/wiki/Schloss_%28Architektur%29', 'image', 'seed'
      from subjects s
     where s.slug = 'geschichte'
       and not exists (select 1 from quizzes q where q.slug = 'bild-schloesser-laender')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Schloss Neuschwanstein', 'Deutschland', 'Ludwig II. ließ es ab 1869 bauen.',
     'Schloss Neuschwanstein 2013.jpg', 'Thomas Wolf, www.foto-tw.de',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 1),
    ('Schloss Chambord', 'Frankreich', 'Renaissanceschloss mit doppelter Wendeltreppe.',
     'France Loir-et-Cher Chambord Chateau 03.jpg', 'No machine-readable author provided. Calips assumed (based on copyright claims).',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 2),
    ('Alhambra', 'Spanien', 'Rote Festung der Nasriden über Granada.',
     'Alhambra detail.jpg', 'Jebulon',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 3),
    ('Windsor Castle', 'Vereinigtes Königreich', 'Älteste durchgehend bewohnte Burg der Welt.',
     'Windsor Castle at Sunset - Nov 2006.jpg', 'Diliff',
     'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5', 4),
    ('Prager Burg', 'Tschechien', 'Größte geschlossene Burganlage der Welt.',
     'Castillo de Praga, Praga, República Checa, 2022-07-02, DD 209.jpg', 'Diego Delso',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 5),
    ('Moskauer Kreml', 'Russland', 'Festung im Herzen der Hauptstadt.',
     'Moscow 05-2012 Kremlin 22.jpg', 'A.Savin',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 6),
    ('Himeji-jō', 'Japan', 'Weiße Burg, die Erdbeben und Bomben überstand.',
     'Himeji castle in may 2015.jpg', 'Nikos Kitsakis',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 7),
    ('Törzburg', 'Rumänien', 'Wird als Draculaschloss vermarktet.',
     'Bran Roumanie.jpg', 'Myrabella',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 8),
    ('Schloss Kronborg', 'Dänemark', 'Schauplatz von Shakespeares Hamlet.',
     'KronborgCastle HCS.jpg', 'H.C. Steensen',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 9),
    ('Marienburg (Ordensburg)', 'Polen', 'Größte Backsteinburg der Welt.',
     'Panorama of Malbork Castle, part 4.jpg', 'DerHexer; derivate work: Carschten',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 10),
    ('Palácio Nacional da Pena', 'Portugal', 'Bunter Romantikbau über Sintra.',
     'Palácio Nacional da Pena por Rodrigo Tetsuo Argenton (39).jpg', 'Wilhelm Ludwig von Eschwege',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11),
    ('Schloss Schönbrunn', 'Österreich', 'Sommerresidenz der Habsburger.',
     'Schloss Schönbrunn Wien 2014 (Zuschnitt 2).jpg', 'Thomas Wolf, www.foto-tw.de',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 12),
    ('Schloss Chillon', 'Schweiz', 'Am Ufer des Genfersees gelegen.',
     'Castle of Chillon N.jpg', 'Zacharie Grossen',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 13)
),
fakes (label, explanation, position) as (
    values
    ('Ungarn', 'Die Budaer Burg stünde dort, und die fehlt auf dem Brett.', 14),
    ('Schweden', 'Schloss Drottningholm steht nicht in dieser Liste.', 15)
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
    select s.id, 'bild-flugzeuge-hersteller', 'Flugzeuge im Bild',
           'Von welchem Hersteller stammt das Flugzeug?', 'hard'::difficulty,
           'Flugzeug', 'https://de.wikipedia.org/wiki/Flugzeug', 'image', 'seed'
      from subjects s
     where s.slug = 'technik'
       and not exists (select 1 from quizzes q where q.slug = 'bild-flugzeuge-hersteller')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Boeing 747', 'Boeing', 'Der Jumbo mit dem markanten Buckel.',
     'B-747 Iberia.jpg', 'Iberia Airlines',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 1),
    ('Airbus A380', 'Airbus', 'Zwei durchgehende Passagierdecks.',
     'A6-EDY A380 Emirates 31 jan 2013 jfk (8442269364) (cropped).jpg', 'Maarten Visser from Capelle aan den IJssel, Nederland',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 2),
    ('Aérospatiale-BAC Concorde', 'Aérospatiale und BAC', 'Überschallverkehr bis 2003.',
     'British Airways Concorde G-BOAC 03.jpg', 'Eduard Marmet',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 3),
    ('Supermarine Spitfire', 'Supermarine', 'Elliptische Tragflächen als Erkennungszeichen.',
     'Ray Flying Legends 2005-1.jpg', 'The original uploader was Bryan Fury75 at French Wikipedia.',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 4),
    ('Junkers Ju 52/3m', 'Junkers', 'Wellblechrumpf mit drei Motoren.',
     'Ju52-Kress.JPG', 'Markus Kress. Hermannk at de.wikipedia',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 5),
    ('Douglas DC-3', 'Douglas', 'Machte den Linienflug wirtschaftlich.',
     'Douglas DC-3, SE-CFP.jpg', 'Towpilot',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 6),
    ('Mikojan-Gurewitsch MiG-21', 'Mikojan-Gurewitsch', 'Meistgebautes Überschallflugzeug.',
     'Czechoslovak Air Force Mikoyan-Gurevich MiG-21R Lofting-4.jpg', 'Chris Lofting',
     'GFDL 1.2', 'http://www.gnu.org/licenses/old-licenses/fdl-1.2.html', 7),
    ('Antonow An-225', 'Antonow', 'Sechs Triebwerke, größtes Flugzeug der Welt.',
     'Antonov An-225 Beltyukov-1.jpg', 'mark steven',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 8),
    ('Cessna 172', 'Cessna', 'Meistgebautes Flugzeug der Geschichte.',
     'Cessna 172S Skyhawk ‘G-JMKE’ (45077563364).jpg', 'Alan Wilson from Stilton, Peterborough, Cambs, UK',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 9),
    ('Lockheed SR-71', 'Lockheed', 'Flog schneller als Mach drei.',
     'SR-71A in flight near Beale AFB 1988.JPEG', 'TSgt. Michael Haggerty, USAF',
     'Public domain', null, 10),
    ('Saab 39 Gripen', 'Saab', 'Für Starts von Landstraßen ausgelegt.',
     'Saab JAS-39 Gripen of the Czech Air Force taking off from AFB Čáslav.jpg', 'Milan Nykodym from Kutna Hora, Czech Republic',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 11),
    ('Embraer E-Jets', 'Embraer', 'Regionaljets aus Brasilien.',
     'EI-RDB Embraer 175 Alitalia BCN.jpg', 'Bene Riobó',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 12)
),
fakes (label, explanation, position) as (
    values
    ('Tupolew', 'Die Tu-144 käme von dort, und die fehlt auf diesem Brett.', 13),
    ('Bombardier', 'Der CRJ steht nicht in dieser Liste.', 14)
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
    select s.id, 'bild-tiere-kontinente', 'Tiere & ihre Heimat',
           'Wo lebt das Tier in freier Wildbahn?', 'medium'::difficulty,
           'Tier', 'https://de.wikipedia.org/wiki/Tier', 'image', 'seed'
      from subjects s
     where s.slug = 'naturwissenschaft'
       and not exists (select 1 from quizzes q where q.slug = 'bild-tiere-kontinente')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Rotes Riesenkänguru', 'Australien', 'Größtes lebendes Beuteltier.',
     'Red kangaroo - melbourne zoo.jpg', 'fir0002 flagstaffotos [at] gmail.com Canon 20D + Canon 70-200mm f/2.8 L',
     'GFDL 1.2', 'http://www.gnu.org/licenses/old-licenses/fdl-1.2.html', 1),
    ('Großer Panda', 'China', 'Frisst fast ausschließlich Bambus.',
     'Giant Panda 2004-03-2.jpg', 'Jeff Kubina',
     'Public domain', null, 2),
    ('Amerikanischer Bison', 'Nordamerika', 'Bestand einst fast ausgerottet.',
     'American bison k5680-1.jpg', 'Jack Dykinga',
     'Public domain', null, 3),
    ('Königspinguin', 'Antarktis', 'Brütet das Ei auf den Füßen aus.',
     'King Penguins on Saunders Island (5586254113).jpg', 'Liam Quinn from Canada',
     'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0', 4),
    ('Zweifingerfaultier', 'Südamerika', 'Verbringt fast das ganze Leben hängend.',
     'Choloepus didactylus 2 - Buffalo Zoo.jpg', 'Dave Pape',
     'Public domain', null, 5),
    ('Bengaltiger', 'Indien', 'Größte lebende Katzenart.',
     'Bengal tiger in Sanjay Dubri Tiger Reserve December 2024 by Tisha Mukherjee 11.jpg', 'Tisha Mukherjee',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 6),
    ('Eisbär', 'Arktis', 'Unter dem weißen Fell ist die Haut schwarz.',
     'Polar Bear - Alaska (cropped).jpg', 'Alan Wilson',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 7),
    ('Erdmännchen', 'Südliches Afrika', 'Wache steht aufrecht am Bau.',
     'Meerkat (Suricata suricatta).jpg', 'Hans Hillewaert',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Komodowaran', 'Indonesien', 'Größte lebende Echse.',
     'Komodo dragon Varanus komodoensis Ragunan Zoo 2.JPG', 'Midori',
     'CC BY-SA 3.0', 'http://creativecommons.org/licenses/by-sa/3.0/', 9),
    ('Kiwis', 'Neuseeland', 'Flugunfähiger Vogel mit langem Schnabel.',
     'TeTuatahianui.jpg', 'Maungatautari Ecological Island Trust',
     'Public domain', null, 10),
    ('Braunbär', 'Europa', 'In den Karpaten lebt der größte Bestand.',
     'Kamchatka Brown Bear near Dvuhyurtochnoe on 2015-07-23.jpg', 'Robert F. Tobler',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11)
),
fakes (label, explanation, position) as (
    values
    ('Madagaskar', 'Die Lemuren lebten dort, und die fehlen auf diesem Brett.', 12),
    ('Japan', 'Kein Tier in dieser Liste lebt dort in freier Wildbahn.', 13)
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
    select s.id, 'bild-bauwerke-baustile', 'Bauwerke & Baustile',
           'In welchem Baustil wurde der Bau errichtet?', 'hard'::difficulty,
           'Baustil', 'https://de.wikipedia.org/wiki/Baustil', 'image', 'seed'
      from subjects s
     where s.slug = 'kunst-kultur'
       and not exists (select 1 from quizzes q where q.slug = 'bild-bauwerke-baustile')
    returning id
),
pairs (label, answer, explanation, image_file, image_credit,
       image_licence, image_licence_url, position) as (
    values
    ('Kölner Dom', 'Gotik', 'Spitzbögen und Strebewerk, begonnen 1248.',
     'Kölner Dom von Osten.jpg', 'Thomas Wolf, www.foto-tw.de',
     'CC BY-SA 3.0 de', 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en', 1),
    ('Hagia Sophia', 'Byzantinische Architektur', 'Riesenkuppel über Pendentifs.',
     'Hagia Sophia Mars 2013.jpg', 'Arild Vågen',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 2),
    ('Schloss Versailles', 'Barock', 'Prunk und strenge Symmetrie.',
     'Vue aérienne du domaine de Versailles par ToucanWings - Creative Commons By Sa 3.0 - 083.jpg', 'ToucanWings',
     'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0', 3),
    ('Petersdom', 'Renaissance', 'Kuppel nach dem Entwurf Michelangelos.',
     'Basilica di San Pietro in Vaticano September 2015-1a.jpg', 'Alvesgaspar',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 4),
    ('Alhambra', 'Maurische Architektur', 'Stuckornamente und Muqarnas.',
     'Alhambra detail.jpg', 'Jebulon',
     'CC0', 'http://creativecommons.org/publicdomain/zero/1.0/deed.en', 5),
    ('Chrysler Building', 'Art déco', 'Spitze aus rostfreiem Stahl.',
     'Chrysler Building by David Shankbone Retouched.jpg', 'w:User:Overand derivative work: Overand (talk)',
     'Public domain', null, 6),
    ('Basilius-Kathedrale', 'Russische Architektur', 'Bunte Zwiebeltürme am Roten Platz.',
     '00 0568 Saint Basil''s Cathedral - Moscow.jpg', 'W. Bulach',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 7),
    ('Pantheon (Rom)', 'Römische Antike', 'Größte unbewehrte Betonkuppel der Welt.',
     'Pantheon (Rome) - Right side and front.jpg', 'NikonZ7II',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 8),
    ('Guggenheim-Museum Bilbao', 'Dekonstruktivismus', 'Titanhülle ohne gerade Flächen.',
     'Museo Guggenheim, Bilbao (31273245344).jpg', 'Naotake Murayama',
     'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0', 9),
    ('Wieskirche', 'Rokoko', 'Verspielte Stuckdekoration im Innenraum.',
     'Wieskirche boenisch okt 2003.jpg', 'Bönisch',
     'CC BY-SA 2.0 de', 'https://creativecommons.org/licenses/by-sa/2.0/de/deed.en', 10),
    ('Chichén Itzá', 'Maya-Architektur', 'Die Stufenpyramide des Kukulcán.',
     'Chichen Itza 3.jpg', 'Daniel Schwen',
     'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', 11)
),
fakes (label, explanation, position) as (
    values
    ('Bauhaus', 'Kein Bau auf diesem Brett steht in diesem Stil.', 12),
    ('Romanik', 'Der Dom zu Speyer wäre das Beispiel, und der fehlt hier.', 13)
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
