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
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  getLobby,
  leaveLobby,
  markAway,
  restartLobby,
  skipReview,
  startGame,
  submitTurn,
  updateLobbySettings,
} from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { forgetPlayer, recallPlayer } from "@/lib/identity";
import { forgetPlayed, NO_PLAYED, playedSlugs, rememberPlayed } from "@/lib/played";
import { subscribeToLobby } from "@/lib/realtime";
import { shuffleBySeed } from "@/lib/shuffle";
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
  LobbySettings,
  LobbyView,
  ResolvedPair,
  SolvedItem,
  Subject,
} from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { cn } from "@/lib/utils";

import { RejoinForm } from "./rejoin-form";

const POLL_MS = 4_000;

/**
 * How long the host's choices settle before they are published.
 *
 * Long enough that ticking four subjects is one request rather than four, short
 * enough that the rest of the table sees the change while the host is still
 * looking at it.
 */
const SETTINGS_DEBOUNCE_MS = 400;

const COPIED_MS = 2_000;

const ROUND_CHOICES = [3, 5, 7, 10];

const TURN_CHOICES = [15, 30, 45, 60];

const DIFFICULTY_CHOICES: { level: Difficulty; label: string; bars: number }[] = [
  { level: "easy", label: "Easy", bars: 1 },
  { level: "medium", label: "Medium", bars: 2 },
  { level: "hard", label: "Hard", bars: 3 },
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
  const [localSetup, setLocalSetup] = useState<LobbySettings>({
    subject_slugs: subjects.slice(0, 3).map((subject) => subject.slug),
    difficulties: ["easy", "medium", "hard"],
    round_count: 5,
    turn_seconds: 30,
  });

  const versionRef = useRef(-1);

  /**
   * What the lobby was last known to hold for the host's choices, as JSON.
   *
   * Null until the first view says which way to sync — see `apply`, where that
   * is decided, and the effect below, which publishes. Comparing against it is
   * what keeps an adopted set from being echoed straight back.
   */
  const pushed = useRef<string | null>(null);

  const [turnDeadline, setTurnDeadline] = useState<number | null>(null);

  const [copiedAt, setCopiedAt] = useState<number | null>(null);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  /**
   * Take a lobby the server sent, and decide once which way settings sync.
   *
   * A lobby with subjects already on it has been set up before — a host who
   * reloaded, most likely — and adopting is the only way not to reset their own
   * choices behind their back. An untouched one keeps the defaults the controls
   * started with, and the effect below publishes those instead.
   *
   * Re-checked on every view rather than only the first, so the player who
   * inherits the host's chair when they leave is handled by the same path.
   */
  const apply = useCallback(
    (view: LobbyView) => {
      if (view.version < versionRef.current) return;
      versionRef.current = view.version;
      setLobby(view);
      setTurnDeadline((current) =>
        reconcileDeadline(current, deadlineFrom(view.turn_seconds_left)),
      );

      const hosting = Boolean(
        playerId && view.players.find((player) => player.id === playerId)?.is_host,
      );
      if (pushed.current !== null || !hosting || view.status !== "lobby") return;

      if (view.settings.subject_slugs.length > 0) {
        pushed.current = JSON.stringify(view.settings);
        setLocalSetup(view.settings);
      } else {
        pushed.current = "";
      }
    },
    [playerId],
  );

  const refresh = useCallback(async () => {
    try {
      const view = await getLobby(code, playerId);
      apply(view);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unknown error");
    }
  }, [code, playerId, apply]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();

    const unsubscribe = subscribeToLobby(code, (view) => {
      if (view) apply(view);
      else void refresh();
    });

    const timer = setInterval(() => void refresh(), POLL_MS);

    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, [code, refresh, apply]);

  const poke = useCallback(() => void refresh(), [refresh]);

  const turnSecondsLeft = useCountdown(turnDeadline, poke);

  useEffect(() => {
    if (!playerId) return;

    const onHide = () => markAway(code, playerId);
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [code, playerId]);

  const me = lobby?.players.find((player) => player.id === playerId) ?? null;
  const isMyTurn = Boolean(playerId && lobby?.current_player_id === playerId);
  const hostName =
    lobby?.players.find((player) => player.is_host)?.nickname ?? null;

  const onTheClock = isMyTurn && lobby?.status === "playing";

  const primed = useRef(false);
  const lastMove = useRef<string | null>(null);
  const wasOnTheClock = useRef(false);
  const lastStatus = useRef<string | null>(null);

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

    const moveKey = lobby.last_move
      ? `${lobby.round_index}:${lobby.history.length}:${lobby.last_move.item_label}`
      : null;

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

    if (onTheClock && !wasOnTheClock.current) playCue("yourTurn");
    wasOnTheClock.current = onTheClock;

    if (lobby.status !== lastStatus.current) {
      if (lobby.status === "reviewing") playCue("roundEnd");
      if (lobby.status === "finished") playCue("gameEnd");
      lastStatus.current = lobby.status;
    }
  }, [lobby, onTheClock]);

  useEffect(() => {
    if (!lobby) return;
    rememberPlayed(lobby.finished_rounds.map((round) => round.slug));
  }, [lobby]);

  useEffect(() => {
    if (!isMyTurn) return;
    if (turnSecondsLeft === null || turnSecondsLeft <= 0) return;
    if (turnSecondsLeft > HURRY_FROM) return;
    playCountdown(turnSecondsLeft);
  }, [turnSecondsLeft, isMyTurn]);

  const isHost = Boolean(me?.is_host);

  /**
   * Publish the host's choices, so the rest of the table can see them.
   *
   * The controls stay driven by local state, so a click lands at once rather
   * than after a round trip; what goes out is a copy for everyone else to read.
   * Debounced, because ticking four subjects is one decision.
   *
   * A push that fails is retried on the next poll rather than reverted, and
   * never adopted over: the host's own screen is the one place these choices
   * are certainly right, and a dropped request is no reason to argue with it.
   * Nothing is lost either way — starting the game sends them again.
   */
  useEffect(() => {
    if (!lobby || !playerId || !isHost) return;
    if (lobby.status !== "lobby") return;
    if (pushed.current === null) return;

    const wanted = JSON.stringify(localSetup);
    if (wanted === pushed.current) return;

    const timer = setTimeout(() => {
      pushed.current = wanted;
      updateLobbySettings(code, playerId, localSetup).then(apply, () => {
        pushed.current = "";
      });
    }, SETTINGS_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [lobby, playerId, isHost, localSetup, code, apply]);

  const [, forgetTick] = useState(0);
  const played = useStored(playedSlugs, NO_PLAYED);

  async function act(fn: () => Promise<LobbyView>) {
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
    const link = `${window.location.origin}/lobby/${code}`;
    if (!(await copyText(link))) {
      toast.error("Could not copy -- the code is right there to type in.");
      return;
    }

    toast.success("Invite link copied.");
    setCopiedAt(Date.now());
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopiedAt(null), COPIED_MS);
  }

  if (error && !lobby) return <ApiErrorNotice message={error} />;

  if (!lobby) {
    return (
      <p className="text-muted-foreground flex items-center gap-2 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading lobby {code}…
      </p>
    );
  }

  if (!playerId) return <RejoinForm code={code} />;

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

        <LobbySetup
          subjects={subjects}
          setup={me?.is_host ? localSetup : lobby.settings}
          readOnly={!me?.is_host}
          hostName={hostName}
          onChange={setLocalSetup}
          footer={
            me?.is_host ? (
              <Button
                onClick={() =>
                  playerId &&
                  act(() =>
                    startGame(
                      code,
                      playerId,
                      localSetup.subject_slugs,
                      localSetup.round_count,
                      localSetup.turn_seconds,
                      played,
                      localSetup.difficulties,
                    ),
                  )
                }
                disabled={
                  busy ||
                  localSetup.subject_slugs.length === 0 ||
                  lobby.players.length < 2
                }
              >
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Start game
              </Button>
            ) : null
          }
        >
          {me?.is_host && played.length > 0 ? (
            <div className="space-y-2">
              <Label>Already played</Label>
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-muted-foreground text-sm">
                  {played.length} question{played.length === 1 ? "" : "s"} will
                  be kept back where possible.
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
                Remembered on this device only, and used up once nothing new is
                left.
              </p>
            </div>
          ) : null}
        </LobbySetup>

        {me?.is_host ? null : (
          <p className="text-muted-foreground text-sm">
            Waiting for {hostName ?? "the host"} to start…
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

  const round = lobby.round_view;
  if (!round) return null;

  const currentPlayer = lobby.players.find(
    (player) => player.id === lobby.current_player_id,
  );
  const nextPlayer = lobby.players.find(
    (player) => player.id === lobby.next_player_id,
  );
  const reviewing = lobby.status === "reviewing";
  const lit = onTheClock;
  const overGlow = lit ? "text-foreground" : "text-muted-foreground";
  const justFinished = reviewing
    ? (lobby.finished_rounds[lobby.finished_rounds.length - 1] ?? null)
    : null;
  const total = round.remaining_items.length + round.solved_items.length;
  const solvedIn = (categoryId: string) =>
    round.solved_items.filter((item) => item.category_id === categoryId);

  const boardSeed = `${round.quiz_id}:${lobby.round_index}`;
  const categories = shuffleBySeed(round.categories, boardSeed, (c) => c.id);
  const remainingItems = shuffleBySeed(
    round.remaining_items,
    boardSeed,
    (item) => item.id,
  );

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
      <div
        className={cn(
          "quiz-room-glow",
          lit && "quiz-room-glow--on",
        )}
        aria-hidden
      />
      <div className="space-y-4">
        {header}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
          <div className="min-w-0 space-y-4">
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
                secondsLeft={reviewing ? null : turnSecondsLeft}
                totalSeconds={reviewing ? null : lobby.turn_seconds}
                deadline={reviewing ? null : turnDeadline}
              />
            </div>

            <Card
              className={cn(
                "animate-quiz-rise relative isolate overflow-hidden",
                lit && "border-primary/50 shadow-lg",
              )}
            >
              <div
                className={cn(
                  "quiz-ambient",
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
                  <div className="flex flex-col items-center gap-3 text-center">
                    <p className="flex items-center gap-2 text-base font-semibold">
                      <BookOpen className="size-4 shrink-0" aria-hidden />
                      Round over — the answers are below
                    </p>
                    <SourceLink source={justFinished?.source ?? null} />
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
                    <div className="flex flex-wrap justify-center gap-2.5">
                      {remainingItems.map((item) => (
                        <Button
                          key={item.id}
                          size="lg"
                          className={cn(
                            "quiz-shine h-auto min-h-14 px-6 py-3 text-lg font-semibold whitespace-normal",
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
                const full = solved.length > 0;
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
                    enterDelayMs={Math.min(index, 8) * 45}
                    onPlace={() => play(category.id)}
                  />
                );
              })}
            </div>
          </div>

          <aside className="space-y-4 lg:sticky lg:top-(--sticky-top)">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-1.5 text-sm">
                  <Users className="size-4" aria-hidden />
                  Turn order
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {lobby.players.map((player, index) => {
                  const theirTurn = player.id === lobby.current_player_id;
                  const upNext = player.id === lobby.next_player_id;
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

    const colour = "background-color 300ms ease";

    if (deadline === null) {
      el.style.transition = colour;
      el.style.width = "100%";
      return;
    }

    const remaining = Math.max(0, deadline - Date.now());
    const start = Math.min(100, (remaining / (totalSeconds * 1000)) * 100);

    el.style.transition = "none";
    el.style.width = `${start}%`;
    void el.offsetWidth;

    el.style.transition = `width ${remaining}ms linear, ${colour}`;
    el.style.width = "0%";
  }, [deadline, totalSeconds]);

  return (
    <span className={cn("h-1 w-16 overflow-hidden rounded-full", trackClass)} aria-hidden>
      <span ref={fill} className={cn("block h-full w-full", fillClass)} />
    </span>
  );
}

function SetupLabel({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <Label>{title}</Label>
      {hint ? (
        <span className="text-muted-foreground text-xs tabular-nums">{hint}</span>
      ) : null}
    </div>
  );
}

/**
 * One toggleable thing in the setup: a subject, a difficulty.
 *
 * Selection is carried three ways over, because one is never enough. Colour
 * does the work at a glance, the tick survives a colourblind reader, and the
 * size holds up in a photograph of a screen across a room -- which is roughly
 * the resolution this gets read at while a table argues about what to play.
 *
 * The wobble is on the inner span rather than the button, so the animation's
 * transform and the button's held `scale-105` never fight over the same
 * property -- together on one element, the chip would snap back to unscaled at
 * the moment the animation ended. It replays whenever the class returns, which
 * is exactly once per selection, and it plays for the players watching the host
 * pick as much as for the host: a chip that jumps is how the change announces
 * itself on somebody else's screen.
 */
function Chip({
  selected,
  disabled,
  onClick,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        "ease-(--ease-soft) rounded-4xl border px-3.5 py-2 text-sm font-medium transition-all duration-200",
        "focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-[3px]",
        selected
          ? "bg-primary text-primary-foreground border-primary scale-105 shadow-sm"
          : "bg-surface border-hairline text-foreground",
        !disabled &&
          !selected &&
          "hover:border-primary/40 hover:bg-surface-strong cursor-pointer",
        !disabled && selected && "cursor-pointer",
        disabled && "cursor-default",
      )}
    >
      <span
        className={cn(
          "flex items-center gap-1.5",
          selected && "animate-quiz-wobble",
        )}
      >
        {selected ? <Check className="size-3.5 shrink-0" aria-hidden /> : null}
        {children}
      </span>
    </button>
  );
}

function ChipCount({
  selected,
  children,
}: {
  selected: boolean;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "text-xs tabular-nums",
        selected ? "text-primary-foreground/70" : "text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

/**
 * How hard a rating is, as bars rather than a colour.
 *
 * Green and red already mean right and wrong everywhere else in this game, and
 * a difficulty picker is no place to teach them a second meaning. Height reads
 * as "more" without borrowing anything.
 */
function LevelBars({ filled, selected }: { filled: number; selected: boolean }) {
  return (
    <span className="flex items-end gap-[3px]" aria-hidden>
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className={cn(
            "w-[3px] rounded-full",
            ["h-1.5", "h-2.5", "h-3.5"][index],
            index < filled
              ? selected
                ? "bg-primary-foreground"
                : "bg-foreground/60"
              : selected
                ? "bg-primary-foreground/25"
                : "bg-muted-foreground/25",
          )}
        />
      ))}
    </span>
  );
}

/**
 * One-of-several, as a track with the choice sliding between the options.
 *
 * No held scale here, unlike `Chip`: these sit in a fixed row, and a pill that
 * grew would push its neighbours around every time the choice moved.
 */
function Segmented({
  options,
  value,
  disabled,
  onSelect,
  format = String,
}: {
  options: number[];
  value: number;
  disabled?: boolean;
  onSelect: (value: number) => void;
  format?: (value: number) => string;
}) {
  return (
    <div className="bg-surface border-hairline inline-flex rounded-4xl border p-1">
      {options.map((option) => {
        const on = option === value;
        return (
          <button
            key={option}
            type="button"
            onClick={() => onSelect(option)}
            disabled={disabled}
            aria-pressed={on}
            className={cn(
              "ease-(--ease-soft) rounded-4xl px-3.5 py-1.5 text-sm font-medium tabular-nums transition-all duration-200",
              "focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-[3px]",
              on
                ? "bg-primary text-primary-foreground animate-quiz-pop shadow-sm"
                : "text-muted-foreground",
              !disabled && !on && "hover:text-foreground cursor-pointer",
              !disabled && on && "cursor-pointer",
            )}
          >
            {format(option)}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The game being set up, for whoever is looking at it.
 *
 * One component for both sides on purpose. The host's controls and the read-only
 * copy the others see are the same thing seen from two chairs, and a second
 * component would be a second version of the truth -- the first setting either
 * one grew that the other did not would go unnoticed until somebody at the table
 * asked why their screen disagreed.
 *
 * `readOnly` disables rather than hides: a ticked box that cannot be clicked
 * still says what was chosen, which is the whole point of showing it.
 */
function LobbySetup({
  subjects,
  setup,
  readOnly,
  hostName,
  onChange,
  children,
  footer,
}: {
  subjects: Subject[];
  setup: LobbySettings;
  readOnly: boolean;
  hostName: string | null;
  onChange: (next: LobbySettings) => void;
  /** Rendered at the end of the card body. The host's device-only settings. */
  children?: React.ReactNode;
  /** Rendered in the card footer. The host's start button, and nobody else's. */
  footer?: React.ReactNode;
}) {
  const chosen = subjects.filter((subject) =>
    setup.subject_slugs.includes(subject.slug),
  );

  const countAt = (level: Difficulty) =>
    chosen.reduce(
      (total, subject) => total + (subject.difficulty_counts[level] ?? 0),
      0,
    );

  const availableQuestions = setup.difficulties.reduce(
    (total, level) => total + countAt(level),
    0,
  );

  const patch = (next: Partial<LobbySettings>) => onChange({ ...setup, ...next });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {readOnly ? "The game being set up" : "Set up the game"}
        </CardTitle>
        <CardDescription>
          {readOnly
            ? `${hostName ?? "The host"} chooses these — they change as they are picked.`
            : "Questions are drawn at random from whatever you choose, spread as evenly as possible across them."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <section className="space-y-2.5">
          <SetupLabel
            title="Subjects"
            hint={
              chosen.length > 0
                ? `${chosen.length} of ${subjects.length}`
                : "Pick at least one"
            }
          />
          <div className="flex flex-wrap gap-2.5">
            {subjects.map((subject) => {
              const on = setup.subject_slugs.includes(subject.slug);
              return (
                <Chip
                  key={subject.slug}
                  selected={on}
                  disabled={readOnly}
                  onClick={() =>
                    patch({
                      subject_slugs: on
                        ? setup.subject_slugs.filter((slug) => slug !== subject.slug)
                        : [...setup.subject_slugs, subject.slug],
                    })
                  }
                >
                  {subject.name}
                  <ChipCount selected={on}>{subject.quiz_count}</ChipCount>
                </Chip>
              );
            })}
          </div>
        </section>

        <section className="space-y-2.5">
          <SetupLabel title="Difficulty" />
          <div className="flex flex-wrap gap-2.5">
            {DIFFICULTY_CHOICES.map(({ level, label, bars }) => {
              const on = setup.difficulties.includes(level);
              const onlyOneLeft = on && setup.difficulties.length === 1;
              return (
                <Chip
                  key={level}
                  selected={on}
                  disabled={readOnly || onlyOneLeft}
                  onClick={() =>
                    patch({
                      difficulties: on
                        ? setup.difficulties.filter((each) => each !== level)
                        : [...setup.difficulties, level],
                    })
                  }
                >
                  <LevelBars filled={bars} selected={on} />
                  {label}
                  <ChipCount selected={on}>{countAt(level)}</ChipCount>
                </Chip>
              );
            })}
          </div>
        </section>

        <div className="grid gap-5 sm:grid-cols-2">
          <section className="space-y-2.5">
            <SetupLabel title="Rounds" />
            <Segmented
              options={ROUND_CHOICES}
              value={setup.round_count}
              disabled={readOnly}
              onSelect={(n) => patch({ round_count: n })}
            />
          </section>

          <section className="space-y-2.5">
            <SetupLabel title="Seconds per turn" />
            <Segmented
              options={TURN_CHOICES}
              value={setup.turn_seconds}
              disabled={readOnly}
              format={(n) => `${n}s`}
              onSelect={(n) => patch({ turn_seconds: n })}
            />
          </section>
        </div>

        {setup.subject_slugs.length > 0 && setup.round_count > availableQuestions ? (
          <p className="text-muted-foreground text-sm">
            Only {availableQuestions} question
            {availableQuestions === 1 ? "" : "s"} available in the chosen subjects
            — the game will be that short.
          </p>
        ) : null}

        <p className="text-muted-foreground text-sm">
          Run out of time and you are out for the round, the same as a wrong
          answer. Whoever opens a round gets a little longer — they are the one
          reading the board cold.
        </p>

        {children}
      </CardContent>
      {footer ? <CardFooter>{footer}</CardFooter> : null}
    </Card>
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
  const urgent = !reviewing && secondsLeft !== null && secondsLeft <= HURRY_FROM;

  return (
    <div
      className={cn(
        "ease-(--ease-soft) flex items-center gap-3 rounded-(--radius) border px-4 py-3 shadow-sm backdrop-blur transition-colors duration-300",
        isMyTurn && !reviewing
          ? "bg-primary text-primary-foreground border-primary animate-quiz-glow"
          : "bg-surface border-hairline",
      )}
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
        armed &&
          "ring-primary/60 hover:ring-primary cursor-pointer hover:-translate-y-1 hover:scale-[1.02] hover:shadow-xl",
        full && !reveal && "bg-muted/50 opacity-60",
        missed && "border-amber-500/50",
      )}
      style={{ animationDelay: `${enterDelayMs}ms` }}
      onClick={armed ? onPlace : undefined}
      aria-disabled={full || undefined}
    >
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
            wrong.length === 0 ? (
              <p className="text-muted-foreground text-sm">Empty</p>
            ) : null
          ) : (
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
          {missed ? (
            <span className="text-muted-foreground text-xs">unsolved</span>
          ) : null}
        </div>

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
        {reveal?.explanation ? (
          <p className="text-muted-foreground text-sm">{reveal.explanation}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
