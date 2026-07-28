"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Check,
  Crown,
  Loader2,
  LogOut,
  Timer,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { ApiErrorNotice } from "@/components/api-error-notice";
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
import { deadlineFrom, useCountdown } from "@/lib/use-countdown";
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
    // Turned into wall-clock deadlines the moment they arrive, so the
    // countdowns can tick without asking the server again.
    setReviewDeadline(deadlineFrom(view.review_seconds_left));
    setTurnDeadline(deadlineFrom(view.turn_seconds_left));
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

  // Lets the host see when they have asked for more rounds than the chosen
  // subjects can supply, rather than silently getting a shorter game.
  const availableQuestions = subjects
    .filter((subject) => chosenSubjects.includes(subject.slug))
    .reduce((total, subject) => total + subject.quiz_count, 0);

  async function act(fn: () => Promise<LobbyView>) {
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
        <Button variant="ghost" size="sm" onClick={leave} disabled={busy}>
          <LogOut className="size-4" aria-hidden />
          Leave
        </Button>
      </div>
    </div>
  );

  const scoreboard = (
    <div className="flex flex-wrap gap-2">
      {[...lobby.players]
        .sort((a, b) => b.score - a.score)
        .map((player) => (
          <Badge
            key={player.id}
            variant={player.id === lobby.current_player_id ? "default" : "outline"}
            className={cn(
              "gap-1.5",
              (!player.is_active || !player.is_connected) && "opacity-50",
            )}
          >
            {player.id === playerId ? `${player.nickname} (you)` : player.nickname}
            <span className="font-mono">{player.score}</span>
            {!player.is_connected ? (
              <WifiOff className="size-3" aria-label="offline" />
            ) : !player.is_active ? (
              <X className="size-3" aria-label="out" />
            ) : null}
          </Badge>
        ))}
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

  return (
    <div className="space-y-6">
      {header}

      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">{round.title}</h1>
            <DifficultyBadge difficulty={round.difficulty} />
          </div>
          <p className="text-muted-foreground text-sm">
            Round {lobby.round_index + 1} of {lobby.round_count}
          </p>
        </div>
        <Progress value={(round.solved_items.length / Math.max(total, 1)) * 100} />
        {round.description ? (
          <p className="text-muted-foreground text-sm">{round.description}</p>
        ) : null}
        {lobby.subject_names.length > 0 ? (
          <p className="text-muted-foreground text-xs">
            Drawn from: {lobby.subject_names.join(", ")}
          </p>
        ) : null}
      </div>

      {scoreboard}

      {lobby.last_move ? (
        <p
          className={cn(
            "flex items-center gap-2 rounded-md border px-3 py-2 text-sm",
            lobby.last_move.was_correct
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-destructive",
          )}
        >
          {lobby.last_move.was_correct ? (
            <Check className="size-4 shrink-0" aria-hidden />
          ) : (
            <X className="size-4 shrink-0" aria-hidden />
          )}
          <span>
            <strong>{lobby.last_move.nickname}</strong> played{" "}
            <strong>{lobby.last_move.item_label}</strong> —{" "}
            {lobby.last_move.was_correct ? "correct" : "wrong, out this round"}
          </span>
        </p>
      ) : null}

      <Separator />

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
      <Card>
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
        <CardContent className="flex flex-wrap gap-2">
          {round.remaining_items.map((item) => (
            <Button
              key={item.id}
              size="sm"
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
        {round.categories.map((category) => {
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
              reveal={reveal}
              armed={isMyTurn && selectedItemId !== null && !busy && !full}
              onPlace={() => play(category.id)}
            />
          );
        })}
      </div>
    </div>
  );
}

function CategoryCard({
  title,
  solved,
  full,
  reveal,
  armed,
  onPlace,
}: {
  title: string;
  solved: { item_id: string; label: string }[];
  /** Already holds its one answer, so it is done for this round. */
  full: boolean;
  /** Set only between rounds: the answer and why, whether or not it was found. */
  reveal: ResolvedPair | null;
  armed: boolean;
  onPlace: () => void;
}) {
  const missed = reveal !== null && reveal.solved_by === null;

  return (
    <Card
      className={cn(
        "transition-colors",
        armed && "border-primary cursor-pointer",
        // Greyed out rather than hidden: the pairing so far is what players
        // reason from when placing what is left.
        full && !reveal && "bg-muted/50 opacity-60",
        // Nobody got this one, so it is the one worth looking at.
        missed && "border-amber-500/50",
      )}
      onClick={armed ? onPlace : undefined}
      aria-disabled={full || undefined}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {full ? (
            <Check
              className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
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
            <p className="text-muted-foreground text-sm">Empty</p>
          ) : (
            solved.map((item) => (
              <Badge key={item.item_id} variant="secondary">
                {item.label}
              </Badge>
            ))
          )}
          {missed ? (
            <span className="text-muted-foreground text-xs">nobody got this</span>
          ) : null}
        </div>
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
