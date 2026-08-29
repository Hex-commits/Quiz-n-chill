"use client";

/**
 * The table.
 *
 * Drawn as one: an oval of felt with the players sat round its rim, all of them
 * facing the same middle. Where a thing sits is what says what it is -- chips
 * in front of a player are theirs, chips in the middle are nobody's yet, and a
 * card on the felt belongs to the whole table.
 *
 * You are always in the near chair. The ring is turned so that whoever is
 * looking sits at the bottom and the rest fan out from there in turn order:
 * some beside you, some across the felt, the table between you. It is the one
 * arrangement anybody who has sat at a table already knows how to read.
 *
 * The felt carries the reveal, as three cards face down in the middle. One
 * turns over at the top of each betting round -- subject, then topic, then the
 * question itself -- and the betting is what the players do about it.
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

/** How far out the chairs sit, as a percentage of the table's box. */
const RING_X = 46;
const RING_Y = 46;

/**
 * Where the `index`-th chair round from yours is.
 *
 * Screen y grows downwards, so starting a quarter turn on puts the first chair
 * -- always the player looking at it -- at the bottom, and the rest run
 * clockwise from there, the way the action does.
 */
function chairAt(index: number, count: number) {
  const angle = Math.PI / 2 + (index / count) * 2 * Math.PI;
  return {
    left: rim(50 + RING_X * Math.cos(angle), "--chair-x"),
    top: rim(50 + RING_Y * Math.sin(angle), "--chair-y"),
    /** Sat above the middle, so their chips belong below them -- towards it. */
    upper: Math.sin(angle) < 0,
  };
}

/**
 * One coordinate of a chair, held far enough from the edge that the plaque on
 * it cannot hang off the page.
 *
 * The ring is a percentage of a box that trebles in width between a phone and a
 * desktop, while a plaque is a fixed number of rem -- so there is no single
 * radius that is both out on the rim of the wide table and still on the screen
 * at the narrow one. The clamp settles it in CSS, where both are known at once,
 * and the chairs it pulls in are the ones at the far ends of the long axis,
 * where a few pixels of ellipse are all that is given up.
 */
function rim(percent: number, half: string) {
  return `clamp(var(${half}), ${percent}%, calc(100% - var(${half})))`;
}

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

  /* Turned so that you are in the near chair. Only where the ring starts moves
     -- the order itself is the server's -- so the player on your left is still
     the one who acts after you. */
  const first = Math.max(
    0,
    poker.seats.findIndex((seat) => seat.player_id === playerId),
  );
  const around = poker.seats.map(
    (_, index) => poker.seats[(first + index) % poker.seats.length],
  );

  return (
    <>
      {curtain ? <Curtain curtain={curtain} /> : null}
      <div className="mx-auto w-full max-w-3xl space-y-3">
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

      {/* Taller than it is wide on a phone, where a landscape table would leave
          the felt too narrow to read a question off; landscape from `sm`, which
          is the shape of the real thing. */}
      <div className="relative aspect-[4/5] w-full sm:aspect-[16/10]">
        <Felt poker={poker} />
        {around.map((seat, index) => {
          const chair = chairAt(index, around.length);
          return (
            <div
              key={seat.player_id}
              /* Half a plaque, for `rim` to keep the chair clear of the edge by. */
              className={cn(
                "absolute -translate-x-1/2 -translate-y-1/2",
                "[--chair-x:2.5rem] [--chair-y:2.25rem]",
                "sm:[--chair-x:3.5rem] sm:[--chair-y:2.5rem]",
              )}
              style={{ left: chair.left, top: chair.top }}
            >
              <Seat
                seat={seat}
                name={nameOf(seat.player_id)}
                isMe={seat.player_id === playerId}
                isDealer={seat.player_id === poker.button_id}
                onTheClock={seat.player_id === poker.to_act}
                backing={seat.backing ? nameOf(seat.backing) : null}
                biggest={biggest}
                stage={poker.stage}
                stakeBelow={chair.upper}
              />
            </div>
          );
        })}
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
 * The table itself: a rail, a felt, and what is on it.
 *
 * Green and round and carrying its own colours rather than the page's, because
 * it is a thing on the page rather than a part of it -- the one element here
 * that should look the same in both themes, for the same reason a real table
 * does not change colour when somebody turns the lights down.
 *
 * It fills its box absolutely so the chairs can be laid over that same box and
 * land on the rim. The inset padding is what keeps the middle clear of them:
 * generous enough that no card ever runs under a plaque, at any width.
 */
function Felt({ poker }: { poker: PokerView }) {
  const revealed = REVEALED[poker.stage];
  const image = revealed >= 3 ? (poker.question?.image ?? null) : null;

  return (
    <div
      className={cn(
        "absolute inset-0 rounded-[50%] p-2.5 shadow-2xl sm:p-4",
        "bg-[linear-gradient(160deg,var(--color-amber-700),var(--color-amber-950))]",
      )}
    >
      <div
        className={cn(
          "flex size-full flex-col items-center justify-center gap-2 rounded-[50%] text-emerald-50 sm:gap-3",
          /* The inset is what keeps the middle clear of the chairs on the rim,
             and it has to be wider on a phone: the plaques do not shrink as
             fast as the table does. */
          "px-[24%] py-8 sm:px-[20%] sm:py-10",
          "bg-[radial-gradient(ellipse_at_center,var(--color-emerald-600),var(--color-emerald-900))]",
          "ring-1 ring-emerald-950/60 ring-inset",
        )}
      >
        <div className="flex flex-col items-center leading-none">
          <span className="text-[9px] font-medium tracking-[0.2em] text-emerald-200/70 uppercase sm:text-[11px]">
            Pot
          </span>
          <span className="font-mono text-2xl font-bold tabular-nums sm:text-4xl">
            {poker.pot}
          </span>
          {poker.carried > 0 ? (
            <span className="mt-1 text-[9px] text-amber-200/90 sm:text-xs">
              {poker.carried} carried from the last hand
            </span>
          ) : null}
        </div>

        {/* One row on a wide table; on a phone the question drops beneath the
            other two, which is the only way it gets a line long enough to read.
            Done with `contents` rather than `flex-wrap` on purpose: a wrapped
            row reports the height of its tallest line rather than of all of
            them, and the middle of the felt is centred against that number --
            so the question ran out under the near chairs. */}
        <div className="flex w-full flex-col items-center gap-1.5 sm:flex-row sm:items-stretch sm:justify-center sm:gap-2">
          <div className="flex justify-center gap-1.5 sm:contents">
            <BoardCard term="Subject" value={poker.subject_name} up={revealed >= 1} />
            <BoardCard term="Topic" value={poker.title} up={revealed >= 2} />
          </div>
          <BoardCard
            term="Question"
            value={poker.question?.label ?? null}
            image={image}
            up={revealed >= 3}
            wide
          />
        </div>

        {/* The licence is owed wherever the work is shown, and on this table it
            is shown on a card the size of a stamp. */}
        {image ? (
          <div className="text-emerald-100/70">
            <ImageCredit image={image} className="text-[9px]" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * One card on the board, face down until its part of the question has been
 * told.
 *
 * All three lie there from the first bet rather than being dealt as they turn.
 * Knowing that two more things are still to come is part of what an early bet
 * is made on, and a face-down card says that better than a blank line does.
 *
 * The question's card is dealt wide -- landscape between two portraits, and on
 * a phone a whole row to itself. It is the one card anybody has to *read*, and
 * a sentence set four words to a line in a poker-shaped box is a sentence
 * nobody reads twice.
 */
function BoardCard({
  term,
  value,
  image,
  up,
  wide,
}: {
  term: string;
  value: string | null;
  image?: CategoryImage | null;
  /** Turned over. What is still face down has no value in the payload either. */
  up: boolean;
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        "quiz-flip rounded-(--radius-sm)",
        wide
          ? "min-h-16 w-full sm:min-h-0 sm:w-auto sm:min-w-36 sm:flex-1"
          : "aspect-[5/7] w-12 shrink-0 sm:w-16",
      )}
    >
      <div className={cn("quiz-flip-inner", up && "quiz-flip-inner--up")}>
        <div className="quiz-flip-face quiz-card-back rounded-(--radius-sm) shadow-md ring-1 ring-emerald-950/40" />
        <div
          className={cn(
            "quiz-flip-face quiz-flip-face--front flex flex-col items-center justify-center gap-0.5",
            "overflow-hidden rounded-(--radius-sm) bg-emerald-50 p-1 text-center text-emerald-950 shadow-md",
          )}
        >
          <span className="text-[7px] font-bold tracking-[0.15em] text-emerald-800/60 uppercase sm:text-[9px]">
            {term}
          </span>
          {image ? (
            /* A height rather than an aspect ratio: the three cards are stretched
               to a common height, and a picture that sets its own would drag the
               two beside it into tall thin strips. Cropping is the lesser cost --
               the curtain shows the picture whole, and the card zooms. */
            <CategoryPicture
              image={image}
              label={value ?? "The question"}
              className="h-16 w-full rounded-(--radius-sm) sm:h-24"
            />
          ) : (
            <span
              className={cn(
                "leading-tight font-semibold text-balance",
                wide ? "text-[11px] sm:text-sm" : "text-[8px] sm:text-[11px]",
              )}
            >
              {value}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * A player's place at the rim: their name, their chips as a number and as a
 * bar, and whatever they have pushed forward.
 *
 * A fixed-width plaque, because chairs sit on an ellipse and one that grew with
 * its nickname would pull the ring out of shape as names came and went. It
 * carries its own opaque back: it lies half on the felt, where the page's own
 * background is nowhere to be seen.
 *
 * The bet is not drawn in the stack, because that is not where those chips are
 * -- out of the stack, not yet in the pot, and sat between the player and the
 * middle until the street closes, which is the side of the plaque it goes on.
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
  stakeBelow,
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
  /** They sit across the felt, so the middle -- and their bet -- is below them. */
  stakeBelow: boolean;
}) {
  const out = seat.folded || seat.sitting_out;
  const stake = seat.committed + seat.side_stake;
  const note = seat.sitting_out
    ? "sitting out"
    : seat.all_in
      ? "all in"
      : seat.folded
        ? backing
          ? `behind ${backing}`
          : "folded"
        : null;

  return (
    <div
      className={cn(
        "bg-card/95 relative w-20 rounded-xl border px-2 py-1.5 shadow-lg backdrop-blur-sm transition-colors sm:w-28",
        onTheClock && "border-primary ring-primary/40 ring-2",
        out && "opacity-60",
      )}
    >
      <div className="flex items-center gap-1">
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium sm:text-sm">
          {name}
          {isMe ? <span className="text-muted-foreground"> (you)</span> : null}
        </span>
        {seat.is_correct === true ? (
          <Crown className="size-3 shrink-0 text-amber-500" aria-label="Right" />
        ) : null}
        {stage === "answering" && seat.has_answered ? (
          <Check className="text-success size-3 shrink-0" aria-label="Answered" />
        ) : null}
      </div>

      <div className="flex items-baseline gap-1">
        <span className="font-mono text-sm font-semibold tabular-nums sm:text-lg">
          {seat.stack}
        </span>
        {seat.won > 0 ? (
          <span className="text-success font-mono text-[10px]">+{seat.won}</span>
        ) : null}
      </div>

      {/* Comparative, not absolute: the bar answers "who is ahead", which the
          numbers alone make you work out. */}
      <div className="bg-muted h-1 overflow-hidden rounded-full">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            out ? "bg-muted-foreground/40" : "bg-primary",
          )}
          style={{ width: `${Math.min(100, (seat.stack / biggest) * 100)}%` }}
        />
      </div>

      {note ? (
        <p className="text-muted-foreground truncate text-[9px] sm:text-[10px]">
          {note}
        </p>
      ) : null}

      {/* On the corner of the plaque rather than in the row of badges: a dealer
          button sits *by* a player, not among the things they did this hand. */}
      {isDealer ? (
        <span
          className="bg-foreground text-background absolute -top-1.5 -left-1.5 flex size-4 items-center justify-center rounded-full text-[9px] font-bold shadow"
          title="Dealer"
        >
          D
        </span>
      ) : null}

      {stake > 0 ? (
        <span
          className={cn(
            "absolute left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-full",
            "bg-amber-400 px-1.5 py-0.5 font-mono text-[10px] font-semibold tabular-nums text-amber-950 shadow",
            stakeBelow ? "top-full mt-1" : "bottom-full mb-1",
          )}
        >
          <Coins className="size-2.5" aria-hidden />
          {stake}
        </span>
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
