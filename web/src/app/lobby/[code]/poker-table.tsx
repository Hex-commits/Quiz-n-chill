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
 * Chips are the thing to be able to read at a glance, so every pile is drawn
 * three ways at once. The number is exact. The bar is comparative -- who is
 * ahead is a question about the other stacks, and answering it by reading four
 * numbers is slower than seeing four bars. And the number is *set at the size
 * of the pile it counts*, so a big stack and a fat pot are literally bigger on
 * the felt than a short stack and an opening bet. See `chipScale`.
 *
 * Holds no rules. Every legality question -- whose turn, what a raise has to
 * be, whether an answer counts -- is settled by the API; this file draws what
 * came back and posts what was clicked.
 */

import { useEffect, useRef, useState } from "react";
import { Check, ChevronsUp, Coins, Crown, Flame, Loader2, X } from "lucide-react";

/** Tenths of a pot a run is worth, capped. Mirrors `poker.STREAK_TENTHS`. */
const STREAK_TENTHS = 3;

import { AnswerPool } from "@/components/answer-pool";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { HURRY_FROM, play, playCountdown } from "@/lib/sound";
import { cn } from "@/lib/utils";
import type { LobbyView, PokerAction, PokerSeat, PokerView } from "@/lib/types";

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

/**
 * The size each chip readout shrinks to when it is the smallest pile at the
 * table, as a fraction of the size it is drawn at when it is the biggest.
 *
 * One floor per readout, because "still legible" is not one number: a pot set
 * at forty pixels can give up half of itself and still be the loudest thing on
 * the felt, while a bet already drawn on a pill has almost nothing to give.
 */
const CHIP_FLOOR = { pot: 0.5, stack: 0.62, bet: 0.82 };

/**
 * How big to draw a pile of chips, against the biggest pile at the table.
 *
 * Square-rooted rather than taken straight off the ratio. Stacks at a table run
 * over an order of magnitude, and a linear scale would draw a player on their
 * last hundred as an unreadable speck long before they were actually out of the
 * game. The root keeps the small end readable while still saying, at a glance
 * and without anybody reading a digit, who is deep and who is nearly out.
 */
function chipScale(amount: number, biggest: number, floor: number) {
  const share = Math.sqrt(Math.min(1, Math.max(0, amount) / Math.max(biggest, 1)));
  return floor + (1 - floor) * share;
}

/** A font size for `amount`, against the `--chip-base` set on the element. */
function chipFont(amount: number, biggest: number, floor: number) {
  return { fontSize: `calc(var(--chip-base) * ${chipScale(amount, biggest, floor)})` };
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
        {/* An open-end table has no "of": it is over when one player has the
            chips, and a total drawn from the question pool would be a promise
            about the length of the game that nothing keeps. */}
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Hand {poker.hand_index + 1}
          {poker.open_end
            ? ` · ${poker.seats.filter((seat) => seat.stack > 0).length} left in`
            : ` of ${poker.hand_count}`}
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
        <Felt poker={poker} biggest={biggest} />
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
    if (!value) return;

    play(rung >= 3 ? "reveal" : "step");
    /* Raising the curtain *is* the reaction to a view arriving, and the sound
       above it cannot happen during a render. Adjusting state in render, as the
       count-in does, is not available to something that also has to make a
       noise. */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurtain({ rung, term: CURTAIN_TERM[rung], value });
  }, [poker.hand_index, poker.stage, rung, value]);

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
      <p className="animate-quiz-count-in text-primary max-w-4xl text-center text-4xl leading-none font-black text-balance sm:text-6xl">
        {curtain.value}
      </p>
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
function Felt({ poker, biggest }: { poker: PokerView; biggest: number }) {
  const revealed = REVEALED[poker.stage];

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
          {/* The pot is a pile like any other, and on the first bet of a hand
              it is the smallest one on the table. It should look it -- and it
              should be seen to grow, so the figure is keyed on itself and every
              call, raise and blind that lands replays the swell. */}
          <span
            key={poker.pot}
            className="animate-quiz-zoom font-mono font-bold tabular-nums [--chip-base:2rem] sm:[--chip-base:2.75rem]"
            style={chipFont(poker.pot, biggest, CHIP_FLOOR.pot)}
          >
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
            up={revealed >= 3}
            wide
          />
        </div>
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
 *
 * Always words, never a photograph. The pictures on a picture round belong to
 * the categories, and the categories are what the table picks between -- so
 * they come out under the felt with the rest of the answers, not on it.
 */
function BoardCard({
  term,
  value,
  up,
  wide,
}: {
  term: string;
  value: string | null;
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
          <span
            className={cn(
              "leading-tight font-semibold text-balance",
              wide ? "text-[11px] sm:text-sm" : "text-[8px] sm:text-[11px]",
            )}
          >
            {value}
          </span>
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
        "bg-card/95 relative w-20 rounded-xl border px-2 py-1.5 shadow-lg backdrop-blur-sm sm:w-28",
        /* Named rather than `all`: the glow below drives `box-shadow`, and a
           transition on the same property fights the animation for it. */
        "ease-(--ease-soft) transition-[opacity,border-color,background-color] duration-300",
        onTheClock && "border-primary ring-primary/40 ring-2",
        out && "opacity-60",
      )}
    >
      {/* A check moves no chips, so the only thing it changes is whose plaque
          is breathing -- which has to carry across the felt. On a layer of its
          own because the pulse is a `box-shadow`, and the plaque composes its
          ring and its lift out of that same property. */}
      {onTheClock ? (
        <span
          className="animate-quiz-glow pointer-events-none absolute inset-0 rounded-xl"
          aria-hidden
        />
      ) : null}

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
        <span
          className="font-mono leading-none font-semibold tabular-nums [--chip-base:1.125rem] sm:[--chip-base:1.5rem]"
          style={chipFont(seat.stack, biggest, CHIP_FLOOR.stack)}
        >
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

      {/* The opposite corner, and for the same reason the dealer button is on
          one: a run is a standing fact about a player, not one of the things
          they did this hand. The numeral is what the next side bet pays, in
          tenths of a pot -- the multiplier itself rather than a count of what
          got them there, which is the number they are deciding on. */}
      {seat.side_streak > 0 ? (
        <span
          key={seat.side_streak}
          className={cn(
            "animate-quiz-pop absolute -top-1.5 -right-1.5 flex items-center gap-px rounded-full",
            "bg-amber-400 px-1 py-0.5 font-mono text-[9px] font-bold text-amber-950 shadow",
          )}
          title={`${seat.side_streak} side bets in a row`}
        >
          <Flame className="size-2.5" aria-hidden />×
          {Math.min(seat.side_streak + 1, STREAK_TENTHS)}
        </span>
      ) : null}

      {/* Two spans, because the pop animates `transform` and the placing of
          the pill is a transform too -- one element doing both loses its
          centring for the length of every bet. The outer one holds it in
          place; the inner one is what moves. */}
      {stake > 0 ? (
        <span
          className={cn(
            "absolute left-1/2 -translate-x-1/2",
            stakeBelow ? "top-full mt-1" : "bottom-full mb-1",
          )}
        >
          <span
            key={stake}
            className={cn(
              "animate-quiz-pop flex items-center gap-0.5 rounded-full",
              "bg-amber-400 px-1.5 py-0.5 font-mono font-semibold tabular-nums text-amber-950 shadow",
              "[--chip-base:0.8125rem]",
            )}
            style={chipFont(stake, biggest, CHIP_FLOOR.bet)}
          >
            {/* Sized in `em`, so the coin grows with the number beside it and
                the whole pill reads as one bet rather than as an icon and a
                figure. */}
            <Coins className="size-[1em]" aria-hidden />
            {stake}
          </span>
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
  /* Which button was pressed. `busy` already says a move is in flight but not
     which one, and which one is the whole job here: it is what lets every move
     you did *not* take go grey. Read through `busy` rather than cleared when
     the move settles, so a press that fails leaves nothing behind. */
  const [pressed, setPressed] = useState<string | null>(null);
  const pending = busy ? pressed : null;

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

  /* Each move as a glyph, a tone and a figure -- never a sentence. The two that
     spend nothing are drawn as outlines, meeting a bet takes the primary fill,
     and going all in takes the amber that is already the colour of chips pushed
     forward on this table. */
  const moves = [
    {
      key: "fold",
      icon: X,
      label: "Fold",
      amount: null,
      variant: "outline" as const,
      tone: "text-muted-foreground hover:border-destructive/50 hover:bg-destructive/5 hover:text-destructive",
      run: () => onAct("fold"),
    },
    owed > 0
      ? {
          key: "call",
          icon: Coins,
          label: "Call",
          amount: Math.min(owed, me.stack),
          variant: "default" as const,
          tone: "",
          run: () => onAct("call"),
        }
      : {
          key: "check",
          icon: Check,
          label: "Check",
          amount: null,
          variant: "outline" as const,
          tone: "",
          run: () => onAct("check"),
        },
    ...raises.map((size) => ({
      key: `raise-${size}`,
      icon: ChevronsUp,
      label: "Raise",
      amount: size,
      variant: "secondary" as const,
      tone: "",
      run: () => onAct("raise", size),
    })),
    {
      key: "all-in",
      icon: Flame,
      label: "All in",
      amount: max,
      variant: "secondary" as const,
      tone: "bg-amber-400 text-amber-950 hover:bg-amber-300 dark:bg-amber-400 dark:text-amber-950",
      run: () => onAct("all_in"),
    },
  ];

  const locked = busy || pending !== null;

  return (
    <Card className="animate-quiz-rise">
      <CardContent className="space-y-2">
        {poker.stage === "turn" ? (
          <p className="text-muted-foreground text-center text-xs">
            The answers come out once this betting round is done.
          </p>
        ) : null}
        <div className="flex flex-wrap items-stretch justify-center gap-2 sm:gap-2.5">
          {moves.map((move) => (
            <Act
              key={move.key}
              icon={move.icon}
              label={move.label}
              amount={move.amount}
              variant={move.variant}
              tone={move.tone}
              chosen={pending === move.key}
              dimmed={locked && pending !== move.key}
              onClick={() => {
                setPressed(move.key);
                move.run();
              }}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * One move, as a chip the size of an answer.
 *
 * The same object the answers are picked from -- lift on hover, press on click,
 * a shine across it -- because both are the one decision the table is waiting
 * on, and there is no reason for them to be different objects.
 *
 * Three states, and none of them is written down. Idle. The one you pressed,
 * which lifts, outlines itself and spins where its glyph was. And every other
 * one, which goes flat, grey and colourless the moment you press anything. The
 * greying is the half that says the click landed: a spinner alone in a row of
 * live buttons reads as a screen still waiting to be told what to do.
 */
function Act({
  icon: Icon,
  label,
  amount,
  variant,
  tone,
  chosen,
  dimmed,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  /** What it costs, or null where the move spends nothing. */
  amount: number | null;
  variant: "default" | "outline" | "secondary";
  /** Colour this move and no other. */
  tone: string;
  /** The one that was pressed. */
  chosen: boolean;
  /** One of the ones that was not, while a move is in flight. */
  dimmed: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      size="lg"
      variant={variant}
      className={cn(
        "quiz-shine ease-(--ease-soft) h-auto min-h-12 grow basis-24 gap-1.5 px-4 py-2.5",
        "text-base font-semibold transition-all duration-200 sm:grow-0",
        tone,
        !chosen &&
          !dimmed &&
          "hover:z-10 hover:-translate-y-0.5 hover:scale-[1.03] hover:shadow-lg active:translate-y-0 active:scale-[0.98] active:duration-75",
        /* Held at full strength against the base `disabled:opacity-50`: the
           pressed button is the one thing on the bar that must not go grey. */
        chosen &&
          "animate-quiz-zoom outline-primary z-10 scale-[1.03] shadow-lg outline-2 outline-offset-2 outline-solid disabled:opacity-100",
        dimmed && "scale-[0.98] opacity-40 saturate-0 shadow-none disabled:opacity-40",
      )}
      disabled={chosen || dimmed}
      onClick={onClick}
    >
      {chosen ? (
        <Loader2 className="size-4 animate-spin" aria-hidden />
      ) : (
        <Icon className="size-4" aria-hidden />
      )}
      {label}
      {amount !== null ? (
        <span className="font-mono font-bold tabular-nums">{amount}</span>
      ) : null}
    </Button>
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
  const [pressed, setPressed] = useState<string | null>(null);
  const pending = busy ? pressed : null;

  if (me.backing) {
    return (
      <Waiting>
        You are behind {nameOf(me.backing)} for {me.side_stake}. A share of
        whatever pot they take is yours -- paid by the pot, not by them.
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
        <p className="flex items-center gap-1.5 text-sm">
          You folded. Put {poker.big_blind} behind someone still in it?
          {me.side_streak > 0 ? (
            <span className="flex items-center gap-0.5 font-mono font-bold text-amber-500">
              <Flame className="size-3.5" aria-hidden />×
              {Math.min(me.side_streak + 1, STREAK_TENTHS)}
            </span>
          ) : null}
        </p>
        <p className="text-muted-foreground text-xs">
          They answer right and your stake comes back with a share of the pot,
          split with anyone else who backed a winner: a tenth of it, two tenths
          on a second call in a row, three on a third and after. Wrong, and the
          stake joins the pot for whoever does take it and your run starts over.
          It costs them nothing either way -- money on them buys them the bigger
          half of a pot they have to split.
        </p>
        {/* The same chips the betting bar is made of, and the same answer to a
            click: the one you picked lights up, the rest go out. */}
        <div className="flex flex-wrap justify-center gap-2 sm:gap-2.5">
          {candidates.map((seat) => (
            <Act
              key={seat.player_id}
              icon={Coins}
              label={nameOf(seat.player_id)}
              amount={poker.big_blind}
              variant="outline"
              tone=""
              chosen={pending === seat.player_id}
              dimmed={
                (busy || pending !== null) && pending !== seat.player_id
              }
              onClick={() => {
                setPressed(seat.player_id);
                onBack(seat.player_id);
              }}
            />
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
            Where does {poker.question?.label ?? "it"} belong?
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
