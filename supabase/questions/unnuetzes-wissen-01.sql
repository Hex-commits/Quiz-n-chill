-- Unnützes Wissen. Zwanzig Fragen quer durch alle Gebiete.
--
-- Das Gebiet ist über die Sorte Frage bestimmt, nicht über den Stoff: kleine
-- nachprüfbare Tatsachen, die man nirgends braucht und trotzdem behält. Darum
-- stehen hier Biologie, Sprache, Technik und Alltag nebeneinander.
--
-- Zwei Dinge waren beim Schreiben die Mühe wert. Erstens: nur Belegbares. Zu
-- diesem Gebiet gehören ganze Sammlungen hübscher Behauptungen, die niemand
-- nachgeprüft hat -- Kängurus, die "ich verstehe nicht" heißen sollen, die
-- Mauer, die man vom Mond aus sehe. Zweitens gibt es hier ein eigenes Brett für
-- genau diese Sorte Satz, `alltagsirrtuemer`, und dort ist das Falsche die
-- Kategorie und die Richtigstellung die Antwort.
--
-- Vorher anwenden: supabase/questions/subject-unnuetzes-wissen.sql.
--
-- Shape, rules and how to apply: see supabase/questions/batch-01.sql.

with spec (subject_slug, slug, title, description, difficulty,
           source_title, source_url, pairs, fakes) as (
    values

    ('unnuetzes-wissen', 'wortherkunft-alltag', 'Wörter & ihre Herkunft',
     'Was bedeutet das Wort ursprünglich?',
     'hard', 'Etymologie', 'https://de.wikipedia.org/wiki/Etymologie',
     '[["Orange", "Apfel aus China", "Die Apfelsine trägt die Herkunft noch im Namen."],
       ["Schokolade", "Bitteres Wasser", "Aus dem Nahuatl-Wort xocolatl."],
       ["Alkohol", "Feines Pulver", "Vom arabischen al-kuhl, einem Schminkpulver."],
       ["Zucker", "Kies", "Über das Arabische aus dem Sanskrit sharkara."],
       ["Tomate", "Schwellfrucht", "Aus dem Nahuatl-Wort tomatl."],
       ["Vanille", "Kleine Schote", "Verkleinerung des spanischen vaina."],
       ["Salat", "Gesalzenes", "Vom lateinischen sal für Salz."],
       ["Muskel", "Mäuschen", "Vom lateinischen musculus."],
       ["Pupille", "Püppchen", "Man sieht sich selbst klein darin gespiegelt."],
       ["Ketchup", "Fischsauce", "Über das Malaiische aus einem chinesischen Dialekt."],
       ["Kollege", "Mitgewählter", "Vom lateinischen collega."]]'::jsonb,
     '[["Runde Scheibe", "Auf kein Wort auf diesem Brett geht das zurück."],
       ["Heißer Stein", "Kein Begriff in dieser Liste kommt daher."]]'::jsonb),

    ('unnuetzes-wissen', 'tierische-kuriositaeten', 'Tiere & ihre Eigenheiten',
     'Welches Tier ist gemeint?',
     'medium', 'Tier', 'https://de.wikipedia.org/wiki/Tier',
     '[["Krake", "Hat drei Herzen", "Zwei für die Kiemen, eines für den Körper."],
       ["Blauwal", "Die Zunge wiegt so viel wie ein Elefant", "Das größte Tier, das je gelebt hat."],
       ["Delfin", "Schläft mit einer Gehirnhälfte", "Die andere hält das Auftauchen in Gang."],
       ["Seestern", "Stülpt den Magen nach außen", "Verdaut wird außerhalb des Körpers."],
       ["Giraffe", "Sieben Halswirbel wie der Mensch", "Sie sind nur deutlich länger."],
       ["Kolibri", "Fliegt auch rückwärts", "Als einziger Vogel."],
       ["Chamäleon", "Bewegt beide Augen unabhängig", "Es sieht zwei Bilder zugleich."],
       ["Koala", "Hat Fingerabdrücke wie ein Mensch", "Sie sind kaum zu unterscheiden."],
       ["Seepferdchen", "Das Männchen trägt die Jungen aus", "In einer Bauchtasche."],
       ["Flamingo", "Wird erst durch das Futter rosa", "Ohne Krebstiere bleibt er blass."],
       ["Fledermaus", "Einziges Säugetier mit echtem Flug", "Alle anderen gleiten nur."]]'::jsonb,
     '[["Sieht die Welt nur schwarz-weiß", "Das sagt man Hunden nach, und die fehlen auf diesem Brett."],
       ["Kann den Schwanz abwerfen", "Das kann die Eidechse, und die steht hier nicht."]]'::jsonb),

    ('unnuetzes-wissen', 'koerper-in-zahlen', 'Der Körper in Zahlen',
     'Welche Zahl gehört dazu?',
     'medium', 'Menschlicher Körper',
     'https://de.wikipedia.org/wiki/Menschlicher_K%C3%B6rper',
     '[["Herzschläge am Tag", "Rund 100.000", "Bei einem Ruhepuls um die siebzig."],
       ["Schwerstes Organ", "Die Haut", "Rund zehn Kilogramm bei einem Erwachsenen."],
       ["Knochen eines Erwachsenen", "206", "Ein Neugeborenes hat deutlich mehr."],
       ["Länge aller Blutgefäße", "Rund 100.000 Kilometer", "Zweieinhalbmal um die Erde."],
       ["Geschwindigkeit eines Niesers", "Bis zu 160 Stundenkilometer", "Deshalb die Armbeuge."],
       ["Speichel am Tag", "Etwa ein Liter", "Ohne ihn schmeckt nichts."],
       ["Anteil des Gehirns am Energieverbrauch", "Rund ein Fünftel", "Bei zwei Prozent des Gewichts."],
       ["Wachstum der Fingernägel", "Viermal schneller als Fußnägel", "Etwa drei Millimeter im Monat."],
       ["Lebensdauer einer Geschmacksknospe", "Rund zehn Tage", "Danach wird sie ersetzt."],
       ["Zähne eines Erwachsenen", "32", "Milchzähne sind es zwanzig."]]'::jsonb,
     '[["Wächst ein Leben lang weiter", "Das sagt man Ohren und Nase nach, hier ist es keine Antwort."],
       ["Besteht vollständig aus Wasser", "Auf nichts auf diesem Brett trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'firmennamen-herkunft', 'Firmennamen & ihre Herkunft',
     'Woher kommt der Name?',
     'medium', 'Unternehmen', 'https://de.wikipedia.org/wiki/Unternehmen',
     '[["Lego", "Spiel gut auf Dänisch", "Aus leg godt zusammengezogen."],
       ["Adidas", "Spitzname und Nachname des Gründers", "Adi Dassler."],
       ["Ikea", "Initialen, Hof und Heimatdorf", "Ingvar Kamprad, Elmtaryd, Agunnaryd."],
       ["Nivea", "Schneeweiß auf Latein", "Nach der Farbe der Creme."],
       ["Haribo", "Gründer und Firmensitz", "Hans Riegel, Bonn."],
       ["Aldi", "Familienname und das Wort Diskont", "Albrecht Diskont."],
       ["Nike", "Die griechische Siegesgöttin", "Der Haken soll ihr Flügel sein."],
       ["Volvo", "Ich rolle auf Latein", "Ursprünglich ein Name für Kugellager."],
       ["Audi", "Die lateinische Übersetzung von Horch", "Der Gründer hieß August Horch."],
       ["Google", "Eine verschriebene Riesenzahl", "Gemeint war googol."],
       ["Samsung", "Drei Sterne auf Koreanisch", "Für etwas Großes und Beständiges."]]'::jsonb,
     '[["Nach einem Fluss benannt", "Kein Name auf diesem Brett kommt daher."],
       ["Aus einem Losverfahren entstanden", "Keine Firma in dieser Liste kam so zu ihrem Namen."]]'::jsonb),

    ('unnuetzes-wissen', 'dinge-eigentlicher-zweck', 'Kleine Details, großer Zweck',
     'Wofür ist das eigentlich da?',
     'hard', 'Design', 'https://de.wikipedia.org/wiki/Design',
     '[["Das Loch in der Kugelschreiberkappe", "Luft, falls jemand sie verschluckt", "Eine Norm verlangt es."],
       ["Die kleine Tasche in der Jeans", "Platz für die Taschenuhr", "Aus der Zeit vor der Armbanduhr."],
       ["Das Loch im Spaghettilöffel", "Misst eine Portion ab", "Was hindurchpasst, reicht für eine Person."],
       ["Die Rillen am Rand von Münzen", "Schutz vor dem Abfeilen", "Ein fehlender Rand fiel sofort auf."],
       ["Die Schlaufe hinten am Hemd", "Zum Aufhängen im Spind", "Aus der Marineuniform übernommen."],
       ["Die wackelnde Nase am Maßband", "Gleicht ihre eigene Dicke aus", "Innen und außen misst man so gleich."],
       ["Die Löcher im Budapester Schuh", "Wasser sollte ablaufen können", "Ursprünglich ein Schuh fürs Moor."],
       ["Das kleine Loch im Becherdeckel", "Lässt Luft nachströmen", "Sonst fließt der Kaffee stockend."],
       ["Die zusätzlichen Ösen am Turnschuh", "Für einen festeren Sitz der Ferse", "Der Schuh rutscht dann nicht."],
       ["Der Pfeil neben der Tankanzeige", "Zeigt die Seite des Tankdeckels", "Praktisch im fremden Wagen."]]'::jsonb,
     '[["Reine Zierde ohne jeden Zweck", "Jedes Detail auf diesem Brett hat einen echten Grund."],
       ["Verhindert das Verrutschen", "Dafür ist nichts in dieser Liste gedacht."]]'::jsonb),

    ('unnuetzes-wissen', 'laender-kuriosa', 'Länder & Kurioses',
     'Was gilt für dieses Land?',
     'hard', 'Staat', 'https://de.wikipedia.org/wiki/Staat',
     '[["Bhutan", "Misst ein Bruttonationalglück", "Statt allein die Wirtschaftsleistung."],
       ["Kanada", "Mehr Seen als der Rest der Welt zusammen", "Über zwei Millionen."],
       ["Schweiz", "Schutzräume für die ganze Bevölkerung", "Gesetzlich vorgeschrieben."],
       ["Island", "Keine Stechmücken", "Eines der wenigen Länder ohne sie."],
       ["Australien", "Mehr Kängurus als Menschen", "Etwa doppelt so viele."],
       ["Monaco", "Kleiner als der Central Park", "Der zweitkleinste Staat der Welt."],
       ["Russland", "Elf Zeitzonen", "Mehr als jedes andere Land."],
       ["Japan", "Mehr Haustiere als Kinder", "Katzen und Hunde zusammengezählt."],
       ["Schweden", "Führt Müll ein, um ihn zu verbrennen", "Die eigenen Anlagen sind nicht ausgelastet."],
       ["Bolivien", "Zwei Hauptstädte zugleich", "Regierung und höchstes Gericht sitzen getrennt."]]'::jsonb,
     '[["Verbietet Regenschirme", "Kein Land auf diesem Brett kennt so ein Gesetz."],
       ["Hat keine eigene Nationalhymne", "Auf keines in dieser Liste trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'namen-fuer-dinge', 'Dinge, die einen Namen haben',
     'Wie heißt das eigentlich?',
     'hard', 'Fachsprache', 'https://de.wikipedia.org/wiki/Fachsprache',
     '[["Der Punkt über dem i", "Tüpfelchen", "Daher die Redewendung."],
       ["Das Zeichen &", "Et-Zeichen", "Aus dem lateinischen et für und."],
       ["Das Zeichen #", "Doppelkreuz", "Nicht zu verwechseln mit dem Kreuz der Musik."],
       ["Das Zeichen @", "Klammeraffe", "Amtlich heißt es At-Zeichen."],
       ["Die Plastikspitze am Schnürsenkel", "Nestelspitze", "Ohne sie franst das Band aus."],
       ["Die Fläche zwischen den Augenbrauen", "Glabella", "Lateinisch für die Unbehaarte."],
       ["Die Rille zwischen Nase und Oberlippe", "Philtrum", "Griechisch für Liebestrank."],
       ["Der helle Halbmond am Fingernagel", "Lunula", "Das Möndchen der Nagelwurzel."],
       ["Das Kribbeln im eingeschlafenen Fuß", "Parästhesie", "Eine Fehlempfindung der Nerven."],
       ["Das Knacken der Fingergelenke", "Kavitation", "Gasbläschen fallen in sich zusammen."]]'::jsonb,
     '[["Zäpfchen", "Es hängt im Rachen, und danach fragt hier keine Zeile."],
       ["Serife", "Der Abschlussstrich am Buchstaben steht nicht auf dem Brett."]]'::jsonb),

    ('unnuetzes-wissen', 'essen-kurios', 'Essen, unnütz betrachtet',
     'Was stimmt über das Lebensmittel?',
     'medium', 'Lebensmittel', 'https://de.wikipedia.org/wiki/Lebensmittel',
     '[["Honig", "Verdirbt praktisch nie", "In Pharaonengräbern war er noch essbar."],
       ["Erdnuss", "Botanisch eine Hülsenfrucht", "Sie reift unter der Erde."],
       ["Banane", "Botanisch eine Beere", "Die Staude ist ein Kraut, kein Baum."],
       ["Karotte", "War ursprünglich violett", "Orange wurde sie erst später gezüchtet."],
       ["Ananas", "Zersetzt Eiweiß im Mund", "Deshalb das Brennen auf der Zunge."],
       ["Muskatnuss", "In großer Menge berauschend", "Ein Grund, sparsam zu reiben."],
       ["Apfel", "Schwimmt, weil er Luft enthält", "Etwa ein Viertel des Volumens."],
       ["Kartoffel", "Wuchs schon im Weltraum", "1995 an Bord eines Spaceshuttles."],
       ["Cashew", "Wächst außen an der Frucht", "Der Kern hängt unten heraus."],
       ["Wassermelone", "Besteht zu über neunzig Prozent aus Wasser", "Der Name sagt es bereits."]]'::jsonb,
     '[["Enthält überhaupt keine Kalorien", "Auf nichts auf diesem Brett trifft das zu."],
       ["Wächst ausschließlich bei Nacht", "Kein Lebensmittel in dieser Liste tut das."]]'::jsonb),

    ('unnuetzes-wissen', 'sprache-kurios', 'Wörter über Wörter',
     'Wie heißt dieser Fall?',
     'hard', 'Sprachwissenschaft',
     'https://de.wikipedia.org/wiki/Sprachwissenschaft',
     '[["Vorwärts wie rückwärts gleich", "Palindrom", "Reliefpfeiler zum Beispiel."],
       ["Ein Satz mit allen Buchstaben", "Pangramm", "Nützlich zum Prüfen von Schriften."],
       ["Ein Wort ahmt seinen Klang nach", "Onomatopoesie", "Zischen, klirren, summen."],
       ["Ein Wort mit gegensätzlichen Bedeutungen", "Autoantonym", "Umfahren zum Beispiel."],
       ["Ein Wort, das es nur im Plural gibt", "Pluraletantum", "Ferien oder Leute."],
       ["Ein erfundener Eintrag als Fälschungsfalle", "Nihilartikel", "Damit lässt sich Abschreiben nachweisen."],
       ["Der häufigste Buchstabe im Deutschen", "Das E", "Weit vor allen anderen."],
       ["Drei gleiche Buchstaben hintereinander", "Schifffahrt", "Seit der Rechtschreibreform erlaubt."],
       ["Ein Wort aus lauter Anfangsbuchstaben", "Akronym", "Wie Laser oder Radar."],
       ["Zwei Wörter zu einem verschmolzen", "Kofferwort", "Wie Brunch oder Motel."]]'::jsonb,
     '[["Anagramm", "Die Umstellung der Buchstaben, danach fragt hier keine Zeile."],
       ["Synonym", "Zwei Wörter mit einer Bedeutung, und das steht nicht auf dem Brett."]]'::jsonb),

    ('unnuetzes-wissen', 'dauer-kurios', 'Wie lange dauert das?',
     'Welche Dauer gehört dazu?',
     'hard', 'Zeit', 'https://de.wikipedia.org/wiki/Zeit',
     '[["Ein Tag auf der Venus", "Länger als ihr Jahr", "Sie dreht sich langsamer, als sie kreist."],
       ["Ein rotes Blutkörperchen", "Rund 120 Tage", "Danach baut die Milz es ab."],
       ["Sonnenlicht bis zur Erde", "Gut acht Minuten", "Wir sehen die Sonne von vorhin."],
       ["Ein Umlauf des Mondes", "Rund 27 Tage", "Von Fixstern zu Fixstern gerechnet."],
       ["Eine Arbeitsbiene im Sommer", "Etwa sechs Wochen", "Im Winter lebt sie viel länger."],
       ["Die Trächtigkeit eines Elefanten", "Fast zwei Jahre", "Die längste aller Landtiere."],
       ["Der Hundertjährige Krieg", "116 Jahre", "Der Name rundet großzügig ab."],
       ["Der kürzeste Krieg der Geschichte", "38 Minuten", "1896 zwischen Sansibar und Britannien."],
       ["Ein Jahr auf dem Merkur", "88 Tage", "Der sonnennächste Planet ist am schnellsten."],
       ["Eine Eintagsfliege als erwachsenes Tier", "Oft weniger als ein Tag", "Als Larve lebt sie Jahre."]]'::jsonb,
     '[["Genau ein Jahrhundert", "Nichts auf diesem Brett dauert exakt so lange."],
       ["Weniger als eine Sekunde", "Kein Vorgang in dieser Liste ist so kurz."]]'::jsonb),

    ('unnuetzes-wissen', 'tiernamen-woertlich', 'Tiernamen, die lügen',
     'Was stimmt am Namen nicht?',
     'medium', 'Trivialname', 'https://de.wikipedia.org/wiki/Trivialname',
     '[["Meerschweinchen", "Weder Schwein noch vom Meer", "Es kam über See aus den Anden."],
       ["Seepferdchen", "Es ist ein Fisch", "Mit Kiemen und Schwimmblase."],
       ["Walhai", "Ein Hai, kein Wal", "Der größte Fisch der Erde."],
       ["Killerwal", "Eine Delfinart", "Der Orca ist der größte Delfin."],
       ["Fliegender Hund", "Eine Fledermaus", "Nur eine besonders große."],
       ["Blindschleiche", "Weder blind noch Schlange", "Eine Echse ohne Beine."],
       ["Tintenfisch", "Kein Fisch", "Ein Weichtier mit Mantel."],
       ["Roter Panda", "Nicht mit dem Großen Panda verwandt", "Er bildet eine eigene Familie."],
       ["Präriehund", "Ein Nagetier", "Der Ruf klang für Siedler nach Bellen."],
       ["Koalabär", "Ein Beuteltier", "Mit Bären hat er nichts zu tun."]]'::jsonb,
     '[["Ein Vogel ohne Federn", "Kein Tier auf diesem Brett ist so beschrieben."],
       ["In Wahrheit längst ausgestorben", "Alle Tiere in dieser Liste gibt es noch."]]'::jsonb),

    ('unnuetzes-wissen', 'gesetze-kurios', 'Regeln, die es wirklich gibt',
     'Wo gilt diese Regel?',
     'hard', 'Gesetz', 'https://de.wikipedia.org/wiki/Gesetz',
     '[["Meerschweinchen dürfen nicht allein leben", "Schweiz", "Die Tierschutzverordnung verlangt Gesellschaft."],
       ["Kaugummi gibt es nur in der Apotheke", "Singapur", "Seit 1992, mit späteren Ausnahmen."],
       ["Vornamen stammen von einer amtlichen Liste", "Dänemark", "Andere müssen genehmigt werden."],
       ["Der Bauchumfang wird amtlich gemessen", "Japan", "Das sogenannte Metabo-Gesetz."],
       ["Tauben füttern ist untersagt", "Venedig", "Seit 2008 auch auf dem Markusplatz."],
       ["Hohe Absätze sind an antiken Stätten verboten", "Griechenland", "Sie beschädigen den Stein."],
       ["Ein fester Anteil im Radio muss aus dem Land kommen", "Kanada", "Die Regel heißt CanCon."],
       ["Auf der Autobahn ist grundloses Halten verboten", "Deutschland", "Auch der leere Tank gilt als vermeidbar."],
       ["Ohne Hemd Auto zu fahren ist untersagt", "Thailand", "Ein Verstoß kostet Bußgeld."],
       ["Der Verkauf von Tabak war landesweit verboten", "Bhutan", "Von 2010 bis 2021."]]'::jsonb,
     '[["Blaue Autos sind verboten", "Kein Ort auf diesem Brett kennt so eine Regel."],
       ["Der Mittagsschlaf ist Pflicht", "Auf keinen in dieser Liste trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'farben-kurios', 'Farben & ihre Geschichten',
     'Was ist das Besondere an der Farbe?',
     'hard', 'Farbe', 'https://de.wikipedia.org/wiki/Farbe',
     '[["Orange", "Nach der Frucht benannt, nicht umgekehrt", "Vorher hieß sie rotgelb."],
       ["Rosa", "Galt lange als Farbe für Jungen", "Als das kleine Rot."],
       ["Blau", "Fehlt in vielen alten Sprachen", "Homer nannte das Meer weinfarben."],
       ["Purpur", "Wurde aus Schnecken gewonnen", "Für ein Gramm Tausende Tiere."],
       ["Weiß", "Alle Farben des Lichts zusammen", "Ein Prisma trennt sie wieder."],
       ["Ultramarin", "War teurer als Gold", "Aus Lapislazuli aus Afghanistan."],
       ["Mumienbraun", "Enthielt tatsächlich Mumien", "Bis ins 20. Jahrhundert verkauft."],
       ["Scheelegrün", "Enthielt Arsen", "In Tapeten wurde es gefährlich."],
       ["Vantablack", "Schluckt fast alles Licht", "Formen verschwinden darin."],
       ["Gelb", "Fällt dem Auge am stärksten auf", "Darum Warnwesten und Taxis."]]'::jsonb,
     '[["Nur unter Wasser sichtbar", "Keine Farbe auf diesem Brett ist das."],
       ["Erst im 21. Jahrhundert entdeckt", "Auf keine in dieser Liste trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'zahlen-kurios', 'Zahlen, die überraschen',
     'Welche Zahl stimmt?',
     'hard', 'Zahl', 'https://de.wikipedia.org/wiki/Zahl',
     '[["Reihenfolgen eines gemischten Kartenspiels", "Mehr als Sterne in der Galaxie", "52 Karten ergeben eine 68-stellige Zahl."],
       ["Sekunden eines Tages", "86.400", "Eine gute Zahl zum Nachrechnen."],
       ["Knochen eines Neugeborenen", "Rund 300", "Viele wachsen später zusammen."],
       ["Muskeln im Rüssel eines Elefanten", "Rund 40.000", "Der ganze Mensch hat gut 600."],
       ["Geschmacksknospen eines Welses", "Über 100.000", "Er schmeckt mit der ganzen Haut."],
       ["Herzen eines Regenwurms", "Fünf Aortenbögen", "Echte Herzen sind es nicht."],
       ["Augen einer Biene", "Fünf", "Zwei große und drei kleine."],
       ["Mägen einer Kuh", "Ein Magen mit vier Abteilungen", "Nur eine davon verdaut wie unsere."],
       ["Beine eines Tausendfüßers", "Meist deutlich unter tausend", "Erst 2021 fand sich eine Art mit über 1.300."],
       ["Nasenlöcher eines Delfins", "Eines", "Das Blasloch auf dem Kopf."]]'::jsonb,
     '[["Genau eine Million", "Keine Zahl auf diesem Brett ist das."],
       ["Immer eine Primzahl", "Auf nichts in dieser Liste trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'alltagsirrtuemer', 'Hartnäckige Irrtümer',
     'Was stimmt daran nicht?',
     'medium', 'Irrtum', 'https://de.wikipedia.org/wiki/Irrtum',
     '[["Fledermäuse sind blind", "Sie sehen durchaus", "Manche Arten sogar sehr gut."],
       ["Goldfische vergessen alles nach drei Sekunden", "Sie merken sich Monate", "Im Versuch lernen sie Aufgaben."],
       ["Der Mensch nutzt zehn Prozent seines Gehirns", "Er nutzt fast alles davon", "Nur nicht alles gleichzeitig."],
       ["Blut in den Venen ist blau", "Es ist immer rot", "Blau wirkt nur die Haut darüber."],
       ["Haare wachsen nach dem Tod weiter", "Die Haut zieht sich zurück", "Das lässt sie länger wirken."],
       ["Kamele speichern Wasser im Höcker", "Dort ist Fett", "Wasser halten sie im Blut."],
       ["Der Blitz schlägt nie zweimal ein", "Er tut es sogar oft", "Hohe Türme trifft es regelmäßig."],
       ["Stiere sehen Rot", "Sie reagieren auf die Bewegung", "Rinder sind rotblind."],
       ["Nach dem Essen darf man nicht schwimmen", "Ein Zusammenhang ist nicht belegt", "Die Warnung hält sich trotzdem."],
       ["Zucker macht Kinder hyperaktiv", "Studien finden das nicht", "Die Erwartung färbt die Beobachtung."]]'::jsonb,
     '[["Das stimmt sogar genau so", "Kein Satz auf diesem Brett ist wahr, das ist der Punkt."],
       ["Von der Forschung inzwischen bestätigt", "Auf keinen Irrtum in dieser Liste trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'weltall-kurios', 'Unnützes über das All',
     'Was gilt dafür?',
     'hard', 'Universum', 'https://de.wikipedia.org/wiki/Universum',
     '[["Ein Tag auf dem Mars", "Rund 40 Minuten länger als bei uns", "Marsmissionen rechnen in Sol."],
       ["Die Fußspuren auf dem Mond", "Bleiben Millionen Jahre liegen", "Es gibt weder Wind noch Regen."],
       ["Ein Löffel Neutronenstern", "Wiegt Milliarden Tonnen", "Materie ist dort maximal gepackt."],
       ["Die Sonne", "Stellt 99,8 Prozent der Masse im System", "Alle Planeten sind der Rest."],
       ["Saturn", "Wäre leichter als Wasser", "Er würde in einer Wanne schwimmen."],
       ["Der Geruch im Weltraum", "Nach verbranntem Metall", "So beschreiben es Raumfahrer."],
       ["Venus", "Dreht sich andersherum", "Dort geht die Sonne im Westen auf."],
       ["Jupiter", "Hat keine feste Oberfläche", "Das Gas wird nach unten nur dichter."],
       ["Olympus Mons", "Dreimal so hoch wie der Everest", "Der höchste Berg im Sonnensystem."],
       ["Der Mond", "Entfernt sich jedes Jahr ein Stück", "Rund vier Zentimeter."]]'::jsonb,
     '[["Ist mit bloßem Auge nicht zu sehen", "Als Antwort passt das zu nichts auf diesem Brett."],
       ["Besteht vollständig aus Eis", "Nichts in dieser Liste ist das."]]'::jsonb),

    ('unnuetzes-wissen', 'sport-kurios', 'Unnützes aus dem Sport',
     'Was steckt dahinter?',
     'hard', 'Sport', 'https://de.wikipedia.org/wiki/Sport',
     '[["Die Dellen im Golfball", "Er fliegt damit weiter", "Sie halten die Luft am Ball."],
       ["Das schwarz-weiße Muster des Fußballs", "Für das Schwarzweißfernsehen", "Damit man den Ball erkannte."],
       ["Der erste Basketballkorb", "Ein Pfirsichkorb mit Boden", "Der Ball musste herausgeholt werden."],
       ["Die krummen 42,195 Kilometer", "Die Strecke von 1908 in London", "Bis vor die königliche Loge."],
       ["Die weiße Fechtkleidung", "Tinte machte den Treffer sichtbar", "Vor der elektrischen Trefferanzeige."],
       ["Der Boxring", "Ist ein Quadrat", "Rund war er nur ganz am Anfang."],
       ["Die Curlingsteine", "Stammen fast alle von einer schottischen Insel", "Der Granit von Ailsa Craig."],
       ["Der V-Stil beim Skispringen", "Galt zuerst als Haltungsfehler", "Punktabzug gab es trotz größerer Weite."],
       ["Der ursprüngliche Name des Volleyballs", "Mintonette", "Erst später nach dem Zuspiel benannt."],
       ["Die gelben Tennisbälle", "Kamen erst 1986 nach Wimbledon", "Davor waren sie weiß."]]'::jsonb,
     '[["War früher olympisch und ist es heute nicht mehr", "Kein Eintrag auf diesem Brett steht dafür."],
       ["Wird ausschließlich bei Nacht ausgetragen", "Auf nichts in dieser Liste trifft das zu."]]'::jsonb),

    ('unnuetzes-wissen', 'technik-kurios', 'Unnützes über Technik',
     'Was gehört dazu?',
     'medium', 'Technikgeschichte',
     'https://de.wikipedia.org/wiki/Technikgeschichte',
     '[["Das Zeichen @", "Älter als der Computer", "Kaufleute nutzten es für den Stückpreis."],
       ["Die Anordnung der Schreibmaschinentasten", "Sollte die Mechanik entlasten", "Häufige Paare wurden getrennt."],
       ["Der erste dokumentierte Computerbug", "Eine echte Motte", "Sie klemmte in einem Relais."],
       ["Die Computermaus", "Hieß zuerst X-Y-Positionsanzeiger", "Der Spitzname setzte sich durch."],
       ["Bluetooth", "Benannt nach einem Wikingerkönig", "Harald Blauzahn einte Dänemark."],
       ["Nokia", "Begann als Papierfabrik", "Benannt nach einem finnischen Fluss."],
       ["Nintendo", "Begann mit Spielkarten", "Hanafuda-Karten ab 1889."],
       ["Das Symbol zum Speichern", "Eine Diskette", "Die kaum noch jemand in der Hand hatte."],
       ["Der erste Tweet", "Meldete nur das Einrichten des Kontos", "Von Jack Dorsey, 2006."],
       ["Das erste Bild im World Wide Web", "Eine Band vom CERN", "Die Comedygruppe Les Horribles Cernettes."]]'::jsonb,
     '[["Entstand in einer Garage", "Als Antwort passt das zu nichts auf diesem Brett."],
       ["Ist bis heute patentgeschützt", "Kein Eintrag in dieser Liste steht dafür."]]'::jsonb),

    ('unnuetzes-wissen', 'pflanzen-kurios', 'Pflanzen mit Eigenheiten',
     'Was zeichnet die Pflanze aus?',
     'medium', 'Pflanzen', 'https://de.wikipedia.org/wiki/Pflanzen',
     '[["Bambus", "Wächst bis zu einen Meter am Tag", "Das schnellste Wachstum überhaupt."],
       ["Erdbeere", "Die Nüsschen außen sind die Früchte", "Das Rote ist nur der Blütenboden."],
       ["Mammutbaum", "Der schwerste Baum der Erde", "Der General Sherman wiegt Tausende Tonnen."],
       ["Grannenkiefer", "Der älteste bekannte Einzelbaum", "Über 4.800 Jahre alt."],
       ["Titanwurz", "Riecht nach verwesendem Fleisch", "So lockt sie Aasfliegen an."],
       ["Venusfliegenfalle", "Zählt die Berührungen mit", "Erst der zweite Reiz schließt sie."],
       ["Sonnenblume", "Junge Blüten folgen der Sonne", "Ausgewachsen zeigen sie nach Osten."],
       ["Brennnessel", "Ihre Haare sind Glasröhrchen", "Sie brechen ab und spritzen."],
       ["Mimose", "Klappt bei Berührung zusammen", "Innerhalb von Sekunden."],
       ["Baobab", "Speichert Tausende Liter Wasser", "Im dicken Stamm."],
       ["Rafflesia", "Trägt die größte Einzelblüte", "Über einen Meter Durchmesser."]]'::jsonb,
     '[["Wächst nur in völliger Dunkelheit", "Keine Pflanze auf diesem Brett tut das."],
       ["Blüht nur alle hundert Jahre", "Das sagt man der Agave nach, und die fehlt hier."]]'::jsonb),

    ('unnuetzes-wissen', 'kuriose-rekorde', 'Kuriose Rekorde',
     'Wer oder was hält ihn?',
     'hard', 'Weltrekord', 'https://de.wikipedia.org/wiki/Weltrekord',
     '[["Längster Ortsname Europas", "Ein Dorf in Wales", "58 Buchstaben auf dem Bahnhofsschild."],
       ["Meistgestohlenes Buch aus Bibliotheken", "Das Guinness-Buch der Rekorde", "Ein Rekord über sich selbst."],
       ["Meistgecovertes Lied", "Yesterday", "Über zweitausend Fassungen."],
       ["Meistverkauftes Buch", "Die Bibel", "In Milliardenauflage."],
       ["Längster Stau der Geschichte", "Zwölf Tage in China", "2010 auf dem Weg nach Peking."],
       ["Meistgesprochene erfundene Sprache", "Klingonisch", "Mit eigenem Wörterbuch."],
       ["Teuerstes Gewürz nach Gewicht", "Safran", "Die Ernte geschieht von Hand."],
       ["Ältestes durchgehend geführtes Unternehmen", "Ein japanischer Baubetrieb", "Gegründet im Jahr 578."],
       ["Meistbesuchtes Gemälde der Welt", "Die Mona Lisa", "Millionen Blicke im Jahr."],
       ["Häufigster Nachname der Welt", "Wang", "Rund hundert Millionen Menschen."]]'::jsonb,
     '[["Der längste Fluss der Welt", "Danach fragt kein Rekord auf diesem Brett."],
       ["Das älteste erhaltene Foto", "Es steht nicht in dieser Liste."]]'::jsonb)
),

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
