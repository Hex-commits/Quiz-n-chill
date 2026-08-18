"""Picture boards for Videospiele, second batch.

The first batch took the obvious free imagery: consoles, handhelds, home
computers, cabinets, controllers. What is left on Commons is mostly *people* --
conference portraits are photographed by attendees and freely licensed, which
is why a games subject can have three portrait boards and no screenshots.

Probed and rejected, so nobody re-probes them: `Rumble Pak`, `Wii Balance
Board`, `Nunchuk` and `Sega Mega Drive` all carry the same P18 file as the
console or controller they belong to, so they would show a photo the player has
already seen on another board. A media board (CD, DVD, UMD, floppy) reached only
eight usable pairs -- `Steckmodul` and `Compactkassette` have no image at all --
and an e-sport board only eight, so neither is here.

Regenerate with:
    python supabase/questions/build_pictures.py bilder-videospiele-02.sql boards_videospiele_02
"""

BOARDS = [
    dict(
        subject="videospiele", slug="bild-entwickler-zwei",
        title="Gesichter hinter den Reihen",
        description="Wofür ist die abgebildete Person bekannt?",
        difficulty="hard", source_title="Spieleentwickler",
        source_url="https://de.wikipedia.org/wiki/Spieleentwickler",
        pairs=[
            ("Todd Howard", "Skyrim", "Er leitet die Rollenspiele von Bethesda."),
            ("Peter Molyneux", "Populous", "Bekannt für große Versprechen vor jedem Start."),
            ("Richard Garriott", "Ultima", "Er nennt sich selbst Lord British."),
            ("Warren Spector", "Deus Ex", "Ein Spiel, drei Lösungswege für jede Tür."),
            ("Cliff Bleszinski", "Gears of War", "Deckung als Kern des Shooters."),
            ("Jane Jensen", "Gabriel Knight", "Adventures mit ernster Handlung."),
            ("Brenda Romero", "Wizardry", "Sie arbeitete schon an den frühen Teilen mit."),
            ("Rand Miller", "Myst", "Er spielt auch selbst eine Rolle darin."),
            ("Sam Houser", "Grand Theft Auto", "Mitgründer von Rockstar Games."),
            ("Fumito Ueda", "Shadow of the Colossus", "Sechzehn Bosse, sonst fast nichts."),
            ("David Cage", "Heavy Rain", "Erzählung mit Entscheidungen statt Kämpfen."),
            ("Jonathan Blow", "Braid", "Es machte kleine Spiele wieder ernst."),
        ],
    ),
    dict(
        subject="videospiele", slug="bild-komponisten",
        title="Wer schrieb die Musik?",
        description="Für welches Spiel oder welche Reihe schrieb die Person die Musik?",
        difficulty="hard", source_title="Videospielmusik",
        source_url="https://de.wikipedia.org/wiki/Videospielmusik",
        pairs=[
            ("Kōji Kondō", "Super Mario", "Die bekannteste Melodie der Branche."),
            ("Nobuo Uematsu", "Final Fantasy", "Seine Stücke füllen Konzertsäle."),
            ("Yoko Shimomura", "Kingdom Hearts", "Zuvor bei Capcom und Square."),
            ("Jesper Kyd", "Hitman", "Chorgesang zum lautlosen Töten."),
            ("Austin Wintory", "Journey", "Erste Spielmusik mit Grammy-Nominierung."),
            ("Martin O’Donnell", "Halo", "Mönchsgesang über Streichern."),
            ("Yuzo Koshiro", "Streets of Rage", "Clubmusik auf dem Mega Drive."),
            ("Jeremy Soule", "The Elder Scrolls", "Hörner und weite Chöre."),
            ("Christopher Tin", "Civilization IV", "Das Titellied gewann einen Grammy."),
            ("Junichi Masuda", "Pokémon", "Er komponierte und leitete zugleich."),
            ("Hans Zimmer", "Call of Duty", "Der Filmkomponist schrieb ein Hauptthema."),
            ("Olivier Deriviere", "A Plague Tale", "Streicher und Chor für das Mittelalter."),
        ],
    ),
    dict(
        subject="videospiele", slug="bild-hauptsitze",
        title="Hauptsitze der Branche",
        description="In welcher Stadt steht das Gebäude?",
        difficulty="hard", source_title="Spieleentwickler",
        source_url="https://de.wikipedia.org/wiki/Spieleentwickler",
        pairs=[
            ("Nintendo", "Kyoto", "Die Firma sitzt seit ihrer Gründung dort."),
            ("Capcom", "Osaka", "Resident Evil und Street Fighter entstehen hier."),
            ("Square Enix", "Tokio", "Im Stadtteil Shinjuku."),
            ("Blizzard Entertainment", "Irvine", "Vor dem Eingang steht ein Orc aus Bronze."),
            ("Electronic Arts", "Redwood City", "Zwischen San Francisco und San José."),
            ("Epic Games", "Cary", "In North Carolina, nicht im Silicon Valley."),
            ("Riot Games", "Los Angeles", "An der Olympic Boulevard."),
            ("Valve", "Bellevue", "Gegenüber von Seattle."),
            ("Ubisoft", "Paris", "Der Sitz liegt in Saint-Mandé am Stadtrand."),
            ("Mojang Studios", "Stockholm", "Minecraft entstand hier."),
        ],
    ),
    dict(
        subject="videospiele", slug="bild-kuriose-hardware",
        title="Kuriose Hardware",
        description="Was ist das Besondere an dem Gerät?",
        difficulty="hard", source_title="Spielkonsole",
        source_url="https://de.wikipedia.org/wiki/Spielkonsole",
        pairs=[
            ("Virtual Boy", "Rot-schwarzes 3D", "Nach kurzer Zeit wieder eingestellt."),
            ("Power Glove", "Handschuh fürs NES", "Berühmter als er funktionierte."),
            ("Sega 32X", "Aufsatz auf die Konsole", "Er steckte im Modulschacht."),
            ("Ouya", "Aus dem Crowdfunding", "Millionen gesammelt, kaum Spiele."),
            ("Nintendo Labo", "Zubehör aus Pappe", "Zusammengefaltet und dann gespielt."),
            ("Paddle (Eingabegerät)", "Drehregler statt Stick", "Für Schläger, die nur seitwärts fahren."),
            ("Steam Controller", "Zwei Tastfelder", "Ersatz für die Maus im Wohnzimmer."),
            ("DualSense", "Widerstand in den Triggern", "Der Bogen spannt sich spürbar."),
            ("Sega Master System", "Mit 3D-Brille erhältlich", "Lange vor der heutigen VR-Welle."),
            ("Wii", "Steuerung durch Schwingen", "Sie holte Leute an die Konsole, die nie spielten."),
            ("PlayStation 3", "Cell-Prozessor", "Berüchtigt schwer zu programmieren."),
        ],
    ),
]
