"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Check,
  Copy,
  Crown,
  History,
  Loader2,
  LogOut,
  RotateCcw,
  Timer,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { CategoryPicture, ImageCredit } from "@/components/category-image";
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
import { copyText } from "@/lib/clipboard";
import { forgetPlayer, recallPlayer } from "@/lib/identity";
import { forgetPlayed, NO_PLAYED, playedSlugs, rememberPlayed } from "@/lib/played";
import { subscribeToLobby } from "@/lib/realtime";
import { shuffleBySeed } from "@/lib/shuffle";
// Aliased: this file already has a `play(categoryId)` that places an answer.
// Both take a string, so an unaliased import shadows silently and every cue
// becomes an attempt to place the selected item into a category called
// "yourTurn".
import {
  HURRY_FROM,
  play as playCue,
  playCountdown,
  unlock,
} from "@/lib/sound";
import { deadlineFrom, reconcileDeadline, useCountdown } from "@/lib/use-countdown";
import type {
  CategoryImage,
  Difficulty,
  LastMove,
  LobbyView,
  ResolvedPair,
  SolvedItem,
  Subject,
} from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { cn } from "@/lib/utils";

import { RejoinForm } from "./rejoin-form";

// Not how changes are learned -- they arrive over the socket with the state in
// them. This is the heartbeat, and the backstop for anything push misses.
//
// It is sized by the heartbeat rather than by freshness. PRESENCE_TIMEOUT on
// the server is 15s and QUIET_AFTER is 6s, so a beat slower than that would
// have the table told a player had gone quiet in the gap between their own
// beats.
const POLL_MS = 4_000;

// How long the copied state sticks on the lobby code. Longer than the wobble
// (600ms) on purpose: the movement catches the eye, the tick that stays behind
// is what answers "did that work?" for someone who looked a moment later.
const COPIED_MS = 2_000;

const ROUND_CHOICES = [3, 5, 7, 10];

// Bounded to match `LobbyStart.turn_seconds` on the server (10–120). Below ten
// nobody can read a board of eight pairs; above two minutes it stops being a
// timer.
const TURN_CHOICES = [15, 30, 45, 60];

// Ordered easiest first, which is the order people reason about them in --
// `Object.keys` on the counts would follow whatever the API happened to send.
const DIFFICULTY_CHOICES: { level: Difficulty; label: string }[] = [
  { level: "easy", label: "Easy" },
  { level: "medium", label: "Medium" },
  { level: "hard", label: "Hard" },
];

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
  // All three to begin with, so the default game is the whole pool. Unticking
  // the last one is refused below -- a game with no questions in it is not a
  // choice anyone means to make, and the API rejects it anyway.
  const [difficulties, setDifficulties] = useState<Difficulty[]>([
    "easy",
    "medium",
    "hard",
  ]);

  // Polling and turn submission race: a poll started before a turn can land
  // after it and show pre-turn state. Applying only newer versions fixes it.
  const versionRef = useRef(-1);

  // The turn clock is held as a wall-clock deadline and ticked in the browser.
  // The server sends how many seconds are left as of the moment it answered;
  // rendering that directly means the number only moves when a request happens,
  // which is what made the clock appear frozen. See useCountdown.
  //
  // The between-rounds review has no clock of its own -- it ends when the host
  // presses the button and at no other time.
  const [turnDeadline, setTurnDeadline] = useState<number | null>(null);

  // When the invite link was last copied: drives the tick on the lobby code and
  // outlives the wobble so the confirmation is still readable after it settles.
  const [copiedAt, setCopiedAt] = useState<number | null>(null);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  const apply = useCallback((view: LobbyView) => {
    if (view.version < versionRef.current) return;
    versionRef.current = view.version;
    setLobby(view);
    // Turned into a wall-clock deadline so the countdown can tick without
    // asking again -- but only adopted when the server is saying something new.
    // Re-pinning it on every poll makes the displayed number stall, because
    // each answer is rounded up and arrives slightly stale. See
    // `reconcileDeadline`.
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

    // The socket carries the state, so a change renders as it arrives rather
    // than triggering a fetch that then renders. `view` is null only when the
    // API judged the state too large to put in a frame, and then this falls
    // back to asking.
    const unsubscribe = subscribeToLobby(code, (view) => {
      if (view) apply(view);
      else void refresh();
    });

    // Still polling, for two reasons that both survive a working socket: it is
    // the heartbeat that keeps this player marked present, and it is the
    // backstop if a message is missed or realtime is not configured at all.
    const timer = setInterval(() => void refresh(), POLL_MS);

    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, [code, refresh, apply]);

  // Reaching zero has to *do* something. The server acts on the turn deadline
  // only when a request arrives and finds it passed -- nothing runs on a timer
  // there, and on serverless nothing can. Without this poke a stalled player
  // would keep the turn until the next poll.
  //
  // Every client pokes at once and the store's lock sorts it out: one request
  // moves the game on and the rest read the result.
  const poke = useCallback(() => void refresh(), [refresh]);

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

  // Actually on the clock, as opposed to merely being next.
  //
  // The server advances the cursor and *then* ends the round, so through the
  // whole review `current_player_id` already names whoever opens the next one.
  // Reading that as "my turn" costs the cue twice over: it fires in the middle
  // of the answers being read, and then the flag is already up when play
  // resumes, so the moment it exists for passes in silence.
  const onTheClock = isMyTurn && lobby?.status === "playing";

  // --- Sound cues ----------------------------------------------------------
  //
  // Fired from transitions rather than from state, so a poll that re-delivers
  // the same lobby is silent. Everything is compared in refs: a cue is a side
  // effect on the world, not a piece of React state, and storing it as state
  // would re-render the room to play a note.
  const primed = useRef(false);
  const lastMove = useRef<string | null>(null);
  const wasOnTheClock = useRef(false);
  const lastStatus = useRef<string | null>(null);

  // A browser holds an AudioContext suspended until the page has been
  // interacted with, so every cue before the first click in this tab is
  // silently dropped. `act()` unlocks on each game action, which covers a host
  // -- they press Start -- and nobody else: a player who joined from a link and
  // sat waiting has clicked nothing here, and the first thing that happens to
  // them is their turn coming round. That is precisely the cue worth hearing,
  // so it cannot be the one paying for the unlock.
  //
  // Capture phase, so a handler that stops propagation cannot swallow it, and
  // `once` because there is nothing to do after the context exists.
  useEffect(() => {
    const open = () => unlock();
    const options = { capture: true, once: true, passive: true } as const;
    window.addEventListener("pointerdown", open, options);
    window.addEventListener("keydown", open, options);
    return () => {
      window.removeEventListener("pointerdown", open, { capture: true });
      window.removeEventListener("keydown", open, { capture: true });
    };
  }, []);

  useEffect(() => {
    if (!lobby) return;

    // Keyed on the move, not on the lobby version. Version was wrong and
    // audibly so: it moves for anything at all -- a player joining, someone
    // reconnecting, a presence flip -- and each of those replayed the last
    // placement's chime at the whole table. What identifies a move is where it
    // sits in the round, so that is what this counts.
    const moveKey = lobby.last_move
      ? `${lobby.round_index}:${lobby.history.length}:${lobby.last_move.item_label}`
      : null;

    // The first view is the state of the world on arrival, not a series of
    // things that just happened -- joining a game in progress should not
    // replay its history at you.
    if (!primed.current) {
      primed.current = true;
      lastMove.current = moveKey;
      wasOnTheClock.current = onTheClock;
      lastStatus.current = lobby.status;
      return;
    }

    if (moveKey && moveKey !== lastMove.current) {
      playCue(lobby.last_move!.was_correct ? "correct" : "wrong");
    }
    lastMove.current = moveKey;

    // The board lights up at the same moment -- see `lit` below. One of the two
    // reaches a player who is looking somewhere else, and which one it is
    // depends on whether they are wearing headphones or watching the table.
    if (onTheClock && !wasOnTheClock.current) playCue("yourTurn");
    wasOnTheClock.current = onTheClock;

    if (lobby.status !== lastStatus.current) {
      if (lobby.status === "reviewing") playCue("roundEnd");
      if (lobby.status === "finished") playCue("gameEnd");
      lastStatus.current = lobby.status;
    }
  }, [lobby, onTheClock]);

  // Remember what this browser has now seen, so the next game prefers something
  // else. Recorded from `finished_rounds` rather than from `quiz_slugs` at the
  // start, because a game that is abandoned in round one has not "played" the
  // four rounds it drew -- and burning them would retire the pool for nothing.
  //
  // Runs on every device in the lobby, not only the host's. Only the host's
  // list is sent when starting, but any of them may host the next game.
  useEffect(() => {
    if (!lobby) return;
    rememberPlayed(lobby.finished_rounds.map((round) => round.slug));
  }, [lobby]);

  // The closing seconds, and only for the player they belong to -- everyone
  // else is watching, and a clock counting down somebody else's turn is noise.
  //
  // The cue escalates with the number rather than repeating, so the last five
  // seconds are heard as running out rather than as passing. See `HURRY` in
  // lib/sound.
  useEffect(() => {
    if (!isMyTurn) return;
    if (turnSecondsLeft === null || turnSecondsLeft <= 0) return;
    if (turnSecondsLeft > HURRY_FROM) return;
    playCountdown(turnSecondsLeft);
  }, [turnSecondsLeft, isMyTurn]);

  // What this browser has already seen. `useStored` takes a separate server
  // snapshot, so SSR and hydration agree instead of flashing.
  //
  // It deliberately does not subscribe to localStorage, so nothing re-reads on
  // its own. The reset button is the only thing that changes the value while
  // the page is up, and the state bump below is what makes React look again.
  const [, forgetTick] = useState(0);
  const played = useStored(playedSlugs, NO_PLAYED);

  // How many questions the chosen subjects hold at one rating. Shown beside each
  // box so an empty tick is visibly empty rather than quietly shortening the
  // game.
  const countAt = (level: Difficulty) =>
    subjects
      .filter((subject) => chosenSubjects.includes(subject.slug))
      .reduce((total, subject) => total + (subject.difficulty_counts[level] ?? 0), 0);

  // Lets the host see when they have asked for more rounds than the chosen
  // subjects can supply, rather than silently getting a shorter game.
  //
  // Counted per difficulty rather than from `quiz_count`, or ticking one box off
  // would leave this claiming a pool the draw no longer has -- and this number
  // is exactly what the round count is chosen against.
  const availableQuestions = subjects
    .filter((subject) => chosenSubjects.includes(subject.slug))
    .reduce(
      (total, subject) =>
        total +
        difficulties.reduce(
          (sum, level) => sum + (subject.difficulty_counts[level] ?? 0),
          0,
        ),
      0,
    );

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

  async function copyInvite() {
    // The room's own URL is the invite: someone opening it without an identity
    // in this browser gets the join form. No separate landing page to point at.
    const link = `${window.location.origin}/lobby/${code}`;
    if (!(await copyText(link))) {
      toast.error("Could not copy -- the code is right there to type in.");
      return;
    }

    toast.success("Invite link copied.");
    // Timestamped rather than a boolean because it doubles as the key on the
    // code below. Clicking again while the wobble is still running has to
    // restart it, and re-applying a class that is already there does not
    // re-trigger the animation -- a new key remounts the element, which does.
    setCopiedAt(Date.now());
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopiedAt(null), COPIED_MS);
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
        <button
          type="button"
          onClick={copyInvite}
          title="Copy the invite link"
          aria-label={`Lobby code ${lobby.code}. Copy the invite link.`}
          className="group focus-visible:ring-ring flex cursor-pointer items-center gap-2 rounded-md focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <span
            key={copiedAt ?? "idle"}
            className={cn(
              "font-mono text-3xl font-bold tracking-widest",
              copiedAt !== null && "animate-quiz-wobble",
            )}
          >
            {lobby.code}
          </span>
          {copiedAt !== null ? (
            <Check className="text-success size-4" aria-hidden />
          ) : (
            // Dimmed until hover, because the code is what people are reading
            // here -- the icon only has to say that the thing is clickable.
            <Copy
              className="text-muted-foreground/60 size-4 transition-colors group-hover:text-foreground"
              aria-hidden
            />
          )}
        </button>
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
              Tap the code above to copy an invite link. The game starts when
              the host is ready.
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

              {/*
                Which ratings may be drawn. Ticked rather than a single choice
                because "easy and medium" is the common want and a three-way
                radio cannot say it.
              */}
              <div className="space-y-2">
                <Label>Difficulty</Label>
                <div className="flex flex-wrap gap-x-6 gap-y-3">
                  {DIFFICULTY_CHOICES.map(({ level, label }) => {
                    const onlyOneLeft =
                      difficulties.length === 1 && difficulties.includes(level);
                    return (
                      <div key={level} className="flex items-start gap-3">
                        <Checkbox
                          id={`difficulty-${level}`}
                          checked={difficulties.includes(level)}
                          // Refused rather than hidden: the box stays where it
                          // is and simply will not turn off, which reads as a
                          // rule instead of as a bug. A game with no questions
                          // in it is not a choice worth offering.
                          disabled={onlyOneLeft}
                          onCheckedChange={(checked) =>
                            setDifficulties((current) =>
                              checked
                                ? [...current, level]
                                : current.filter((each) => each !== level),
                            )
                          }
                        />
                        <Label
                          htmlFor={`difficulty-${level}`}
                          className="font-normal"
                        >
                          {label}
                          <span className="text-muted-foreground">
                            {" "}
                            · {countAt(level)}
                          </span>
                        </Label>
                      </div>
                    );
                  })}
                </div>
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
                  wrong answer. Whoever opens a round gets a little longer —
                  they are the one reading the board cold.
                </p>
              </div>

              {/*
                Only worth showing once there is a history. A preference rather
                than a promise, which the wording has to carry: the server falls
                back to played questions when nothing new is left, and a big
                question is never counted as used up because it deals a
                different board each time.
              */}
              {played.length > 0 ? (
                <div className="space-y-2">
                  <Label>Already played</Label>
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="text-muted-foreground text-sm">
                      {played.length} question{played.length === 1 ? "" : "s"}{" "}
                      will be kept back where possible.
                    </p>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        forgetPlayed();
                        forgetTick((n) => n + 1);
                      }}
                    >
                      <RotateCcw className="size-4" aria-hidden />
                      Reset
                    </Button>
                  </div>
                  <p className="text-muted-foreground text-sm">
                    Remembered on this device only, and used up once nothing new
                    is left.
                  </p>
                </div>
              ) : null}
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
                      played,
                      difficulties,
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
                        <dt className="flex flex-wrap items-center gap-2">
                          {pair.image ? (
                            <span className="size-10 shrink-0 overflow-hidden rounded-(--radius-sm)">
                              <CategoryPicture
                                image={pair.image}
                                label={pair.category_label}
                              />
                            </span>
                          ) : null}
                          <span className="text-muted-foreground">
                            {pair.category_label}
                          </span>
                          <span className="font-medium">{pair.item_label}</span>
                        </dt>
                        {pair.image ? (
                          <dd className="pl-12">
                            <ImageCredit image={pair.image} />
                          </dd>
                        ) : null}
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
  const nextPlayer = lobby.players.find(
    (player) => player.id === lobby.next_player_id,
  );
  // Named on every other screen so a review reads as waiting for a person
  // rather than as the game having hung.
  const hostName = lobby.players.find((player) => player.is_host)?.nickname ?? null;
  const reviewing = lobby.status === "reviewing";
  // The room, the board and the question's own greys all key off the same flag
  // as the cue above, so they can only ever light up together.
  const lit = onTheClock;
  // The question's supporting text sits directly over the glow, and amber is
  // light: at the strength the glow reaches on your turn, `muted-foreground`
  // falls to about 2.2:1 against it. Brightened rather than the glow being held
  // back -- see `.quiz-ambient--yours` in globals.css, which has the numbers.
  const overGlow = lit ? "text-foreground" : "text-muted-foreground";
  // The round that just ended is the last one appended.
  const justFinished = reviewing
    ? (lobby.finished_rounds[lobby.finished_rounds.length - 1] ?? null)
    : null;
  const total = round.remaining_items.length + round.solved_items.length;
  const solvedIn = (categoryId: string) =>
    round.solved_items.filter((item) => item.category_id === categoryId);

  // The API hands both lists over in the order the question was written, which
  // pairs them off by position: first answer, first category, and so on down
  // the board. Read once, that is the whole round.
  //
  // Seeded on the round rather than drawn fresh, so the board holds still
  // between polls and reads the same way for everyone at the table -- see
  // `shuffleBySeed`. The round index is in the seed because a question can come
  // round again in a later game, and a board that always deals itself the same
  // way is the leak back in a slower form.
  const boardSeed = `${round.quiz_id}:${lobby.round_index}`;
  const categories = shuffleBySeed(round.categories, boardSeed, (c) => c.id);
  const remainingItems = shuffleBySeed(
    round.remaining_items,
    boardSeed,
    (item) => item.id,
  );

  // Answers already tried here and rejected. A wrong placement leaves the
  // category open -- the right answer is still out there -- so without showing
  // this the next player has no way of knowing the guess has been used, and the
  // table works through the same wrong idea one at a time.
  //
  // Read off the round's move history rather than stored per category: the
  // server already sends every placement with the category it went into.
  // Kept as whole moves rather than labels so the caller keeps the context of
  // who guessed. De-duplicated by label: the same wrong answer tried twice on
  // one category is one thing to show, not two.
  const wrongIn = (categoryId: string) => {
    const seen = new Set<string>();
    return lobby.history.filter((move) => {
      if (move.was_correct || move.category_id !== categoryId) return false;
      if (seen.has(move.item_label)) return false;
      seen.add(move.item_label);
      return true;
    });
  };

  return (
    <>
      {/*
        The room lights up when the turn comes to you -- the one cue that works
        on someone who is looking at the table rather than at their screen.
        Outside the column below because it is fixed to the viewport: as a child
        of a `space-y` stack it would collect a margin and hang a gap along the
        top of the wash.
      */}
      <div
        className={cn(
          "quiz-room-glow",
          lit && "quiz-room-glow--on",
        )}
        aria-hidden
      />
      <div className="space-y-4">
        {header}

        {/*
          Two columns: the question has the room to itself, and everything that
          is *about* the players sits beside it rather than above it. Stacks on
          a phone, where the question still comes first.
        */}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
          <div className="min-w-0 space-y-4">
            {/*
              Whose turn it is, at the top of the column and stuck there. It used
              to be a line of body text inside the question card's header, which
              is exactly where a player scanning the board does not look --
              "hard to tell when I am up" was the complaint, and it was fair.

              Sticky rather than merely first, because the board scrolls past it:
              the answer to "am I up?" has to be on screen at every scroll
              position, not only at the top of the page.
            */}
            {/* Pinned *below* the site header, which is itself sticky and paints
                on top. At a smaller offset this slid under it and only its lower
                half stayed readable -- worst on a phone, where the bar is the
                tallest thing on screen and the header eats most of it. */}
            <div className="sticky top-(--sticky-top) z-20">
              <TurnBar
                isMyTurn={isMyTurn}
                isOut={Boolean(me && !me.is_active)}
                isCatchUp={lobby.is_catch_up}
                reviewing={reviewing}
                hasSelection={selectedItemId !== null}
                currentName={currentPlayer?.nickname ?? null}
                nextName={nextPlayer?.nickname ?? null}
                quiet={lobby.current_player_quiet}
                hostName={hostName}
                isHost={Boolean(me?.is_host)}
                // Nothing is on the clock during a review, so the whole readout
                // goes away rather than showing a stopped one.
                secondsLeft={reviewing ? null : turnSecondsLeft}
                totalSeconds={reviewing ? null : lobby.turn_seconds}
                deadline={reviewing ? null : turnDeadline}
              />
            </div>

            {/*
              The question and the answers, in one card. They were two blocks
              with a gap between them, which read as a heading that happened to
              sit above an unrelated widget rather than as one thing being asked.
            */}
            <Card
              className={cn(
                "animate-quiz-rise relative isolate overflow-hidden",
                // The board itself picks up the accent while you are on the
                // clock, so the signal is not confined to one strip.
                lit && "border-primary/50 shadow-lg",
              )}
            >
              {/* Lights the question from behind. Purely decorative, so it is
                  hidden from assistive tech and cannot be clicked -- what it
                  signals is said in words by the bar above it. */}
              <div
                className={cn(
                  "quiz-ambient",
                  // Turned right up while the turn is yours. Same condition as the
                  // card's border above, so the whole board brightens as one
                  // thing rather than lighting up in pieces.
                  lit && "quiz-ambient--yours",
                )}
                aria-hidden
              />
              <CardHeader className="space-y-2 text-center">
                <p
                  className={cn(
                    "text-xs font-medium tracking-wide uppercase",
                    overGlow,
                  )}
                >
                  {lobby.is_catch_up
                    ? "Settling round"
                    : `Round ${lobby.round_index + 1} of ${lobby.round_count}`}
                </p>
                {/* Outfit carries weight well, and a heading at 900 with the
                    tracking pulled in is a good part of what separates a game
                    from a form. Sized up again here: at 4xl it competed with the
                    answers rather than leading them. */}
                <h1 className="text-4xl font-black tracking-tight text-balance sm:text-5xl">
                  {round.title}
                </h1>
                {round.description ? (
                  <p
                    className={cn(
                      "mx-auto max-w-prose text-base text-balance sm:text-lg",
                      overGlow,
                    )}
                  >
                    {round.description}
                  </p>
                ) : null}
                <div className="flex items-center justify-center gap-2 pt-1">
                  <DifficultyBadge difficulty={round.difficulty} />
                  <span className={cn("font-mono text-xs tabular-nums", overGlow)}>
                    {round.solved_items.length}/{total}
                  </span>
                </div>
                {/*
                  Said plainly, because a round where most of the table cannot
                  play and most of the board goes untouched looks broken
                  otherwise. It is short by design: only the turns the rotation
                  never handed out are played here.
                */}
                {lobby.is_catch_up ? (
                  <p
                    className={cn(
                      "mx-auto max-w-prose text-sm text-balance",
                      overGlow,
                    )}
                  >
                    Evening things up. Over the game the answers did not divide
                    evenly between you, so whoever was asked fewer questions gets
                    the difference back now — everyone else sits this one out.
                  </p>
                ) : null}
                <Progress
                  value={(round.solved_items.length / Math.max(total, 1)) * 100}
                  className="h-1.5"
                />
              </CardHeader>

              <CardContent>
                {reviewing ? (
                  /*
                    Between rounds. The board below stays on screen with every
                    answer revealed and its reason underneath, which is the point
                    of the pause -- so this replaces the answer pool, not the
                    page.
                  */
                  <div className="flex flex-col items-center gap-3 text-center">
                    <p className="flex items-center gap-2 text-base font-semibold">
                      <BookOpen className="size-4 shrink-0" aria-hidden />
                      Round over — the answers are below
                    </p>
                    <SourceLink source={justFinished?.source ?? null} />
                    {/*
                      The only way out of a review -- it has no clock behind it,
                      so the table reads for as long as it wants and the host
                      says when that is done. Everyone else is told whose button
                      it is, or the pause looks like the game has hung.
                    */}
                    {me?.is_host ? (
                      <Button
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          playerId && act(() => skipReview(code, playerId))
                        }
                      >
                        {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                        Next round
                      </Button>
                    ) : (
                      <p className="text-muted-foreground text-sm">
                        Read them through — the next round starts when{" "}
                        {hostName ?? "the host"} is ready.
                      </p>
                    )}
                  </div>
                ) : (
                  <>
                    {/* The answers are read across a room, so they are sized to
                        be legible at a glance rather than packed in. Always words
                        now: the photographs are the categories. */}
                    <div className="flex flex-wrap justify-center gap-2.5">
                      {remainingItems.map((item) => (
                        <Button
                          key={item.id}
                          size="lg"
                          className={cn(
                            "quiz-shine h-auto min-h-14 px-6 py-3 text-lg font-semibold whitespace-normal",
                            // Lifts and grows a little under the cursor, settles
                            // under the press. The shared easing is what stops
                            // this reading as a separate widget from everything
                            // else on the board.
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
                            setSelectedItemId(
                              selectedItemId === item.id ? null : item.id,
                            )
                          }
                        >
                          {item.label}
                        </Button>
                      ))}
                    </div>
                    {lobby.timed_out ? (
                      <p className="text-muted-foreground flex items-center justify-center gap-2 pt-4 text-sm">
                        <Timer className="size-4 shrink-0" aria-hidden />
                        <strong>{lobby.timed_out}</strong> ran out of time.
                      </p>
                    ) : null}
                  </>
                )}
              </CardContent>
            </Card>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {categories.map((category, index) => {
                const solved = solvedIn(category.id);
                // A category holds exactly one answer, so once it is filled there
                // is no legal move left into it. Arming it anyway would offer a
                // placement that is always wrong and costs the player the round.
                const full = solved.length > 0;
                // Matched by label because the solution is built from the round
                // that has just been dropped, so its category ids are no longer
                // to hand.
                // Matched by label because the solution is built from the round
                // that has just been dropped, so its category ids are no longer
                // to hand. Guarded on a name existing: a picture round withholds
                // them while it is being played, and `null === null` would match
                // every card to the first pair.
                const reveal =
                  (category.label
                    ? justFinished?.solution.find(
                        (pair) => pair.category_label === category.label,
                      )
                    : null) ?? null;
                return (
                  <CategoryCard
                    key={category.id}
                    title={category.label}
                    image={category.image}
                    solved={solved}
                    full={full}
                    wrong={wrongIn(category.id)}
                    reveal={reveal}
                    armed={isMyTurn && selectedItemId !== null && !busy && !full}
                    // Staggered so the board deals itself in rather than
                    // appearing at once. Capped, or the last card of a
                    // thirteen-pair round would still be arriving after the first
                    // is ready to click.
                    enterDelayMs={Math.min(index, 8) * 45}
                    onPlace={() => play(category.id)}
                  />
                );
              })}
            </div>
          </div>

          {/*
            Everything about the players, out of the way of the question. Sticky
            so the order stays visible while the board is scrolled.
          */}
          <aside className="space-y-4 lg:sticky lg:top-(--sticky-top)">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-1.5 text-sm">
                  <Users className="size-4" aria-hidden />
                  Turn order
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {/*
                  Seating order, never re-sorted. This used to rank by score,
                  which meant the list rearranged itself under the players every
                  time anyone scored -- and it is the one panel whose job is to
                  say who comes after whom. The scores are still here; the running
                  standings are on the final scoreboard, which is where a ranking
                  belongs.
                */}
                {lobby.players.map((player, index) => {
                  const theirTurn = player.id === lobby.current_player_id;
                  const upNext = player.id === lobby.next_player_id;
                  // Only during a settling round, where "how many turns do I
                  // still have" is the thing a player wants and the seat number
                  // tells them nothing.
                  const owed = lobby.is_catch_up
                    ? (lobby.catch_up_left[player.id] ?? 0)
                    : 0;
                  return (
                    <div
                      key={player.id}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                        theirTurn && "bg-primary/15 ring-primary/40 font-medium ring-1",
                        upNext && "bg-surface",
                        (!player.is_active || !player.is_connected) && "opacity-50",
                      )}
                    >
                      <span className="text-muted-foreground w-4 shrink-0 text-center font-mono text-xs">
                        {index + 1}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {player.nickname}
                        {player.id === playerId ? " (you)" : ""}
                      </span>
                      {owed > 0 ? (
                        <Badge
                          variant="secondary"
                          className="h-5 px-1.5 text-[10px] tabular-nums"
                          title="turns still owed"
                        >
                          +{owed}
                        </Badge>
                      ) : null}
                      {theirTurn ? (
                        <Badge className="h-5 px-1.5 text-[10px] tracking-wide uppercase">
                          Now
                        </Badge>
                      ) : upNext ? (
                        <Badge
                          variant="outline"
                          className="h-5 px-1.5 text-[10px] tracking-wide uppercase"
                        >
                          Next
                        </Badge>
                      ) : null}
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
                          className="text-success mt-0.5 size-3.5 shrink-0"
                          aria-label="correct"
                        />
                      ) : (
                        <X
                          className="text-destructive mt-0.5 size-3.5 shrink-0"
                          aria-label="wrong"
                        />
                      )}
                      <span className="flex min-w-0 items-center gap-1.5">
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
    </>
  );
}

/**
 * Whose turn it is, and how long they have.
 *
 * Its whole job is to be answerable at a glance from across a room, so it is
 * sized and coloured well past what the information alone would justify: on
 * your turn the bar fills with the primary colour, states it in a heading
 * rather than a sentence, and breathes. That asymmetry is the point — every
 * other state is deliberately quiet, so the loud one cannot be missed.
 *
 * The clock is ticked in the browser from a deadline the server set, so it
 * moves every second rather than only when a request happens. The server still
 * owns the rule; this is the display, not the referee.
 */
/**
 * The turn clock as a bar that drains continuously.
 *
 * **Why it is not driven by `secondsLeft`.** That number is a whole second, so
 * a width computed from it can only ever move in steps — which is what made
 * this tick rather than run. Rounding it less would not help either: the
 * component re-renders about twice a second, and anything smoother than that
 * would mean re-rendering the whole bar on every frame to animate one number.
 *
 * So the browser is given the whole job instead. On a new deadline the fill is
 * snapped to where the clock actually is, then transitioned to zero over
 * exactly the remaining milliseconds, linearly. The compositor interpolates it
 * at the display's refresh rate and React does not render again until the
 * deadline changes. A backgrounded tab is handled for free: transitions run on
 * wall-clock time, so the bar is where it should be on return rather than
 * where it was when the timers stopped firing.
 */
function TimeBar({
  deadline,
  totalSeconds,
  trackClass,
  fillClass,
}: {
  deadline: number | null;
  totalSeconds: number;
  trackClass: string;
  fillClass: string;
}) {
  const fill = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = fill.current;
    if (!el) return;

    // Colour is carried in the same declaration because an inline `transition`
    // replaces the class-based one outright, and the fill has to keep fading to
    // red under five seconds.
    const colour = "background-color 300ms ease";

    if (deadline === null) {
      el.style.transition = colour;
      el.style.width = "100%";
      return;
    }

    const remaining = Math.max(0, deadline - Date.now());
    const start = Math.min(100, (remaining / (totalSeconds * 1000)) * 100);

    // Snap to the true position without animating the jump -- on a new turn
    // that jump is from empty back to full, and transitioning it would show the
    // bar refilling.
    el.style.transition = "none";
    el.style.width = `${start}%`;
    // Forces the style above to be committed as its own value. Without it the
    // browser coalesces both writes into one frame, sees only the final width,
    // and there is nothing left to transition from.
    void el.offsetWidth;

    el.style.transition = `width ${remaining}ms linear, ${colour}`;
    el.style.width = "0%";
  }, [deadline, totalSeconds]);

  return (
    <span className={cn("h-1 w-16 overflow-hidden rounded-full", trackClass)} aria-hidden>
      {/* No transition class: the effect owns the `transition` property, and an
          inline one would replace whatever Tailwind put here. Colour is folded
          into it there instead. */}
      <span ref={fill} className={cn("block h-full w-full", fillClass)} />
    </span>
  );
}

function TurnBar({
  isMyTurn,
  isOut,
  isCatchUp,
  reviewing,
  hasSelection,
  currentName,
  nextName,
  quiet,
  hostName,
  isHost,
  secondsLeft,
  totalSeconds,
  deadline,
}: {
  isMyTurn: boolean;
  /** Knocked out for the rest of this round — or, in a settling round, simply
   * not one of the players it is for. */
  isOut: boolean;
  isCatchUp: boolean;
  reviewing: boolean;
  /** An answer is picked and the board is waiting for a category. */
  hasSelection: boolean;
  currentName: string | null;
  nextName: string | null;
  /** The player on the clock has gone silent. Only ever seen by the others. */
  quiet: boolean;
  /** Who has the button that ends a review, so the wait can be attributed. */
  hostName: string | null;
  isHost: boolean;
  secondsLeft: number | null;
  /** What the clock started from, for the bar. Null while reviewing. */
  totalSeconds: number | null;
  /**
   * The wall-clock instant the turn ends. The bar needs this rather than
   * `secondsLeft` — a whole number can only ever move the bar in steps.
   */
  deadline: number | null;
}) {
  // Same threshold the countdown cue starts at, so what you see turning red
  // and what you hear speeding up are one event rather than two near misses.
  const urgent = !reviewing && secondsLeft !== null && secondsLeft <= HURRY_FROM;

  return (
    <div
      className={cn(
        "ease-(--ease-soft) flex items-center gap-3 rounded-(--radius) border px-4 py-3 shadow-sm backdrop-blur transition-colors duration-300",
        isMyTurn && !reviewing
          ? "bg-primary text-primary-foreground border-primary animate-quiz-glow"
          : "bg-surface border-hairline",
      )}
      // The one state worth interrupting a screen reader for is your own turn
      // arriving; the rest is commentary it can pick up when it gets there.
      aria-live={isMyTurn ? "assertive" : "polite"}
    >
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "truncate font-extrabold tracking-tight",
            isMyTurn && !reviewing ? "text-xl sm:text-2xl" : "text-base",
          )}
        >
          {reviewing
            ? "Round over"
            : isMyTurn
              ? hasSelection
                ? "Now pick a category"
                : "Your turn"
              : `${currentName ?? "Somebody"} is up`}
        </p>
        <p
          className={cn(
            "truncate text-xs",
            isMyTurn && !reviewing
              ? "text-primary-foreground/80"
              : "text-muted-foreground",
          )}
        >
          {reviewing
            ? isHost
              ? "You start the next round when everyone is ready"
              : `Waiting for ${hostName ?? "the host"} to start the next round`
            : isOut
              ? isCatchUp
                ? "You had your share of the questions — this one is for the others"
                : "You are out this round — back in at the next topic"
              : quiet && !isMyTurn
                ? `${currentName ?? "That player"} has stopped responding`
                : nextName
                  ? `Next: ${nextName}`
                  : "Place one answer, then it moves on"}
        </p>
      </div>

      {secondsLeft !== null ? (
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span
            className={cn(
              "font-mono text-3xl leading-none font-bold tabular-nums",
              urgent && !isMyTurn && "text-destructive",
            )}
          >
            {secondsLeft}
          </span>
          {totalSeconds ? (
            <TimeBar
              deadline={deadline}
              totalSeconds={totalSeconds}
              trackClass={isMyTurn ? "bg-primary-foreground/25" : "bg-hairline"}
              fillClass={
                isMyTurn
                  ? "bg-primary-foreground"
                  : urgent
                    ? "bg-destructive"
                    : "bg-primary"
              }
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function CategoryCard({
  title,
  image,
  solved,
  full,
  wrong,
  reveal,
  armed,
  enterDelayMs,
  onPlace,
}: {
  /** Null while a picture round runs -- naming it answers the question. */
  title: string | null;
  /** The photograph, for a picture question. Null for a worded category. */
  image: CategoryImage | null;
  solved: SolvedItem[];
  /** Already holds its one answer, so it is done for this round. */
  full: boolean;
  /**
   * Answers tried here and rejected, as the moves that placed them. The
   * category stays open and clickable — unlike `full`, a wrong guess costs the
   * guesser their round but leaves the pairing unsolved for everyone else.
   */
  wrong: LastMove[];
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
      {/*
        The photograph IS the question, so it comes before anything else and
        fills the card. `armed` is passed down because the whole card is a drop
        target when an answer is selected -- see the note in `category-image`.
      */}
      {image ? (
        <div className="px-6">
          <CategoryPicture
            image={image}
            label={title ?? "Bild"}
            armed={armed}
            className="aspect-[4/3] w-full rounded-(--radius-sm)"
          />
        </div>
      ) : null}
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {full ? (
            <Check
              className="size-4 shrink-0 text-success"
              aria-hidden
            />
          ) : null}
          {/*
            Null while a picture round runs: naming the bridge answers the
            question the photograph asks. The name arrives with the review.
          */}
          {title ?? (
            <span className="text-muted-foreground font-normal">
              Was ist das?
            </span>
          )}
        </CardTitle>
        {image ? <ImageCredit image={image} /> : null}
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
            // Pops as it mounts, which is exactly when the answer lands.
            solved.map((item) => (
              <Badge
                key={item.item_id}
                variant="secondary"
                className="animate-quiz-pop"
              >
                {item.label}
              </Badge>
            ))
          )}
          {/*
            "unsolved" rather than "nobody got this": with the round ending on
            a lap boundary, a pair here has usually not been attempted at all,
            and claiming the table failed at it would be wrong.
          */}
          {missed ? (
            <span className="text-muted-foreground text-xs">unsolved</span>
          ) : null}
        </div>

        {/*
          Guesses that were tried here and rejected. Shown because a wrong
          placement leaves the category open -- the right answer is still to
          come -- so without this the next player cannot tell the idea has
          already been spent, and the table burns a turn each on the same one.
        */}
        {wrong.length > 0 ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {wrong.map((move) => (
              <span
                key={move.item_label}
                className="text-muted-foreground flex items-center gap-1 text-xs"
              >
                <X className="text-destructive size-3 shrink-0" aria-hidden />
                <span className="line-through">{move.item_label}</span>
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
