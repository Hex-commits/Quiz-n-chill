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

MEHRERE FRAGEN:
Du lieferst eine Liste von Fragen. Jede Frage ist ein eigener Blickwinkel auf den
Artikel und steht für sich -- zwei Fragen dürfen nicht dieselbe Zuordnung mit
anderen Worten sein.

Suche aktiv nach allen Blickwinkeln, die der Artikel wirklich hergibt: andere
Klasse von Dingen, andere Eigenschaft, andere Epoche. Ein längerer Artikel trägt
oft mehrere gute Fragen, und sie alle zu liefern ist ausdrücklich erwünscht.

Aber: Liefere nur so viele, wie der Artikel deckt. Findest du einen einzigen
guten Blickwinkel, gib genau eine Frage zurück -- das ist dann die richtige
Antwort. Eine Frage, die nur aufgefüllt wurde, um die Liste zu verlängern, ist
schlechter als keine Frage: sie kostet den Artikel nichts, aber sie verdrängt
nichts Gutes und wird ohnehin aussortiert.

Gibt der Artikel überhaupt nichts her, gib eine einzige Frage mit
`usable: false` zurück.

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
{extras}
Verfügbare Themengebiete (wähle für jede Frage genau eines, gib den slug an):
{subjects}

Erstelle daraus bis zu {drafts} verschiedene Zuordnungsfragen nach den Regeln.
"""

NEIGHBOURS_NOTE = """\
DER ARTIKEL OBEN ALLEIN REICHT NICHT.

Er handelt von einem einzelnen Ding, und eine Zuordnungsfrage braucht mehrere
gleichartige Dinge. Darum folgen weitere Artikel über Dinge derselben Art.

Behandle alle Texte zusammen als EINEN Steinbruch: nimm aus jedem Text ein Paar
derselben Art und stelle sie zu einer Frage zusammen -- der Artikel oben ist
dabei eines der Dinge, nicht das Thema.

Aus "Fort Carson" allein wird nichts. Aus "Fort Carson", "Fort Bragg" und
"Fort Hood" wird "Militärbasen & Bundesstaaten".

Es bleibt dabei: Jedes Paar muss in einem der Texte belegt sein, und alle
Kategorien einer Frage sind gleichartig, ebenso alle Antworten. Reicht auch das
zusammen nicht für {min_pairs} saubere Paare, setze `usable` auf false.
""".format(min_pairs=MIN_PAIRS)
"""Prefixes the neighbouring articles `broaden` fetched, when there are any.

Not part of the system prompt: on the overwhelming majority of articles there
are no neighbours, and a permanent paragraph about how to use texts that are not
there is a paragraph that invites the model to imagine them.

The worked example is doing the real work. Told only that further texts follow,
a small model reads them as background and writes a question about the first
article anyway -- which is the question it just declined. Naming three forts and
the board they make is what turns "here is more to read" into "here is the class
this article is a member of".
"""

NEIGHBOUR_ARTICLE = """\

--- Weiterer Artikel: {title} ---
{text}
--- Ende ---"""

EXTRACT = ChatPromptTemplate.from_messages(
    [
        ("system", EXTRACT_SYSTEM),
        ("human", EXTRACT_HUMAN),
        MessagesPlaceholder("repairs", optional=True),
    ]
)

SELECT_SYSTEM = """\
Du wählst aus mehreren Entwürfen für Quiz-Fragen die aus, die es wert sind,
gespielt zu werden.

Alle Entwürfe stammen aus demselben Artikel. Sie sind formal in Ordnung -- darum
geht es hier nicht. Die Frage ist:

  Lernt oder weiß der Spieler etwas, wenn er diese Frage löst?

BEHALTE eine Frage, wenn sie echtes Wissen abfragt: etwas, das man wissen kann,
das interessant ist, und bei dem Richtig und Falsch einen Unterschied machen.

VERWIRF eine Frage, wenn:
- sie zu trivial ist. Zehn europäische Hauptstädte sind für Erwachsene kein
  Wissen, sondern Schulstoff.
- sie beliebig ist. Katalognummern, Aktenzeichen, Kapitelüberschriften: es gibt
  nichts zu wissen, nur etwas nachzulesen.
- sie eine andere Frage der Liste nur wiederholt. Behalte dann die bessere.

Arbeite in dieser Reihenfolge:
1. `verdict`: Sag in einem Satz, was die Entwürfe taugen.
2. `keep`: Die Nummern der Fragen, die du behältst.

MEHRERE behalten ist ausdrücklich erlaubt und erwünscht, wenn mehrere wirklich
gut sind und verschiedene Dinge abfragen.

KEINE behalten ist auch erlaubt: eine leere Liste heißt, dass dieser Artikel
keine Frage hergibt, die jemand spielen will. Das ist besser als eine langweilige
Frage durchzulassen.

Deutsch.
"""

SELECT_HUMAN = """\
Artikel: {title}

Die Entwürfe:
{drafts}

Welche behältst du?
"""

SELECT = ChatPromptTemplate.from_messages(
    [
        ("system", SELECT_SYSTEM),
        ("human", SELECT_HUMAN),
    ]
)
"""Picks which of `extract`'s drafts are worth playing.

Not a correctness check -- `check` and `review` do that, and this runs before
both, on drafts nothing has vetted yet. The judgement is narrower and it is the
one no other step makes: **does answering this teach the player anything?**

The two failure modes it exists to catch, neither of which is a rule violation:

    1. The trivial board. "Deutschland -> Berlin" for ten European capitals is
       well-formed, factual, unambiguous and worth nothing to anyone who has
       been to school. Every gate downstream passes it.
    2. The arbitrary board. Ten obscure list entries paired with their catalogue
       numbers is equally well-formed and equally worthless -- there is nothing
       to *know*, only something to have read.

Keeping several is expected and is the point of asking for several: one article
usually holds more than one good question, and the pipeline used to take
whichever the model happened to write first.

**What it is worth today.** On `glm4:9b`, not much: asked about two drafts of
`Periodensystem` it kept both and called them "gut geeignet für ein Quiz", one
of which was two pairs long with the same answer under both categories. That is
the same agreement bias measured for the homogeneity judgement in `REVIEW` and
for `vet.py` -- a small model asked "is this good?" says yes.

It is wired to `INGEST_JUDGE_MODEL` for that reason, alongside `vet`: the
mechanism is sound and the judge is the part to upgrade. The step cannot admit a
*malformed* question whatever it thinks, because `check` and `review` are both
downstream of it. What a weak judge costs is the filtering: it keeps drafts that
are merely dull, so the pool grows faster than it improves. `--drafts 1` is the
way back to one question per article, and it skips this step entirely.
"""

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

Arbeite in dieser Reihenfolge:
1. `shown`: Was ist auf den Fotos zu sehen? Das ist die linke Seite der Paare
   unten -- die Kategorie.
2. `asked`: Was soll der Spieler dem Foto zuordnen? Das ist die rechte Seite der
   Paare unten -- die Antwort.
3. `title`: kurzer Titel der Frage, passend zu dieser Richtung.
4. `description`: EIN kurzer Satz Spielanleitung, der nach `asked` fragt.

Lies `shown` und `asked` aus den Paaren ab, nicht aus dem bisherigen Titel. Wenn
du sie verdrehst, fragt die Anleitung nach dem, was der Spieler schon sieht.

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
    shown:       "eine Stadt"
    asked:       "das Land"
    title:       "Städte & Länder"
    description: "In welchem Land liegt diese Stadt?"
  Paare "Eisen -> Fe", "Sauerstoff -> O"          (Bild = das Element)
    shown:       "ein chemisches Element"
    asked:       "das Symbol"
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

AUGMENT_SYSTEM = """\
Du ergänzt eine bestehende Zuordnungsfrage um weitere Paare.

Die Frage ist fertig und korrekt, ihr fehlen nur noch ein paar Paare. Du liest
jetzt einen ANDEREN Artikel und suchst darin Paare der GLEICHEN Art.

REGELN:
- Die Beziehung zwischen Kategorie und Antwort muss exakt dieselbe sein wie in
  den vorhandenen Paaren. Sieh dir an, was dort womit verknüpft ist.
- Jedes neue Paar muss im Quelltext unten klar belegt sein. Nichts aus deinem
  eigenen Wissen ergänzen.
- Keine Kategorie und keine Antwort darf schon in der Frage vorkommen.
- Antworten sind höchstens vier Wörter lang.
- WENIGER ist völlig in Ordnung. Findest du nichts Passendes, gib eine leere
  Liste zurück. Erfinde niemals ein Paar, nur um die Zahl zu erreichen.
- Deutsch.

Beispiel: Die Frage ordnet Flüssen ihre Länge zu ("Rhein -> 1233 km").
  Im neuen Artikel steht die Länge der Donau  -> "Donau -> 2857 km"   RICHTIG
  Im neuen Artikel steht die Quelle der Donau -> "Donau -> Schwarzwald" FALSCH
  (andere Beziehung, auch wenn das Paar für sich stimmt)
"""

AUGMENT_HUMAN = """\
Die bestehende Frage: {title}

Ihre bisherigen Paare (Kategorie -> Antwort):
{pairs}

--- Quelltext ({source_title}) ---
{text}
--- Ende Quelltext ---

Suche höchstens {needed} weitere Paare derselben Art in diesem Quelltext.
"""

AUGMENT = ChatPromptTemplate.from_messages(
    [
        ("system", AUGMENT_SYSTEM),
        ("human", AUGMENT_HUMAN),
    ]
)
"""Asks for further pairs from a *different* article.

Runs only when a question failed the pair count and nothing else, so the two
risks here are not the ones the extract prompt guards against:

    1. Drifting off the relation. Given "Fluss -> Länge" and an article about a
       river, a model will happily offer "Fluss -> Quellgebiet". That is a fine
       pairing and the wrong one, and mixed into a board it makes the question
       unanswerable.
    2. Filling the gap. It is told exactly how many are missing, which is an
       invitation to invent that many. Saying "fewer is fine, none is fine" is
       the only thing that reliably stops it.
"""

VET_SYSTEM = """\
Auf einem Quiz-Spielfeld stehen Paare. Jedes beantwortet dieselbe Frage über
sein Stichwort.

Dir wird EIN weiteres Paar vorgeschlagen. Arbeite in dieser Reihenfolge:

1. `relation`: Welche Frage beantworten die Paare auf dem Spielfeld? Formuliere
   sie als echte Frage -- "Wie lang ist dieser Fluss?", "Welche Stadt ist die
   Hauptstadt dieses Landes?".
2. `answers_it`: Welche Frage beantwortet das vorgeschlagene Paar? Sieh dir
   dafür NUR das vorgeschlagene Paar an. Schreibe hier nicht einfach die Frage
   von oben ab.
3. `fits`: Sind das dieselbe Frage?

Es geht um die BEDEUTUNG, nicht um die Form. Ein Paar kann genauso aussehen wie
die anderen und eine andere Frage beantworten -- dann ist `fits` false. Sag auch
dann nein, wenn das Paar für sich genommen völlig richtig ist.

Beispiele:
  Spielfeld "Rhein -> 1233 km", vorgeschlagen "Mosel -> Rhein"
    Das Spielfeld fragt nach der Länge, der Vorschlag nach der Mündung.
    -> fits: false
  Spielfeld "Deutschland -> Berlin", vorgeschlagen "Frankreich -> Macron"
    Das Spielfeld fragt nach der Hauptstadt, der Vorschlag nach dem Präsidenten.
    -> fits: false
"""

VET_HUMAN = """\
Spielfeld:
{board}

Vorgeschlagenes Paar:
{candidate}
"""

VET = ChatPromptTemplate.from_messages(
    [
        ("system", VET_SYSTEM),
        ("human", VET_HUMAN),
    ]
)
"""Judges ONE borrowed pair against the board.

Per pair rather than per board, because a model asked "are these all the same
kind of thing" answers about the set and says yes; asked about a single pair it
at least has something specific to be wrong about.

`relation` comes first in the schema and constrained decoding emits properties
in order, so the model has to name what the board asks before it may rule on the
candidate. That is the difference between judging meaning and judging shape --
without it, `Mosel -> Rhein` passes a board of river lengths because it looks
the same.

Measured at roughly chance on glm4:9b. See the note in `vet.py`; the step is off
by default for that reason.
"""

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
nicht. Ein Teil der Paare kann aus einem anderen Artikel stammen; steht unten
ein zusätzlicher Quelltext, gilt er für die Prüfung genauso wie der erste.

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
"""Checks three things, not four.

Homogeneity -- "are all these pairs the same kind of pairing" -- belongs here in
principle and was tried here in practice, and glm4:9b cannot do it. Measured on
five boards, including

    Deutschland -> Berlin, Frankreich -> Baguette, Italien -> Rom

it answered `same_kind: true` every time, and justified that one as
"Land -> Hauptstadt". A dedicated single-purpose prompt with three worked
examples did no better than a fourth bullet in this one, so it is not a question
of wording: the model is agreement-biased and this judgement is past it. Adding
the bullet anyway would lengthen a prompt it already struggles with and document
a check that does not happen.

So the board's consistency is still caught by a person reading the Markdown
report before `--commit`, which is what that report is for. Worth retrying on a
larger reviewer model.

There is no MessagesPlaceholder here, and that is the point: the reviewer sees
the article and the finished question, never the generator's transcript. A model
re-reading its own reasoning mostly agrees with itself.
"""
