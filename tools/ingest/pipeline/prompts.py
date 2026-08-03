"""Every word the model is sent, as LangChain prompt templates.

Kept apart from the chains that run them: the prompts are the part that gets
tuned, and tuning them should not mean reading control flow. Each template
declares its own input variables, so a missing one is an error at invoke time
rather than a silently half-filled prompt.

`EXTRACT` ends with a `MessagesPlaceholder`. That is what makes the repair loop
work: the first pass fills it with nothing, and each rejected attempt appends
the model's own answer plus the complaints about it, so attempt three still sees
everything that went wrong in attempts one and two.

The rules here come in two kinds, and the difference is worth keeping straight.
What makes a question *correct* is stated -- one answer per category, everything
from the article -- because `validate.py` and the reviewer enforce the same
thing afterwards. What makes a question *ours* is shown instead, out of
`examples.py`: told to write a good title a small model writes
"Periodensystem-Zuordnung", and no amount of prose fixes that, while four real
titles from the seeded pool do.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from ..domain.rules import MAX_ITEM_WORDS, MAX_PAIRS, MIN_PAIRS
from .examples import render_explanations, render_questions

EXTRACT_SYSTEM = f"""\
Du erstellst Zuordnungsfragen für ein deutschsprachiges Quiz.

EINE ZUORDNUNGSFRAGE IST EINE 1-ZU-1-ZUORDNUNG.

Jede Frage besteht aus Paaren. Ein Paar ist eine Kategorie und die EINE Antwort,
die dazu gehört. Der Spieler ordnet jede Antwort genau einer Kategorie zu.

WAS IST KATEGORIE, WAS IST ANTWORT?
- `label` (Kategorie) = das Feld, in das einsortiert wird. Auf dem Spielfeld
  steht es fest sichtbar.
- `answer` (Antwort) = der konkrete Begriff, den der Spieler dorthin zieht.

Alle Kategorien einer Frage sind gleichartig, und alle Antworten sind
gleichartig. Prüfe das: Ergeben deine Kategorien untereinander eine sinnvolle
Liste? Und deine Antworten ebenso?

Beispiel:
  Deutschland  -> Berlin
  Frankreich   -> Paris
  Italien      -> Rom
  Spanien      -> Madrid

Hier sind alle Kategorien Länder und alle Antworten Hauptstädte. Genau so.

VERDREHE DIE BEIDEN NICHT. Falsch wäre:
  Berlin  -> Hauptstadt          <-- FALSCH, Rollen vertauscht
  Paris   -> Hauptstadt          <-- und "Hauptstadt" doppelt

Ebenso falsch ist eine Frage über EIN einzelnes Ding, deren Kategorien nur
dessen Eigenschaften sind:
  Fort Carson  -> Hauptquartier  <-- FALSCH
  1917         -> Gründungsjahr  <-- FALSCH
Eine Frage vergleicht MEHRERE gleichartige Dinge miteinander. Gibt der Artikel
nur ein einziges Ding her, setze `usable` auf false.

STRIKTE REGELN:
- Jede Kategorie hat GENAU EINE Antwort. Niemals zwei.
- Jede Antwort gehört zu GENAU EINER Kategorie.
- Keine Kategorie kommt zweimal vor.
- Keine Antwort kommt zweimal vor.
- Es gibt KEINE zusätzlichen Antworten und keine Antworten ohne Kategorie.
  Jede Antwort auf dem Spielfeld gehört zu genau einer Kategorie.

Falsch wäre zum Beispiel:
  19. Jahrhundert -> Deutsche Reichsgründung
  19. Jahrhundert -> Wiener Kongress          <-- FALSCH, Kategorie doppelt

GRÖSSE DER FRAGE:
Eine Frage braucht {MIN_PAIRS} bis {MAX_PAIRS} Paare. Das ist eine feste
Vorgabe.

Gibt der Artikel nicht genug her, um auf mindestens {MIN_PAIRS} saubere, im
Artikel belegte Paare zu kommen, dann setze `usable` auf false und begründe es
kurz. Das ist die richtige Antwort und kein Fehler -- es gibt immer einen
nächsten Artikel.

Erfinde NIEMALS Paare, nur um auf {MIN_PAIRS} zu kommen. Eine abgelehnte Frage
ist weit besser als eine Frage mit erfundenen Fakten.

WEITERE REGELN:
- Alle Angaben müssen aus dem gelieferten Artikel belegbar sein.
- Die Zuordnung muss eindeutig sein: eine Antwort darf sachlich nicht zu zwei
  der angebotenen Kategorien passen. Wähle im Zweifel eine andere Kategorie.
- Antworten sind kurze Begriffe (höchstens {MAX_ITEM_WORDS} Wörter), keine Sätze.
- Kein Begriff ist gleichzeitig Kategorie und Antwort.
- Alles auf Deutsch.

Schwierigkeit:
- easy: Allgemeinwissen, die meisten Erwachsenen lösen das.
- medium: solides Allgemeinwissen nötig.
- hard: Detailwissen oder Fachkenntnis nötig.

STIL -- SO SEHEN UNSERE FRAGEN AUS:

- Die Frage handelt von einer KLASSE von Dingen, nicht vom Artikel. Der Artikel
  ist der Steinbruch, nicht das Thema. Aus dem Artikel "Periodensystem" wird
  "Chemische Elemente", niemals "Periodensystem-Zuordnung".
- `title`: zwei oder drei Wörter, keine Frage, kein Doppelpunkt, kein
  Artikelname. Entweder beide Seiten der Zuordnung mit & verbunden
  ("Gemälde & Maler") oder eine Sammelbezeichnung im Plural
  ("Chemische Elemente").
- `slug`: der Titel klein geschrieben, ohne &, mit Bindestrichen, Umlaute
  ausgeschrieben -- "gemaelde-maler", "hauptstaedte-europas". Nie ein Anhängsel
  wie "-zuordnung" und nie der Titel des Artikels.
- `description`: GENAU EINE Frage mit Fragezeichen, höchstens acht Wörter. Sie
  nennt die KATEGORIE im Singular mit Artikel und fragt nach der ANTWORT --
  Kategorie "Italien", Antwort "Rom" ergibt "Welche Stadt ist die Hauptstadt des
  Landes?". Sprich den Spieler nicht an ("Ordne zu ..."), und nenne kein Wort,
  das in den Paaren vorkommt.
- Kategorien und Antworten stehen ohne Artikel und ohne Zusatz in Klammern da.
- Antworten sind so kurz, wie sie eindeutig sein können: "Goethe", nicht
  "Johann Wolfgang von Goethe"; "Fe", nicht "Fe (Eisen)".

Vier echte Fragen aus unserem Bestand. Übernimm ihre Machart -- Zuschnitt,
Titel, Anleitung, Kürze der Antworten -- aber NIEMALS ihren Inhalt: deine Frage
kommt aus dem Artikel unten.

{render_questions()}

Antworte ausschließlich mit dem geforderten JSON-Objekt.
"""

EXTRACT_HUMAN = """\
Artikel: {title}

--- Artikeltext ---
{text}
--- Ende Artikeltext ---

Verfügbare Themengebiete (wähle genau eines, gib den slug an):
{subjects}

Erstelle daraus eine Zuordnungsfrage nach den Regeln.
"""

EXTRACT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACT_SYSTEM),
        ("human", EXTRACT_HUMAN),
        MessagesPlaceholder("repairs", optional=True),
    ]
)

REPAIR = PromptTemplate.from_template(
    f"""\
Deine letzte Antwort verletzt diese Regeln:
{{problems}}

Erstelle die Zuordnungsfrage erneut und behebe genau diese Punkte. Halte dich
an alle übrigen Regeln.

Wenn ein Paar inhaltlich falsch war oder nicht eindeutig zugeordnet werden
kann: lass es lieber ganz weg, statt es durch etwas Erfundenes zu ersetzen.
Fällst du dabei unter {MIN_PAIRS} Paare, setze `usable` auf false.
"""
)

REFRAME_SYSTEM = """\
Du benennst eine bestehende Zuordnungsfrage um.

Die Frage wird jetzt mit BILDERN gespielt: jede KATEGORIE ist ein Foto. Der
Spieler sieht also mehrere Fotos und ordnet jedem Foto eine Antwort in Worten
zu. Die Antworten bleiben Text.

Die Paare sind unverändert und korrekt. Bei manchen Fragen wurde zusätzlich die
Richtung gedreht -- was vorher die Antwort war, ist jetzt die Kategorie und
damit das Bild. Verlass dich deshalb nur auf die Paare unten, nicht auf den
bisherigen Titel.

Schreibe dafür:
- `title`: kurzer Titel der Frage, passend zu dieser Richtung.
- `description`: EIN kurzer Satz Spielanleitung, der sagt, was zu tun ist.

REGELN:
- Deutsch.
- Der Titel nennt beide Seiten der Zuordnung, mit & verbunden, zwei oder drei
  Wörter: "Städte & Länder", "Elemente & Symbole". Keine Frage, kein
  Doppelpunkt, kein Artikelname.
- Die Anleitung ist EIN Satz mit Fragezeichen, höchstens acht Wörter. Sie
  spricht das Bild an und fragt nach der ANTWORT -- also nach dem, was der
  Spieler dem Bild zuordnen soll. Nimm die Wörter aus den Paaren unten, nicht
  aus dieser Anleitung.
- Ändere KEINE Paare. Erfinde nichts dazu.

Die Beispiele hier sind NUR das Format, niemals der Inhalt:
  Paare "Paris -> Frankreich", "Rom -> Italien"   (Bild = die Stadt)
    title:       "Städte & Länder"
    description: "In welchem Land liegt diese Stadt?"
  Paare "Eisen -> Fe", "Sauerstoff -> O"          (Bild = das Element)
    title:       "Elemente & Symbole"
    description: "Welches Symbol gehört zu diesem Element?"
"""

REFRAME_HUMAN = """\
Die Zuordnung, wie sie gespielt wird (Kategorie, die als Bild gezeigt wird ->
Antwort in Worten):
{pairs}

Bisheriger Titel: {title}

Schreibe Titel und Anleitung für diese Bilderfrage.
"""

REFRAME = ChatPromptTemplate.from_messages(
    [
        ("system", REFRAME_SYSTEM),
        ("human", REFRAME_HUMAN),
    ]
)

EXPLAIN_SYSTEM = f"""\
Du schreibst zu jeder Antwort einer Zuordnungsfrage eine sehr kurze Begründung.

Sie wird dem Spieler erst NACH dem Antworten gezeigt, direkt neben der Antwort.
Er soll auf einen Blick verstehen, warum die Antwort zu ihrer Kategorie gehört.

REGELN:
- Höchstens EIN kurzer Satz, maximal 12 Wörter. Kein Nebensatzgeflecht.
- Kein einleitendes Gerede ("Diese Antwort ist richtig, weil ..."). Direkt zur
  Sache.
- Nenne den entscheidenden Fakt, nicht die Spielregel. Am besten ist eine harte
  Angabe: eine Jahreszahl, ein Ort, die Herkunft des Namens, das eine Merkmal.
- Ein Satz ohne Verb ist erlaubt und oft der bessere ("Vom lateinischen
  aurum."). Punkt am Ende.
- Deutsch.

So sehen unsere Begründungen aus -- oben das Paar, darunter die Begründung zu
seiner Antwort:

{render_explanations()}

Schreibe für JEDE Antwort genau eine Begründung.
"""

EXPLAIN_HUMAN = """\
--- Quelltext ---
{text}
--- Ende Quelltext ---

Frage: {title}

Die Zuordnung:
{pairs}

Schreibe zu jeder Antwort eine Begründung.
"""

EXPLAIN = ChatPromptTemplate.from_messages(
    [
        ("system", EXPLAIN_SYSTEM),
        ("human", EXPLAIN_HUMAN),
    ]
)

REVIEW_SYSTEM = """\
Du prüfst eine Zuordnungsfrage für ein Quiz gegen den Quelltext.

Die Frage ist eine 1-zu-1-Zuordnung: jede Kategorie hat genau eine Antwort,
jede Antwort gehört zu genau einer Kategorie. Es gibt keine zusätzlichen
Antworten.

Prüfe genau drei Dinge:
1. Gehört jede Antwort wirklich zu ihrer Kategorie -- belegt durch den Quelltext
   oder unstrittiges Allgemeinwissen? Wenn nicht, melde die Antwort in
   `misplaced_items`.
2. Ist die Zuordnung EINDEUTIG? Eine Antwort, die sachlich genauso gut zu einer
   anderen der angebotenen Kategorien passt, macht die Frage unfair -- melde sie
   ebenfalls in `misplaced_items` und sage in `problems`, mit welcher Kategorie
   sie sich überschneidet.
3. Ist inhaltlich etwas schlicht falsch?

Die ANZAHL der Paare ist NICHT dein Thema. Ob ein Begriff kurz genug ist, auch
nicht.

Sei streng, aber melde nur echte Fehler. Wenn die Frage in Ordnung ist, setze
`ok` auf true und lass die Listen leer.

Formuliere jeden Punkt in `problems` so, dass er direkt behebbar ist, z. B.
"'Wasser' passt sowohl zu 'Anorganische Stoffe' als auch zu 'Reduktionsmittel'
-- ersetze eine der beiden Kategorien".
"""

REVIEW_HUMAN = """\
--- Quelltext ---
{text}
--- Ende Quelltext ---

Zu prüfende Zuordnungsfrage: {title}

Die Zuordnung:
{pairs}

Prüfe die Frage.
"""

REVIEW = ChatPromptTemplate.from_messages(
    [
        ("system", REVIEW_SYSTEM),
        ("human", REVIEW_HUMAN),
    ]
)
