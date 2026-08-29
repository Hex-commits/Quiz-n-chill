"use client";

/**
 * The table.
 *
 * Laid out as one, because that is what the game is: a felt in the middle with
 * the pot and the question on it, and the players sat round the edge. Everyone
 * is looking at the same object, and where a thing sits says what it is --
 * chips in front of a player are theirs, chips in the middle are nobody's yet.
 *
 * The felt carries the reveal. There are no cards in this version: the question
 * fills in a line at a time, one at the top of each betting round, and the
 * betting is what the players do about it.
 *
 * Chips are the thing to be able to read at a glance, so every stack gets a
 * number *and* a bar. The number is exact; the bar is comparative -- who is
 * ahead is a question about the other stacks, and answering it by reading four
 * numbers is slower than seeing four bars.
 *
 * Holds no rules. Every legality question -- whose turn, what a raise has to
 * be, whether an answer counts -- is settled by the API; this file draws what
 * came back and posts what was clicked.
 */

import { useEffect, useRef, useState } from "react";
import { Check, Coins, Crown, Loader2 } from "lucide-react";

import { AnswerPool } from "@/components/answer-pool";
import { CategoryPicture, ImageCredit } from "@/components/category-image";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { HURRY_FROM, play, playCountdown } from "@/lib/sound";
import { cn } from "@/lib/utils";
import type {
  CategoryImage,
  LobbyView,
  PokerAction,
  PokerSeat,
  PokerView,
} from "@/lib/types";

/**
 * How many rungs of the reveal each round has lit.
 *
 * The opening round is already worth one: the blinds and the subject arrive
 * together, so there is no round in this game that is bet on nothing.
 */
const REVEALED: Record<PokerView["stage"], number> = {
  preflop: 1,
  flop: 2,
  turn: 3,
  answering: 3,
  payout: 3,
};

/**
 * How long each reveal holds the screen, in milliseconds.
 *
 * The question gets longer than the two that lead up to it. It is the one
 * anybody has to read rather than glance at, and it is the last thing they see
 * before betting on whether they know it.
 */
const CURTAIN_MS = [0, 2400, 2400, 3400];

/** What each rung of the reveal is called on the curtain. */
const CURTAIN_TERM = ["", "Subject", "Topic", "The question"];

export function PokerTable({
  lobby,
  poker,
  playerId,
  secondsLeft,
  busy,
  onAct,
  onAnswer,
  onBack,
}: {
  lobby: LobbyView;
  poker: PokerView;
  playerId: string;
  /** Whichever clock the table is running, ticked in the browser. */
  secondsLeft: number | null;
  busy: boolean;
  onAct: (action: PokerAction, amount?: number) => void;
  onAnswer: (itemId: string) => void;
  onBack: (backedId: string) => void;
}) {
  const me = poker.seats.find((seat) => seat.player_id === playerId) ?? null;
  const curtain = useReveal(poker);
  usePokerSounds(poker, me, secondsLeft);

  const nameOf = (id: string) =>
    lobby.players.find((player) => player.id === id)?.nickname ?? "—";

  /* What the bars are drawn against: the biggest stack at the table, or the pot
     where that is bigger still. Early in a hand the pot is most of the chips
     that have moved, and a bar scaled to a full stack would never leave zero. */
  const biggest = Math.max(...poker.seats.map((seat) => seat.stack), poker.pot, 1);

  /* Split down the middle so the felt has players either side of it, the way it
     would if they were sat there. One column below `lg`, where a table with
     sides is just two narrow columns of nothing. */
  const half = Math.ceil(poker.seats.length / 2);
  const sides = [poker.seats.slice(0, half), poker.seats.slice(half)];

  return (
    <>
      {curtain ? <Curtain curtain={curtain} /> : null}
      <div className="mx-auto w-full max-w-5xl space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Hand {poker.hand_index + 1} of {poker.hand_count}
        </p>
        {secondsLeft !== null ? (
          <Badge
            variant="outline"
            className={cn(
              "font-mono tabular-nums",
              secondsLeft <= HURRY_FROM && "border-destructive/60 text-destructive",
            )}
          >
            {secondsLeft}s
          </Badge>
        ) : null}
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)_minmax(0,1fr)] lg:items-center">
        {sides.map((side, index) => (
          <div
            key={index}
            className={cn(
              "grid gap-2 sm:grid-cols-2 lg:grid-cols-1",
              /* The felt reads first on a phone, where there are no sides. */
              index === 0 ? "order-2 lg:order-none" : "order-3 lg:order-none",
            )}
          >
            {side.map((seat) => (
              <Seat
                key={seat.player_id}
                seat={seat}
                name={nameOf(seat.player_id)}
                isMe={seat.player_id === playerId}
                isDealer={seat.player_id === poker.button_id}
                onTheClock={seat.player_id === poker.to_act}
                backing={seat.backing ? nameOf(seat.backing) : null}
                biggest={biggest}
                stage={poker.stage}
              />
            ))}
          </div>
        ))}

        <div className="order-1 lg:order-none">
          <Felt poker={poker} />
        </div>
      </div>

      {poker.stage === "payout" && poker.result ? (
        <Payout poker={poker} nameOf={nameOf} secondsLeft={secondsLeft} />
      ) : poker.stage === "answering" ? (
        <Answering
          poker={poker}
          me={me}
          secondsLeft={secondsLeft}
          seconds={lobby.settings.turn_seconds}
          busy={busy}
          onAnswer={onAnswer}
        />
      ) : (
        <Betting
          poker={poker}
          me={me}
          playerId={playerId}
          nameOf={nameOf}
          busy={busy}
          onAct={onAct}
          onBack={onBack}
        />
      )}
      </div>
    </>
  );
}

type Reveal = {
  rung: number;
  term: string;
  value: string | null;
  image: CategoryImage | null;
};

/**
 * Raise the curtain when the question has just said something new.
 *
 * Keyed on how far the reveal has got rather than on the stage, so a hand that
 * jumps -- everyone all in, and the rest of the question arriving in one
 * server-side step -- still shows the last thing it uncovered rather than
 * nothing at all.
 *
 * The one thing raised on a client's first view is a hand that has only just
 * begun -- the game starting, which the whole table is watching. Anything
 * further along is somebody joining part-way through and catching up, and see
 * the effect for why that gets no curtain.
 */
function useReveal(poker: PokerView): Reveal | null {
  const [curtain, setCurtain] = useState<Reveal | null>(null);
  const seen = useRef<{ hand: number; rung: number } | null>(null);

  const rung = REVEALED[poker.stage];
  const value =
    rung === 1
      ? poker.subject_name
      : rung === 2
        ? poker.title
        : (poker.question?.label ?? null);
  const image = rung >= 3 ? (poker.question?.image ?? null) : null;

  useEffect(() => {
    const was = seen.current;
    seen.current = { hand: poker.hand_index, rung };

    /* On the very first view, the only thing worth raising a curtain for is a
       hand that has only just begun -- the game starting, which every player is
       watching. Anything further along is a hand somebody is joining part-way
       through, and announcing what the table saw a minute ago would be a lie
       about what just happened. */
    const fresh = was
      ? poker.hand_index !== was.hand
        ? 0
        : was.rung
      : poker.stage === "preflop"
        ? 0
        : rung;
    if (rung <= fresh || rung < 1) return;
    if (!value && !image) return;

    play(rung >= 3 ? "reveal" : "step");
    /* Raising the curtain *is* the reaction to a view arriving, and the sound
       above it cannot happen during a render. Adjusting state in render, as the
       count-in does, is not available to something that also has to make a
       noise. */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurtain({ rung, term: CURTAIN_TERM[rung], value, image });
  }, [poker.hand_index, poker.stage, rung, value, image]);

  useEffect(() => {
    if (!curtain) return;
    const timer = setTimeout(() => setCurtain(null), CURTAIN_MS[curtain.rung]);
    return () => clearTimeout(timer);
  }, [curtain]);

  return curtain;
}

/**
 * The reveal, full screen.
 *
 * The same shape as the count-in between rounds, deliberately: this game
 * already has one way of saying "everybody look up", and a second one would
 * only be a second thing to learn. It does not take the pointer -- the clock is
 * still running underneath, and a player who has already decided should be able
 * to act through it.
 */
function Curtain({ curtain }: { curtain: Reveal }) {
  return (
    <div
      className="animate-quiz-curtain bg-background/80 pointer-events-none fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 p-6 backdrop-blur-md"
      style={{ "--curtain-ms": `${CURTAIN_MS[curtain.rung]}ms` } as React.CSSProperties}
      aria-hidden
    >
      <p className="text-muted-foreground text-xs font-bold tracking-[0.3em] uppercase">
        {curtain.term}
      </p>
      {curtain.image ? (
        <div className="animate-quiz-count-in w-full max-w-sm overflow-hidden rounded-2xl shadow-2xl">
          <CategoryPicture image={curtain.image} label="The question" />
        </div>
      ) : (
        <p className="animate-quiz-count-in text-primary max-w-4xl text-center text-4xl leading-none font-black text-balance sm:text-6xl">
          {curtain.value}
        </p>
      )}
    </div>
  );
}

/**
 * The middle of the table: the pot, and the question as far as it has been
 * told.
 *
 * Green and round and carrying its own colours rather than the page's, because
 * it is a thing on the page rather than a part of it -- the one element here
 * that should look the same in both themes, for the same reason a real table
 * does not change colour when somebody turns the lights down.
 */
function Felt({ poker }: { poker: PokerView }) {
  const revealed = REVEALED[poker.stage];

  return (
    <div
      className={cn(
        "mx-auto w-full max-w-md rounded-[2.5rem] px-6 py-7 text-emerald-50 shadow-xl",
        "bg-[radial-gradient(ellipse_at_center,var(--color-emerald-700),var(--color-emerald-900))]",
        "ring-8 ring-amber-950/40 ring-inset",
      )}
    >
      <div className="flex flex-col items-center gap-0.5">
        <span className="text-[11px] font-medium tracking-[0.2em] text-emerald-200/70 uppercase">
          Pot
        </span>
        <span className="font-mono text-4xl font-bold tabular-nums">
          {poker.pot}
        </span>
        {poker.carried > 0 ? (
          <span className="text-xs text-amber-200/90">
            {poker.carried} carried from the last hand
          </span>
        ) : null}
      </div>

      <dl className="mt-5 space-y-1.5 border-t border-emerald-200/20 pt-4 text-sm">
        <Rung term="Subject" value={poker.subject_name} lit={revealed >= 1} />
        <Rung term="Topic" value={poker.title} lit={revealed >= 2} />
        <Rung
          term="Question"
          value={poker.question ? (poker.question.label ?? "the picture below") : null}
          lit={revealed >= 3}
          loud
        />
      </dl>

      {poker.question?.image ? (
        <figure className="mt-3 space-y-1">
          <div className="overflow-hidden rounded-(--radius-sm)">
            <CategoryPicture
              image={poker.question.image}
              label={poker.question.label ?? "The question"}
            />
          </div>
          <figcaption className="text-emerald-100/70">
            <ImageCredit image={poker.question.image} />
          </figcaption>
        </figure>
      ) : null}
    </div>
  );
}

/**
 * One line of the reveal, or a dash where it has not been told yet.
 *
 * The unlit rungs stay on the felt rather than appearing as they fill. Knowing
 * that two more things are still to come is part of what an early bet is made
 * on.
 */
function Rung({
  term,
  value,
  lit,
  loud,
}: {
  term: string;
  value: string | null;
  lit: boolean;
  /** The question itself, which is the one anybody reads twice. */
  loud?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-3">
      <dt className="w-20 shrink-0 text-[10px] tracking-[0.15em] text-emerald-200/60 uppercase">
        {term}
      </dt>
      <dd
        className={cn(
          "min-w-0 truncate",
          !lit || !value
            ? "text-emerald-200/30"
            : loud
              ? "text-lg font-semibold"
              : "font-medium",
        )}
      >
        {lit && value ? value : "—"}
      </dd>
    </div>
  );
}

/**
 * A player's place: their name, their chips as a number and as a bar, and
 * whatever they have pushed forward.
 *
 * The bet sits in its own pill rather than in the stack, because that is where
 * those chips are -- out of the stack, not yet in the pot, and coming back to
 * nobody until the street closes.
 */
function Seat({
  seat,
  name,
  isMe,
  isDealer,
  onTheClock,
  backing,
  biggest,
  stage,
}: {
  seat: PokerSeat;
  name: string;
  isMe: boolean;
  isDealer: boolean;
  onTheClock: boolean;
  /** Who they are behind, having folded. */
  backing: string | null;
  /** The biggest stack at the table, for the bar to be read against. */
  biggest: number;
  stage: PokerView["stage"];
}) {
  const out = seat.folded || seat.sitting_out;

  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2 transition-colors",
        onTheClock && "border-primary bg-primary/5 shadow-sm",
        out && "opacity-55",
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {name}
          {isMe ? <span className="text-muted-foreground"> (you)</span> : null}
        </span>
        {seat.is_correct === true ? (
          <Crown className="size-3.5 shrink-0 text-amber-500" aria-label="Right" />
        ) : null}
        {stage === "answering" && seat.has_answered ? (
          <Check className="text-success size-3.5 shrink-0" aria-label="Answered" />
        ) : null}
        {isDealer ? (
          <span
            className="bg-foreground text-background flex size-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold"
            title="Dealer"
          >
            D
          </span>
        ) : null}
      </div>

      <div className="mt-0.5 flex items-baseline gap-2">
        <span className="font-mono text-xl font-semibold tabular-nums">
          {seat.stack}
        </span>
        {seat.won > 0 ? (
          <span className="text-success font-mono text-xs">+{seat.won}</span>
        ) : null}
        <span className="text-muted-foreground ml-auto truncate text-[11px]">
          {seat.sitting_out
            ? "sitting out"
            : seat.all_in
              ? "all in"
              : seat.folded
                ? backing
                  ? `behind ${backing}`
                  : "folded"
                : ""}
        </span>
      </div>

      {/* Comparative, not absolute: the bar answers "who is ahead", which the
          numbers alone make you work out. */}
      <div className="bg-muted mt-1.5 h-1 overflow-hidden rounded-full">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            out ? "bg-muted-foreground/40" : "bg-primary",
          )}
          style={{ width: `${Math.min(100, (seat.stack / biggest) * 100)}%` }}
        />
      </div>

      {seat.committed > 0 || seat.side_stake > 0 ? (
        <div className="mt-1.5 flex justify-end">
          <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 font-mono text-xs tabular-nums text-amber-700 dark:text-amber-300">
            <Coins className="size-3" aria-hidden />
            {seat.committed + seat.side_stake}
          </span>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The betting bar.
 *
 * Raise sizes are offered as buttons rather than a field. A field on a phone is
 * a keyboard over the table and a number to think of while a clock runs; the
 * two sizes anyone reaches for are the smallest legal one and the pot, so those
 * are the two that get a button.
 */
function Betting({
  poker,
  me,
  playerId,
  nameOf,
  busy,
  onAct,
  onBack,
}: {
  poker: PokerView;
  me: PokerSeat | null;
  playerId: string;
  nameOf: (id: string) => string;
  busy: boolean;
  onAct: (action: PokerAction, amount?: number) => void;
  onBack: (backedId: string) => void;
}) {
  if (!me || me.sitting_out) {
    return <Waiting>Sitting this hand out.</Waiting>;
  }

  if (me.folded) {
    return <Backing poker={poker} me={me} nameOf={nameOf} busy={busy} onBack={onBack} />;
  }

  if (poker.to_act !== playerId) {
    return (
      <Waiting>
        {poker.to_act ? `${nameOf(poker.to_act)} is thinking…` : "Dealing…"}
      </Waiting>
    );
  }

  const owed = poker.current_bet - me.committed;
  const max = me.committed + me.stack;
  const raises = [
    poker.current_bet + poker.min_raise,
    poker.current_bet + poker.pot,
  ].filter((size, index, all) => size < max && all.indexOf(size) === index);

  return (
    <Card>
      <CardContent className="space-y-2">
        {poker.stage === "turn" ? (
          <p className="text-muted-foreground text-center text-xs">
            The answers come out once this betting round is done.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button variant="outline" disabled={busy} onClick={() => onAct("fold")}>
            Fold
          </Button>
          {owed > 0 ? (
            <Button disabled={busy} onClick={() => onAct("call")}>
              Call {Math.min(owed, me.stack)}
            </Button>
          ) : (
            <Button disabled={busy} onClick={() => onAct("check")}>
              Check
            </Button>
          )}
          {raises.map((size) => (
            <Button
              key={size}
              variant="secondary"
              disabled={busy}
              onClick={() => onAct("raise", size)}
            >
              Raise to {size}
            </Button>
          ))}
          <Button variant="secondary" disabled={busy} onClick={() => onAct("all_in")}>
            All in {max}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Out of the hand, but not out of the game.
 *
 * A folded player can put a big blind behind somebody still in it. It gives the
 * players who folded early something to do besides watch, and it is a real read
 * rather than a raffle: you fold before the question is up, so you are betting
 * on who at this table knows their subjects.
 */
function Backing({
  poker,
  me,
  nameOf,
  busy,
  onBack,
}: {
  poker: PokerView;
  me: PokerSeat;
  nameOf: (id: string) => string;
  busy: boolean;
  onBack: (backedId: string) => void;
}) {
  if (me.backing) {
    return (
      <Waiting>
        You are behind {nameOf(me.backing)} for {me.side_stake}. A share of
        whatever they take is yours.
      </Waiting>
    );
  }

  const candidates = poker.seats.filter((seat) => !seat.folded && !seat.sitting_out);
  if (me.stack < poker.big_blind || candidates.length === 0) {
    return <Waiting>You folded. Watching this one out.</Waiting>;
  }

  return (
    <Card>
      <CardContent className="space-y-2">
        <p className="text-sm">
          You folded. Put {poker.big_blind} behind someone still in it?
        </p>
        <p className="text-muted-foreground text-xs">
          They answer right and your stake comes back with a share of what they
          take. Wrong, and it joins the pot for whoever does take it.
        </p>
        <div className="flex flex-wrap gap-2">
          {candidates.map((seat) => (
            <Button
              key={seat.player_id}
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => onBack(seat.player_id)}
            >
              Back {nameOf(seat.player_id)}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * The answers, and the one button that spends them.
 *
 * Two clicks rather than one: a hand's worth of chips is riding on the answer,
 * and a mis-tap on a twelve-button grid should cost nothing. The first click
 * picks, the second commits, and after that the choice is the server's -- it
 * comes back only when the hand pays out.
 */
function Answering({
  poker,
  me,
  secondsLeft,
  seconds,
  busy,
  onAnswer,
}: {
  poker: PokerView;
  me: PokerSeat | null;
  secondsLeft: number | null;
  /** What the clock started at, so the bar drains against the right total. */
  seconds: number;
  busy: boolean;
  onAnswer: (itemId: string) => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const answered = poker.seats.filter((seat) => seat.has_answered).length;
  const answering = poker.seats.filter(
    (seat) => !seat.folded && !seat.sitting_out,
  ).length;

  if (!me || me.folded || me.sitting_out) {
    return (
      <Waiting>
        {me?.backing ? "Riding on your pick. " : "Out of this one. "}
        {answered} of {answering} have answered.
      </Waiting>
    );
  }

  if (me.has_answered) {
    return (
      <Waiting>
        Locked in. {answered} of {answering} have answered.
      </Waiting>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium">
            Which of these belongs to the question?
          </p>
          <span className="text-muted-foreground font-mono text-xs tabular-nums">
            {answered}/{answering}
          </span>
        </div>
        <Progress
          value={((secondsLeft ?? 0) / Math.max(seconds, 1)) * 100}
          className="h-1.5"
        />
        <AnswerPool
          items={poker.options}
          selectedId={picked}
          disabled={busy}
          onSelect={setPicked}
        />
        {/* As heavy as the chips above it: the pool is the decision, and this
            is the half of it that spends chips. */}
        <Button
          size="lg"
          className="w-full"
          disabled={busy || picked === null}
          onClick={() => picked && onAnswer(picked)}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          Lock in
        </Button>
      </CardContent>
    </Card>
  );
}

/** What the hand was for, once it is over. */
function Payout({
  poker,
  nameOf,
  secondsLeft,
}: {
  poker: PokerView;
  nameOf: (id: string) => string;
  secondsLeft: number | null;
}) {
  const result = poker.result;
  if (!result) return null;

  return (
    <Card>
      <CardContent className="space-y-3 text-sm">
        {result.uncontested ? (
          <p className="font-medium">
            Everyone folded — the pot goes without a question being asked.
          </p>
        ) : (
          <p>
            <span className="text-muted-foreground">The answer was </span>
            <span className="font-medium">
              {result.correct_labels.join(", ") || "—"}
            </span>
          </p>
        )}
        {result.explanation ? (
          <p className="text-muted-foreground">{result.explanation}</p>
        ) : null}

        {result.awards.length > 0 ? (
          <ul className="space-y-1">
            {result.awards.map((award) => (
              <li key={award.player_id} className="flex items-center gap-2">
                <Coins className="text-success size-3.5" aria-hidden />
                <span className="font-medium">{nameOf(award.player_id)}</span>
                <span className="text-muted-foreground">takes</span>
                <span className="font-mono">{award.amount}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">
            Nobody had it. {result.carried} stays on the table for the next hand.
          </p>
        )}

        <p className="text-muted-foreground text-xs">
          Next hand in {secondsLeft ?? 0}s
        </p>
      </CardContent>
    </Card>
  );
}

function Waiting({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground py-2 text-center text-sm">{children}</p>;
}

/**
 * The table, heard.
 *
 * One effect rather than a cue fired from each button, because most of what is
 * worth hearing did not happen on this device: somebody else called, the reveal
 * moved on, the answers went up. All of that arrives as a new view, so the
 * sounds are differences between the last one and this one.
 *
 * Nothing plays on the first view, and nothing plays across a change of hand. A
 * player who reloads mid-hand would otherwise be dealt every sound of the hand
 * so far at once.
 */
function usePokerSounds(
  poker: PokerView,
  me: PokerSeat | null,
  secondsLeft: number | null,
) {
  const before = useRef<{
    hand: number;
    stage: PokerView["stage"];
    chips: number;
    folded: number;
    allIn: number;
    onTheClock: boolean;
  } | null>(null);

  /* Holding a seat is not the same as being in the hand: a folded player must
     not be told it is their turn to answer. */
  const answering = Boolean(me && !me.folded && !me.sitting_out);

  useEffect(() => {
    const now = {
      hand: poker.hand_index,
      stage: poker.stage,
      /* Side stakes count as chips moving too -- backing someone is the one bet
         in this game that never touches `committed`. */
      chips: poker.seats.reduce(
        (total, seat) => total + seat.committed + seat.side_stake,
        0,
      ),
      folded: poker.seats.filter((seat) => seat.folded).length,
      allIn: poker.seats.filter((seat) => seat.all_in).length,
      onTheClock: poker.to_act === me?.player_id,
    };
    const was = before.current;
    before.current = now;
    if (!was || now.hand !== was.hand) return;

    if (now.allIn > was.allIn) play("allIn");
    else if (now.chips > was.chips) play("chip");
    if (now.folded > was.folded) play("fold");

    if (now.onTheClock && !was.onTheClock) play("yourTurn");
    if (now.stage === "answering" && was.stage !== "answering" && answering) {
      play("yourTurn");
    }

    if (now.stage === "payout" && was.stage !== "payout") {
      if (me && me.won > 0) play("potWon");
      else if (me?.is_correct === false) play("wrong");
      else if (me?.is_correct) play("correct");
    }
  }, [poker, me, answering]);

  /**
   * The closing seconds, in the same escalating cue the classic clock uses.
   *
   * Only where the seconds are yours to spend: your own turn to act, an
   * answering you are part of, and the count-in to the next hand, which is the
   * one moment the whole table is counted in together.
   */
  const yours =
    (poker.stage === "answering" && answering) ||
    poker.stage === "payout" ||
    poker.to_act === me?.player_id;

  useEffect(() => {
    if (!yours || secondsLeft === null) return;
    if (secondsLeft <= 0 || secondsLeft > HURRY_FROM) return;
    playCountdown(secondsLeft);
  }, [secondsLeft, yours]);
}
