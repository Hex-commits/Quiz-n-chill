-- Neues Fachgebiet: Unnützes Wissen.
--
-- Anders als die zehn Gebiete davor steht hier nicht ein Stoffgebiet im
-- Mittelpunkt, sondern eine Sorte Frage: nachprüfbare Kleinigkeiten, die man
-- nirgends braucht und trotzdem behält. Die Bretter greifen deshalb quer durch
-- Biologie, Sprache, Technik und Alltag.
--
-- seed.sql führt diese Zeile nicht mit -- das Gebiet entstand nach der Datei.
-- Vor den unnuetzes-wissen-*.sql-Dateien anwenden, sonst findet deren Join auf
-- subjects nichts und es wird still nichts eingefügt.
--
-- Wie die Fragendateien re-runnable: ein zweiter Lauf tut nichts.

insert into subjects (slug, name, description, position)
select 'unnuetzes-wissen', 'Unnützes Wissen',
       'Kleinigkeiten, die niemand braucht und alle behalten.', 11
 where not exists (select 1 from subjects s where s.slug = 'unnuetzes-wissen');
