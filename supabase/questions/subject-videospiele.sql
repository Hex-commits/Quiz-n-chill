-- Neues Fachgebiet: Videospiele.
--
-- seed.sql führt dieselbe Zeile mit, greift aber nur bei `supabase db reset`.
-- Diese Datei ist für Datenbanken, die schon laufen: sie muss vor den
-- videospiele-*.sql-Dateien angewandt werden, sonst findet deren Join auf
-- subjects nichts und es wird still nichts eingefügt.
--
-- Wie die Fragendateien re-runnable: ein zweiter Lauf tut nichts.

insert into subjects (slug, name, description, position)
select 'videospiele', 'Videospiele', 'Konsolen, Spielereihen und Studios.', 10
 where not exists (select 1 from subjects s where s.slug = 'videospiele');
