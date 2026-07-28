"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Check,
  Crown,
  History,
  Loader2,
  LogOut,
  Timer,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { ApiErrorNotice } from "@/components/api-error-notice";
import { SoundToggle } from "@/components/sound-toggle";
import { DifficultyBadge, SourceLink } from "@/components/source-link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  getLobby,
  leaveLobby,
  markAway,
  restartLobby,
  skipReview,
  startGame,
  submitTurn,
} from "@/lib/api";
import { forgetPlayer, recallPlayer } from "@/lib/identity";
import { subscribeToLobby } from "@/lib/realtime";
// Aliased: this file already has a `play(categoryId)` that places an answer.
// Both take a string, so an unaliased import shadows silently and every cue
// becomes an attempt to place the selected item into a category called
// "yourTurn".
import { play as playCue, unlock } from "@/lib/sound";
import { deadlineFrom, reconcileDeadline, useCountdown } from "@/lib/use-countdown";
import type { LobbyView, ResolvedPair, Subject } from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { cn } from "@/lib/utils";

import { RejoinForm } from "./rejoin-form";

// The heartbeat, and the backstop for anything push misses -- not how changes
// are normally learned. Was 1500ms when polling *was* the mechanism, then 10s
// while the store was a cache that billed per command. Neither constraint
// applies now: the store is Postgres and nothing meters round trips.
//
// Tied to PRESENCE_TIMEOUT on the server (15s), which must stay comfortably
// above this or players get marked disconnected between beats.
const POLL_MS = 4_000;

const ROUND_CHOICES = [3, 5, 7, 10];

// Bounded to match `LobbyStart.turn_seconds` on the server (10–120). Below ten
// nobody can read a board of eight pairs; above two minutes it stops being a
// timer.
const TURN_CHOICES = [15, 30, 45, 60];

export function LobbyRoom({
  code,
  subjects,
}: {
  code: string;
  subjects: Subject[];
}) {
  const router = useRouter();
  const playerId = useStored<string | null>(() => recallPlayer(code), null);
  const [lobby, setLobby] = useState<LobbyView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [chosenSubjects, setChosenSubjects] = useState<string[]>(
    subjects.slice(0, 3).map((subject) => subject.slug),
  );
  const [roundCount, setRoundCount] = useState(5);
  const [turnSeconds, setTurnSeconds] = useState(30);

  // Polling and turn submission race: a poll started before a turn can land
  // after it and show pre-turn state. Applying only newer versions fixes it.
  const versionRef = useRef(-1);

  // Both clocks are held as wall-clock deadlines and ticked in the browser.
  // The server sends how many seconds are left as of the moment it answered;
  // rendering that directly means the number only moves when a request happens,
  // which is what made the review countdown appear frozen. See useCountdown.
  const [reviewDeadline, setReviewDeadline] = useState<number | null>(null);
  const [turnDeadline, setTurnDeadline] = useState<number | null>(null);

  const apply = useCallback((view: LobbyView) => {
    if (view.version < versionRef.current) return;
    versionRef.current = view.version;
    setLobby(view);
    // Turned into wall-clock deadlines so the countdowns can tick without
    // asking again -- but only adopted when the server is saying something new.
    // Re-pinning them on every poll makes the displayed number stall, because
    // each answer is rounded up and arrives slightly stale. See
    // `reconcileDeadline`.
    setReviewDeadline((current) =>
      reconcileDeadline(current, deadlineFrom(view.review_seconds_left)),
    );
    setTurnDeadline((current) =>
      reconcileDeadline(current, deadlineFrom(view.turn_seconds_left)),
    );
  }, []);

  const refresh = useCallback(async () => {
    try {
      // Passing the player id makes this double as a heartbeat, which is why
      // the interval below still runs even though changes now arrive by push.
      const view = await getLobby(code, playerId);
      apply(view);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unknown error");
    }
  }, [code, playerId, apply]);

  useEffect(() => {
    // `refresh` is async: its setState happens in a promise continuation, not
    // synchronously in this effect body, which is the case the rule is aimed
    // at. There is no way to express that to the linter.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();

    // Push is how a change is normally learned: the API publishes one message
    // per actual change and this fetches once in response. The payload is
    // ignored on purpose -- it carries only a version, and the API remains the
    // only thing that decides what this player may see.
    const unsubscribe = subscribeToLobby(code, () => {
      void refresh();
    });

    // Still polling, at a fraction of the old rate, for two reasons that both
    // survive a working socket: it is the heartbeat that keeps this player
    // marked present, and it is the backstop if a message is missed or realtime
    // is not configured at all.
    const timer = setInterval(() => void refresh(), POLL_MS);

    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, [code, refresh]);

  // Reaching zero has to *do* something. The server acts on either deadline
  // only when a request arrives and finds it passed -- nothing runs on a timer
  // there, and on serverless nothing can. Without this poke the round would sit
  // finished, or a stalled player keep the turn, until the next poll.
  //
  // Every client pokes at once and the store's lock sorts it out: one request
  // moves the game on and the rest read the result.
  const poke = useCallback(() => void refresh(), [refresh]);

  const secondsLeft = useCountdown(reviewDeadline, poke);
  const turnSecondsLeft = useCountdown(turnDeadline, poke);

  // Closing or backgrounding the tab hands the turn on immediately instead of
  // making everyone wait out the server's presence timeout. `pagehide` fires
  // where `beforeunload` does not, notably on mobile Safari. Coming back is
  // handled by the next poll, which re-checks the player in.
  useEffect(() => {
    if (!playerId) return;

    const onHide = () => markAway(code, playerId);
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [code, playerId]);

  const me = lobby?.players.find((player) => player.id === playerId) ?? null;
  const isMyTurn = Boolean(playerId && lobby?.current_player_id === playerId);

  // --- Sound cues ----------------------------------------------------------
  //
  // Fired from transitions rather than from state, so a poll that re-delivers
  // the same lobby is silent. Everything is compared in refs: a cue is a side
  // effect on the world, not a piece of React state, and storing it as state
  // would re-render the room to play a note.
  const primed = useRef(false);
  const lastMove = useRef<string | null>(null);
  const wasMyTurn = useRef(false);
  const lastStatus = useRef<string | null>(null);

  useEffect(() => {
    if (!lobby) return;

    const moveKey = lobby.last_move
      ? `${lobby.version}:${lobby.last_move.item_label}`
      : null;

    // The first view is the state of the world on arrival, not a series of
    // things that just happened -- joining a game in progress should not
    // replay its history at you.
    if (!primed.current) {
      primed.current = true;
      lastMove.current = moveKey;
      wasMyTurn.current = isMyTurn;
      lastStatus.current = lobby.status;
      return;
    }

    if (moveKey && moveKey !== lastMove.current) {
      playCue(lobby.last_move!.was_correct ? "correct" : "wrong");
    }
    lastMove.current = moveKey;

    if (isMyTurn && !wasMyTurn.current) playCue("yourTurn");
    wasMyTurn.current = isMyTurn;

    if (lobby.status !== lastStatus.current) {
      if (lobby.status === "reviewing") playCue("roundEnd");
      if (lobby.status === "finished") playCue("gameEnd");
      lastStatus.current = lobby.status;
    }
  }, [lobby, isMyTurn]);

  // The closing seconds, and only for the player they belong to -- everyone
  // else is watching, and a clock ticking for somebody else's turn is noise.
  useEffect(() => {
    if (!isMyTurn) return;
    if (turnSecondsLeft === null || turnSecondsLeft <= 0 || turnSecondsLeft > 5) {
      return;
    }
    playCue("tick");
  }, [turnSecondsLeft, isMyTurn]);

  // Lets the host see when they have asked for more rounds than the chosen
  // subjects can supply, rather than silently getting a shorter game.
  const availableQuestions = subjects
    .filter((subject) => chosenSubjects.includes(subject.slug))
    .reduce((total, subject) => total + subject.quiz_count, 0);

  async function act(fn: () => Promise<LobbyView>) {
    // Every path through here starts with a click, which is the only moment a
    // browser will let an AudioContext start. Doing it here means the first cue
    // of the game is audible rather than swallowed.
    unlock();
    setBusy(true);
    try {
      apply(await fn());
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    if (!playerId) return;
    setBusy(true);
    try {
      await leaveLobby(code, playerId);
    } catch {
      // Leaving is best-effort: if the call fails the lobby may already be
      // gone. Either way this browser is done with it, so drop the identity
      // rather than trapping the player on a dead screen.
    } finally {
      forgetPlayer(code);
      router.push("/play");
    }
  }

  function play(categoryId: string) {
    if (!playerId || !selectedItemId) return;
    const itemId = selectedItemId;
    setSelectedItemId(null);
    act(() => submitTurn(code, playerId, itemId, categoryId));
  }

  // --- Guards --------------------------------------------------------------

  if (error && !lobby) return <ApiErrorNotice message={error} />;

  // Loading is checked before identity on purpose: `playerId` reads null during
  // the server render, so testing it first would flash "not in this lobby"
  // before hydration supplies the real value.
  if (!lobby) {
    return (
      <p className="text-muted-foreground flex items-center gap-2 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading lobby {code}…
      </p>
    );
  }

  // No identity in this browser: either a newcomer or someone returning on a
  // different device. Both are handled by rejoining with a nickname.
  if (!playerId) return <RejoinForm code={code} />;

  // --- Shared header -------------------------------------------------------

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-muted-foreground text-sm">Lobby code</p>
        <p className="font-mono text-3xl font-bold tracking-widest">
          {lobby.code}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="gap-1.5">
          <Users className="size-3.5" aria-hidden />
          {lobby.players.length}{" "}
          {lobby.players.length === 1 ? "player" : "players"}
        </Badge>
        <SoundToggle />
        <Button variant="ghost" size="sm" onClick={leave} disabled={busy}>
          <LogOut className="size-4" aria-hidden />
          Leave
        </Button>
      </div>
    </div>
  );

  // --- Waiting room --------------------------------------------------------

  if (lobby.status === "lobby") {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        {header}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Players</CardTitle>
            <CardDescription>
              Share the code above. The game starts when the host is ready.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {lobby.players.map((player) => (
              <div key={player.id} className="flex items-center gap-2 text-sm">
                <span
                  className={cn(
                    "font-medium",
                    !player.is_connected && "text-muted-foreground",
                  )}
                >
                  {player.nickname}
                </span>
                {player.is_host ? (
                  <Badge variant="secondary" className="gap-1">
                    <Crown className="size-3" aria-hidden />
                    Host
                  </Badge>
                ) : null}
                {!player.is_connected ? (
                  <Badge variant="outline" className="gap-1">
                    <WifiOff className="size-3" aria-hidden />
                    Offline
                  </Badge>
                ) : null}
                {player.id === playerId ? (
                  <span className="text-muted-foreground">(you)</span>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>

        {me?.is_host ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Pick the subjects</CardTitle>
              <CardDescription>
                Questions are drawn at random from whatever you choose, spread
                as evenly as possible across them.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                {subjects.map((subject) => (
                  <div key={subject.slug} className="flex items-start gap-3">
                    <Checkbox
                      id={subject.slug}
                      checked={chosenSubjects.includes(subject.slug)}
                      onCheckedChange={(checked) =>
                        setChosenSubjects((current) =>
                          checked
                            ? [...current, subject.slug]
                            : current.filter((slug) => slug !== subject.slug),
                        )
                      }
                    />
                    <Label htmlFor={subject.slug} className="font-normal">
                      {subject.name}
                      <span className="text-muted-foreground">
                        {" "}
                        · {subject.quiz_count}
                      </span>
                    </Label>
                  </div>
                ))}
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Rounds</Label>
                <div className="flex flex-wrap gap-2">
                  {ROUND_CHOICES.map((n) => (
                    <Button
                      key={n}
                      type="button"
                      size="sm"
                      variant={roundCount === n ? "default" : "outline"}
                      aria-pressed={roundCount === n}
                      onClick={() => setRoundCount(n)}
                    >
                      {n}
                    </Button>
                  ))}
                </div>
                {roundCount > availableQuestions ? (
                  <p className="text-muted-foreground text-sm">
                    Only {availableQuestions} question
                    {availableQuestions === 1 ? "" : "s"} available in the
                    chosen subjects — the game will be that short.
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <Label>Seconds per turn</Label>
                <div className="flex flex-wrap gap-2">
                  {TURN_CHOICES.map((n) => (
                    <Button
                      key={n}
                      type="button"
                      size="sm"
                      variant={turnSeconds === n ? "default" : "outline"}
                      aria-pressed={turnSeconds === n}
                      onClick={() => setTurnSeconds(n)}
                    >
                      {n}s
                    </Button>
                  ))}
                </div>
                <p className="text-muted-foreground text-sm">
                  Run out of time and you are out for the round, the same as a
                  wrong answer.
                </p>
              </div>
            </CardContent>
            <CardFooter>
              <Button
                onClick={() =>
                  playerId &&
                  act(() =>
                    startGame(
                      code,
                      playerId,
                      chosenSubjects,
                      roundCount,
                      turnSeconds,
                    ),
                  )
                }
                disabled={
                  busy || chosenSubjects.length === 0 || lobby.players.length < 2
                }
              >
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Start game
              </Button>
            </CardFooter>
          </Card>
        ) : (
          <p className="text-muted-foreground text-sm">
            Waiting for the host to start…
          </p>
        )}

        {lobby.players.length < 2 ? (
          <p className="text-muted-foreground text-sm">
            At least two players are needed to start.
          </p>
        ) : null}
      </div>
    );
  }

  // --- Finished ------------------------------------------------------------

  if (lobby.status === "finished") {
    const ranked = [...lobby.players].sort((a, b) => b.score - a.score);
    const winners = lobby.players.filter((player) =>
      lobby.winner_ids.includes(player.id),
    );

    return (
      <div className="mx-auto max-w-2xl space-y-6">
        {header}

        <Card>
          <CardHeader>
            <CardDescription>Final result</CardDescription>
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Crown className="size-6 text-amber-500" aria-hidden />
              {winners.length === 1
                ? `${winners[0].nickname} wins`
                : `Draw: ${winners.map((w) => w.nickname).join(", ")}`}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {ranked.map((player, index) => (
              <div
                key={player.id}
                className="flex items-center gap-3 border-b pb-2 text-sm last:border-0"
              >
                <span className="text-muted-foreground w-6 font-mono">
                  {index + 1}.
                </span>
                <span className="font-medium">{player.nickname}</span>
                <span className="ml-auto font-mono">{player.score}</span>
              </div>
            ))}
          </CardContent>
          <CardFooter className="gap-2">
            {me?.is_host ? (
              <Button
                onClick={() => playerId && act(() => restartLobby(code, playerId))}
                disabled={busy}
              >
                Back to lobby
              </Button>
            ) : null}
            <Button variant="ghost" asChild>
              <Link href="/play">New game</Link>
            </Button>
          </CardFooter>
        </Card>

        {/*
          Every question has now been answered, so the material each was written
          from can be published for players to check against.
        */}
        {lobby.finished_rounds.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Questions and sources</CardTitle>
              <CardDescription>
                Check the answers against where each question came from.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {lobby.finished_rounds.map((finished, index) => (
                <div
                  key={finished.quiz_id}
                  className="space-y-2 border-b pb-3 text-sm last:border-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-muted-foreground w-6 font-mono">
                      {index + 1}.
                    </span>
                    <span className="font-medium">{finished.title}</span>
                    <DifficultyBadge difficulty={finished.difficulty} />
                    <SourceLink source={finished.source} className="ml-auto" />
                  </div>
                  {/*
                    The last round never gets a between-rounds review -- there is
                    no next round to pause before -- so this is the only place
                    its answers can be read.
                  */}
                  <dl className="space-y-1 pl-9">
                    {finished.solution.map((pair) => (
                      <div key={pair.category_label}>
                        <dt className="flex flex-wrap items-baseline gap-2">
                          <span className="text-muted-foreground">
                            {pair.category_label}
                          </span>
                          <span className="font-medium">{pair.item_label}</span>
                        </dt>
                        {pair.explanation ? (
                          <dd className="text-muted-foreground text-xs">
                            {pair.explanation}
                          </dd>
                        ) : null}
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>
    );
  }

  // --- Playing -------------------------------------------------------------

  const round = lobby.round_view;
  if (!round) return null;

  const currentPlayer = lobby.players.find(
    (player) => player.id === lobby.current_player_id,
  );
  const reviewing = lobby.status === "reviewing";
  // The round that just ended is the last one appended.
  const justFinished = reviewing
    ? (lobby.finished_rounds[lobby.finished_rounds.length - 1] ?? null)
    : null;
  const total = round.remaining_items.length + round.solved_items.length;
  const solvedIn = (categoryId: string) =>
    round.solved_items.filter((item) => item.category_id === categoryId);

  // Answers already tried here and rejected. A wrong placement leaves the
  // category open -- the right answer is still out there -- so without showing
  // this the next player has no way of knowing the guess has been used, and the
  // table works through the same wrong idea one at a time.
  //
  // Read off the round's move history rather than stored per category: the
  // server already sends every placement with the category it went into.
  const wrongIn = (categoryId: string) =>
    Array.from(
      new Set(
        lobby.history
          .filter((move) => !move.was_correct && move.category_id === categoryId)
          .map((move) => move.item_label),
      ),
    );

  return (
    <div className="space-y-4">
      {header}

      {/*
        Two columns: the question has the room to itself, and everything that is
        *about* the players sits beside it rather than above it. Stacks on a
        phone, where the question still comes first.
      */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-start">
        <div className="min-w-0 space-y-4">
          {/* The question, centred and large -- it is what everyone is
              actually looking at, and it used to compete with the scoreboard
              and the turn banner for the top of the page. */}
          <div className="animate-quiz-rise relative isolate space-y-2 text-center">
            {/* Lights the question from behind. Purely decorative, so it is
                hidden from assistive tech and cannot be clicked. */}
            <div className="quiz-ambient" aria-hidden />
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Round {lobby.round_index + 1} of {lobby.round_count}
            </p>
            {/* Outfit carries weight well, and a heading at 800 with the
                tracking pulled in is a good part of what separates a game from
                a form. */}
            <h1 className="text-3xl font-extrabold tracking-tight text-balance sm:text-4xl">
              {round.title}
            </h1>
            {round.description ? (
              <p className="text-muted-foreground text-base text-balance">
                {round.description}
              </p>
            ) : null}
            <div className="flex justify-center pt-1">
              <DifficultyBadge difficulty={round.difficulty} />
            </div>
            <Progress
              value={(round.solved_items.length / Math.max(total, 1)) * 100}
              className="mt-2"
            />
          </div>

      {/*
        Between rounds. The board stays on screen with every answer revealed and
        its reason underneath, which is the point of the pause -- so this is a
        banner over the board rather than a screen that replaces it.
      */}
      {reviewing ? (
        <Card className="border-primary/40">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              <BookOpen className="size-4 shrink-0" aria-hidden />
              Round over — here is why
            </CardTitle>
            <CardDescription>
              {secondsLeft !== null && secondsLeft > 0
                ? `Next round in ${secondsLeft}s.`
                : "Starting the next round…"}
            </CardDescription>
            <SourceLink source={justFinished?.source ?? null} className="pt-1" />
          </CardHeader>
          {me?.is_host ? (
            <CardFooter>
              <Button
                size="sm"
                disabled={busy}
                onClick={() => playerId && act(() => skipReview(code, playerId))}
              >
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Next round
              </Button>
            </CardFooter>
          ) : null}
        </Card>
      ) : (
      <Card
        className={cn(
          // Breathing while it is your go, so a player who looked away knows
          // the table is waiting on them without reading anything.
          isMyTurn && "border-primary/60 animate-quiz-glow",
        )}
      >
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
            <span>
              {isMyTurn
                ? selectedItemId
                  ? "Now pick a category"
                  : "Your turn — pick an answer"
                : `Waiting for ${currentPlayer?.nickname ?? "the next player"}…`}
            </span>
            {/*
              Ticked in the browser from a deadline the server set, so it moves
              every second rather than only when a request happens. The server
              still owns the rule -- this is the display, not the referee.
            */}
            {turnSecondsLeft !== null ? (
              <span
                className={cn(
                  "flex items-center gap-1.5 font-mono text-sm tabular-nums",
                  turnSecondsLeft <= 5
                    ? "text-destructive font-semibold"
                    : "text-muted-foreground",
                )}
                // Read out only as it gets urgent, rather than every second.
                aria-live={turnSecondsLeft <= 5 ? "assertive" : "off"}
              >
                <Timer className="size-4 shrink-0" aria-hidden />
                {turnSecondsLeft}s
              </span>
            ) : null}
          </CardTitle>
          {turnSecondsLeft !== null && lobby.turn_seconds ? (
            <Progress
              value={(turnSecondsLeft / lobby.turn_seconds) * 100}
              className={cn("h-1", turnSecondsLeft <= 5 && "[&>*]:bg-destructive")}
            />
          ) : null}
          <CardDescription>
            {me && !me.is_active
              ? "You are out for this round. You are back in at the next topic."
              : "One placement per turn. Get it wrong — or run out of time — and you sit out the rest of the round."}
          </CardDescription>
          {lobby.timed_out ? (
            <p className="text-muted-foreground flex items-center gap-2 pt-1 text-sm">
              <Timer className="size-4 shrink-0" aria-hidden />
              <strong>{lobby.timed_out}</strong> ran out of time.
            </p>
          ) : null}
          {/*
            Only the other players ever see this: if it were you, your own
            polling would be keeping you marked responsive.
          */}
          {lobby.current_player_quiet ? (
            <p className="text-muted-foreground flex items-center gap-2 pt-1 text-sm">
              <WifiOff className="size-4 shrink-0" aria-hidden />
              {currentPlayer?.nickname ?? "That player"} has stopped responding
              — their turn will be skipped shortly.
            </p>
          ) : null}
        </CardHeader>
        {/* The answers are the thing being read across a room, so they are
            sized to be legible at a glance rather than packed in. */}
        <CardContent className="flex flex-wrap justify-center gap-2">
          {round.remaining_items.map((item) => (
            <Button
              key={item.id}
              size="lg"
              className={cn(
                "quiz-shine h-auto min-h-12 px-5 py-2.5 text-base font-medium whitespace-normal",
                // Lifts and grows a little under the cursor, settles under the
                // press. The shared easing is what stops this reading as a
                // separate widget from everything else on the board.
                "ease-(--ease-soft) transition-all duration-200",
                "hover:-translate-y-0.5 hover:scale-[1.03] hover:shadow-lg",
                "active:translate-y-0 active:scale-[0.98] active:duration-75",
                selectedItemId === item.id &&
                  "ring-primary/50 scale-[1.03] shadow-lg ring-2",
              )}
              variant={selectedItemId === item.id ? "default" : "outline"}
              disabled={!isMyTurn || busy}
              aria-pressed={selectedItemId === item.id}
              onClick={() =>
                setSelectedItemId(selectedItemId === item.id ? null : item.id)
              }
            >
              {item.label}
            </Button>
          ))}
        </CardContent>
      </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {round.categories.map((category, index) => {
          const solved = solvedIn(category.id);
          // A category holds exactly one answer, so once it is filled there is
          // no legal move left into it. Arming it anyway would offer a
          // placement that is always wrong and costs the player the round.
          const full = solved.length > 0;
          // Matched by label because the solution is built from the round that
          // has just been dropped, so its category ids are no longer to hand.
          const reveal =
            justFinished?.solution.find(
              (pair) => pair.category_label === category.label,
            ) ?? null;
          return (
            <CategoryCard
              key={category.id}
              title={category.label}
              solved={solved}
              full={full}
              wrong={wrongIn(category.id)}
              reveal={reveal}
              armed={isMyTurn && selectedItemId !== null && !busy && !full}
              // Staggered so the board deals itself in rather than appearing at
              // once. Capped, or the last card of a ten-pair round would still
              // be arriving after the first is ready to click.
              enterDelayMs={Math.min(index, 8) * 45}
              onPlace={() => play(category.id)}
            />
          );
        })}
          </div>
        </div>

        {/*
          Everything about the players, out of the way of the question. Sticky
          so the turn and the clock stay visible while the board is scrolled.
        */}
        <aside className="space-y-4 lg:sticky lg:top-20">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-1.5">
                  <Users className="size-4" aria-hidden />
                  Players
                </span>
                {turnSecondsLeft !== null ? (
                  <span
                    className={cn(
                      "flex items-center gap-1 font-mono tabular-nums",
                      turnSecondsLeft <= 5
                        ? "text-destructive font-semibold"
                        : "text-muted-foreground",
                    )}
                    aria-live={turnSecondsLeft <= 5 ? "assertive" : "off"}
                  >
                    <Timer className="size-3.5 shrink-0" aria-hidden />
                    {turnSecondsLeft}s
                  </span>
                ) : null}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {[...lobby.players]
                .sort((a, b) => b.score - a.score)
                .map((player) => {
                  const theirTurn = player.id === lobby.current_player_id;
                  return (
                    <div
                      key={player.id}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                        // Whose turn it is has to be readable without hunting.
                        theirTurn && "bg-primary/10 ring-primary/30 ring-1",
                        (!player.is_active || !player.is_connected) &&
                          "opacity-50",
                      )}
                    >
                      {theirTurn ? (
                        <Timer
                          className="text-primary size-3.5 shrink-0"
                          aria-label="on the clock"
                        />
                      ) : (
                        <span className="size-3.5 shrink-0" />
                      )}
                      <span className="min-w-0 flex-1 truncate">
                        {player.nickname}
                        {player.id === playerId ? " (you)" : ""}
                      </span>
                      {player.is_host ? (
                        <Crown
                          className="size-3.5 shrink-0 text-amber-500"
                          aria-label="host"
                        />
                      ) : null}
                      {!player.is_connected ? (
                        <WifiOff className="size-3.5 shrink-0" aria-label="offline" />
                      ) : !player.is_active ? (
                        <X className="size-3.5 shrink-0" aria-label="out" />
                      ) : null}
                      <span className="font-mono tabular-nums">{player.score}</span>
                    </div>
                  );
                })}
            </CardContent>
          </Card>

          {/* What has been played this round, newest first. */}
          {lobby.history.length > 0 ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-1.5 text-sm">
                  <History className="size-4" aria-hidden />
                  This round
                </CardTitle>
              </CardHeader>
              <CardContent className="max-h-72 space-y-1 overflow-y-auto">
                {[...lobby.history].reverse().map((move, index) => (
                  <div
                    key={`${move.item_label}-${lobby.history.length - index}`}
                    className="flex items-start gap-2 text-sm"
                  >
                    {move.was_correct ? (
                      <Check
                        className="mt-0.5 size-3.5 shrink-0 text-success"
                        aria-label="correct"
                      />
                    ) : (
                      <X
                        className="text-destructive mt-0.5 size-3.5 shrink-0"
                        aria-label="wrong"
                      />
                    )}
                    <span className="min-w-0">
                      <span className="text-muted-foreground">
                        {move.nickname}
                      </span>{" "}
                      <span className="font-medium">{move.item_label}</span>
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function CategoryCard({
  title,
  solved,
  full,
  wrong,
  reveal,
  armed,
  enterDelayMs,
  onPlace,
}: {
  title: string;
  solved: { item_id: string; label: string }[];
  /** Already holds its one answer, so it is done for this round. */
  full: boolean;
  /**
   * Answers tried here and rejected. The category stays open and clickable —
   * unlike `full`, a wrong guess costs the guesser their round but leaves the
   * pairing unsolved for everyone else.
   */
  wrong: string[];
  /** Set only between rounds: the answer and why, whether or not it was found. */
  reveal: ResolvedPair | null;
  armed: boolean;
  /** Stagger, so the board deals itself in rather than appearing all at once. */
  enterDelayMs: number;
  onPlace: () => void;
}) {
  const missed = reveal !== null && reveal.solved_by === null;

  return (
    <Card
      className={cn(
        "animate-quiz-rise",
        // Rises to meet the cursor only when it can actually take the answer,
        // so the movement means something rather than decorating everything.
        armed &&
          "ring-primary/60 hover:ring-primary cursor-pointer hover:-translate-y-1 hover:scale-[1.02] hover:shadow-xl",
        // Greyed out rather than hidden: the pairing so far is what players
        // reason from when placing what is left.
        full && !reveal && "bg-muted/50 opacity-60",
        // Nobody got this one, so it is the one worth looking at.
        missed && "border-amber-500/50",
      )}
      style={{ animationDelay: `${enterDelayMs}ms` }}
      onClick={armed ? onPlace : undefined}
      aria-disabled={full || undefined}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {full ? (
            <Check
              className="size-4 shrink-0 text-success"
              aria-hidden
            />
          ) : null}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-14 space-y-2">
        <div className="flex flex-wrap gap-2">
          {reveal ? (
            <Badge variant={missed ? "outline" : "secondary"}>
              {reveal.item_label}
            </Badge>
          ) : solved.length === 0 ? (
            // Only "Empty" when nothing has been tried either -- a category
            // with rejected guesses under it is not empty, it is unsolved.
            wrong.length === 0 ? (
              <p className="text-muted-foreground text-sm">Empty</p>
            ) : null
          ) : (
            solved.map((item) => (
              // Pops as it mounts, which is exactly when the answer lands.
              <Badge
                key={item.item_id}
                variant="secondary"
                className="animate-quiz-pop"
              >
                {item.label}
              </Badge>
            ))
          )}
          {missed ? (
            <span className="text-muted-foreground text-xs">nobody got this</span>
          ) : null}
        </div>

        {/*
          Guesses that were tried here and rejected. Shown because a wrong
          placement leaves the category open -- the right answer is still to
          come -- so without this the next player cannot tell the idea has
          already been spent, and the table burns a turn each on the same one.
        */}
        {wrong.length > 0 ? (
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {wrong.map((label) => (
              <span
                key={label}
                className="text-muted-foreground flex items-center gap-1 text-xs"
              >
                <X className="text-destructive size-3 shrink-0" aria-hidden />
                <span className="line-through">{label}</span>
              </span>
            ))}
          </div>
        ) : null}
        {/*
          The reason, underneath its answer. Absent on questions seeded before
          the explain step existed, and then simply nothing is shown.
        */}
        {reveal?.explanation ? (
          <p className="text-muted-foreground text-sm">{reveal.explanation}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
