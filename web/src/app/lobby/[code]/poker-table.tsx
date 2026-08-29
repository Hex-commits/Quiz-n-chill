"use client";

/**
 * The poker table: five cards that say more about the question each time one
 * turns over, and the betting that happens in between.
 *
 * The layout follows the reveal rather than the poker. Board and ladder sit
 * together at the top, because the whole point of a card here is the line it
 * fills in underneath: flop → subject, turn → topic, river → the question and
 * the answers it can be given. Chips, seats and the action bar sit below that,
 * where they can be read without taking the eye off what is being asked.
 *
 * Holds no rules. Every legality question — whose turn, what a raise has to be,
 * whether an answer counts — is settled by the API; this file draws what came
 * back and posts what was clicked.
 */

import { useState } from "react";
import { Check, Circle, Coins, Crown, Loader2 } from "lucide-react";

import { CategoryPicture, ImageCredit } from "@/components/category-image";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { LobbyView, PokerAction, PokerSeat, PokerView } from "@/lib/types";

/**
 * How many rungs of the ladder each stage has lit.
 *
 * Capped at three rather than indexed off the stage, because the question stays
 * on screen for the two stages after the river deals it -- answering it and
 * paying it out are exactly when it is being read.
 */
const REVEALED: Record<PokerView["stage"], number> = {
  preflop: 0,
  flop: 1,
  turn: 2,
  river: 3,
  answering: 3,
  payout: 3,
};

const SUITS: Record<string, { glyph: string; red: boolean }> = {
  s: { glyph: "♠", red: false },
  h: { glyph: "♥", red: true },
  d: { glyph: "♦", red: true },
  c: { glyph: "♣", red: false },
};

export function PokerTable({
  lobby,
  poker,
  playerId,
  cards,
  busy,
  onAct,
  onAnswer,
}: {
  lobby: LobbyView;
  poker: PokerView;
  playerId: string;
  /** The asking player's own two cards, fetched per hand. */
  cards: string[];
  busy: boolean;
  onAct: (action: PokerAction, amount?: number) => void;
  onAnswer: (itemId: string) => void;
}) {
  const me = poker.seats.find((seat) => seat.player_id === playerId) ?? null;
  const nameOf = (id: string) =>
    lobby.players.find((player) => player.id === id)?.nickname ?? "—";

  const revealed = REVEALED[poker.stage];
  const over = poker.stage === "payout";

  return (
    <div className="mx-auto w-full max-w-5xl space-y-3">
      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Hand {poker.hand_index + 1} of {poker.hand_count}
            </p>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="gap-1.5 font-mono">
                <Coins className="size-3.5" aria-hidden />
                {poker.pot}
              </Badge>
              {poker.carried > 0 ? (
                <Badge variant="outline" className="font-mono">
                  {poker.carried} carried
                </Badge>
              ) : null}
              {poker.seconds_left !== null ? (
                <Badge variant="outline" className="font-mono tabular-nums">
                  {poker.seconds_left}s
                </Badge>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            {[0, 1, 2, 3, 4].map((index) => (
              <PlayingCard key={index} card={poker.board[index] ?? null} />
            ))}
          </div>

          <dl className="mx-auto grid max-w-md gap-1 text-sm">
            <Rung term="Subject" value={poker.subject_name} lit={revealed >= 1} />
            <Rung term="Topic" value={poker.title} lit={revealed >= 2} />
            <Rung
              term="Question"
              value={
                poker.question
                  ? (poker.question.label ?? "the picture below")
                  : null
              }
              lit={revealed >= 3}
            />
          </dl>

          {poker.question?.image ? (
            <figure className="mx-auto w-full max-w-sm space-y-1">
              <div className="overflow-hidden rounded-(--radius-sm)">
                <CategoryPicture
                  image={poker.question.image}
                  label={poker.question.label ?? "The question"}
                />
              </div>
              <figcaption>
                <ImageCredit image={poker.question.image} />
              </figcaption>
            </figure>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-2 sm:grid-cols-2">
          {poker.seats.map((seat) => (
            <Seat
              key={seat.player_id}
              seat={seat}
              name={nameOf(seat.player_id)}
              isMe={seat.player_id === playerId}
              isDealer={seat.player_id === poker.button_id}
              onTheClock={seat.player_id === poker.to_act}
              stage={poker.stage}
            />
          ))}
        </CardContent>
      </Card>

      {me && me.has_cards ? (
        <div className="flex items-center justify-center gap-2">
          {cards.length > 0 ? (
            cards.map((card) => <PlayingCard key={card} card={card} />)
          ) : (
            <>
              <PlayingCard card={null} />
              <PlayingCard card={null} />
            </>
          )}
        </div>
      ) : null}

      {over && poker.result ? (
        <Payout poker={poker} nameOf={nameOf} />
      ) : poker.stage === "answering" ? (
        <Answering
          poker={poker}
          me={me}
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
        />
      )}
    </div>
  );
}

/**
 * One line of the ladder: what this card said, or a dash where it has not been
 * turned over yet.
 *
 * The unlit rungs stay on screen rather than appearing as they fill. Knowing
 * that two more things are still to be told is part of what a bet before the
 * flop is made on.
 */
function Rung({
  term,
  value,
  lit,
}: {
  term: string;
  value: string | null;
  lit: boolean;
}) {
  return (
    <div className="flex items-baseline gap-3">
      <dt className="text-muted-foreground w-20 shrink-0 text-xs tracking-wide uppercase">
        {term}
      </dt>
      <dd
        className={cn(
          "min-w-0 truncate",
          lit && value ? "font-medium" : "text-muted-foreground/50",
        )}
      >
        {lit && value ? value : "—"}
      </dd>
    </div>
  );
}

/** A card, or its back where one has not been dealt. */
function PlayingCard({ card }: { card: string | null }) {
  if (!card) {
    return (
      <div
        className="bg-muted/60 border-border h-16 w-11 rounded-md border border-dashed"
        aria-label="Face down"
      />
    );
  }

  const suit = SUITS[card.slice(-1)] ?? { glyph: "?", red: false };
  const rank = card.slice(0, -1).replace("T", "10");
  return (
    <div
      className={cn(
        "bg-card flex h-16 w-11 flex-col items-center justify-center rounded-md border shadow-sm",
        suit.red ? "text-red-600 dark:text-red-400" : "text-foreground",
      )}
      aria-label={`${rank}${suit.glyph}`}
    >
      <span className="text-lg leading-none font-bold">{rank}</span>
      <span className="text-lg leading-none">{suit.glyph}</span>
    </div>
  );
}

function Seat({
  seat,
  name,
  isMe,
  isDealer,
  onTheClock,
  stage,
}: {
  seat: PokerSeat;
  name: string;
  isMe: boolean;
  isDealer: boolean;
  onTheClock: boolean;
  stage: PokerView["stage"];
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-(--radius-sm) border px-3 py-2 text-sm",
        onTheClock && "border-primary/60 bg-primary/5",
        (seat.folded || seat.sitting_out) && "opacity-50",
      )}
    >
      <span className="truncate font-medium">
        {name}
        {isMe ? " (you)" : ""}
      </span>
      {isDealer ? (
        <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
          D
        </Badge>
      ) : null}
      {seat.sitting_out ? (
        <span className="text-muted-foreground text-xs">out</span>
      ) : seat.folded ? (
        <span className="text-muted-foreground text-xs">folded</span>
      ) : seat.all_in ? (
        <span className="text-xs font-medium">all in</span>
      ) : null}
      {stage === "answering" && seat.has_answered ? (
        <Check className="text-success size-3.5" aria-label="Answered" />
      ) : null}
      {seat.is_correct === true ? (
        <Crown className="size-3.5 text-amber-500" aria-label="Right" />
      ) : null}
      <span className="ml-auto flex items-center gap-2 font-mono tabular-nums">
        {seat.committed > 0 ? (
          <span className="text-muted-foreground text-xs">
            +{seat.committed}
          </span>
        ) : null}
        {seat.won > 0 ? (
          <span className="text-success text-xs">+{seat.won}</span>
        ) : null}
        {seat.stack}
      </span>
    </div>
  );
}

/**
 * The betting bar.
 *
 * Raise sizes are offered as buttons rather than a field. A field on a phone is
 * a keyboard over the board and a number to think of while a clock runs; the
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
}: {
  poker: PokerView;
  me: PokerSeat | null;
  playerId: string;
  nameOf: (id: string) => string;
  busy: boolean;
  onAct: (action: PokerAction, amount?: number) => void;
}) {
  if (!me || me.sitting_out || me.folded) {
    return (
      <Waiting>
        {me?.folded
          ? "You folded. Watching this one out."
          : "Sitting this hand out."}
      </Waiting>
    );
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
  const minRaise = poker.current_bet + poker.min_raise;
  const potRaise = poker.current_bet + poker.pot;
  const raises = [minRaise, potRaise].filter(
    (size, index, all) => size < max && all.indexOf(size) === index,
  );

  return (
    <Card>
      <CardContent className="space-y-2">
        {/* Said once, on the street where the board looks unfinished: the
            question is up but nothing to answer it with is. */}
        {poker.stage === "river" ? (
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
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => onAct("all_in")}
        >
          All in {max}
        </Button>
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
 * picks, the second commits, and after that the choice is the server's — it
 * comes back only when the hand pays out.
 */
function Answering({
  poker,
  me,
  seconds,
  busy,
  onAnswer,
}: {
  poker: PokerView;
  me: PokerSeat | null;
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
        Out of this one. {answered} of {answering} have answered.
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
          value={((poker.seconds_left ?? 0) / Math.max(seconds, 1)) * 100}
          className="h-1.5"
        />
        <div className="flex flex-wrap gap-2">
          {poker.options.map((option) => (
            <Button
              key={option.id}
              variant={picked === option.id ? "default" : "outline"}
              size="sm"
              onClick={() => setPicked(option.id)}
            >
              {option.label}
            </Button>
          ))}
        </div>
        <Button
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
}: {
  poker: PokerView;
  nameOf: (id: string) => string;
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

        <p className="text-muted-foreground flex items-center gap-2 text-xs">
          <Circle className="size-3 animate-pulse" aria-hidden />
          Next hand in {poker.seconds_left ?? 0}s
        </p>
      </CardContent>
    </Card>
  );
}

function Waiting({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-muted-foreground py-2 text-center text-sm">{children}</p>
  );
}
