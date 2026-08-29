"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Check,
  Copy,
  Crown,
  History,
  Loader2,
  Lock,
  LogOut,
  RotateCcw,
  Timer,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { CategoryPicture, ImageCredit } from "@/components/category-image";
import { AnswerPool } from "@/components/answer-pool";
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
  pokerAct,
  pokerAnswer,
  pokerBack,
  markAway,
  readyForNextRound,
  restartLobby,
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
  GameMode,
  LastMove,
  LobbySettings,
  LobbyView,
  ResolvedPair,
  SolvedItem,
  Subject,
} from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { cn } from "@/lib/utils";

import { PokerTable } from "./poker-table";
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

/**
 * How long the count-in before a round lasts, mirroring `NEXT_ROUND_COUNTDOWN`
 * in `api/app/services/lobbies.py`.
 *
 * The server owns the rule — this is only what the draining bar treats as full,
 * and every number on screen still comes from the deadline the server set. A
 * copy that drifted would cost a bar that starts part-drained, nothing more.
 */
const NEXT_ROUND_SECONDS = 3;

/**
 * The modes, in the order they are offered. Named here rather than taken from
 * the mode value itself so the label is a decision someone made, not a
 * capitalised slug that changes meaning the day a mode is renamed.
 */
const MODE_CHOICES: GameMode[] = ["classic", "poker"];

const MODE_LABELS: Record<GameMode, string> = {
  classic: "Classic",
  poker: "Poker",
};

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
  /**
   * What the setup starts on: everything ticked.
   *
   * A host who wants the whole pool -- which is most of them, and is the game
   * as written -- has nothing to do but start. Narrowing it is the deliberate
   * act, and unticking what you do not want is a shorter job than finding what
   * you do among a dozen subjects.
   */
  const [localSetup, setLocalSetup] = useState<LobbySettings>({
    mode: "classic",
    subject_slugs: subjects.map((subject) => subject.slug),
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

  /**
   * When the next round begins, once enough players have asked for it.
   *
   * A second clock rather than a mode of the turn one: they can never run
   * together — the review has no turns — but they are set from different
   * fields, and folding them into one state would mean deciding which of the
   * two an arriving view was talking about on every poll.
   */
  const [nextRoundDeadline, setNextRoundDeadline] = useState<number | null>(null);
  const [pokerDeadline, setPokerDeadline] = useState<number | null>(null);

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
      setNextRoundDeadline((current) =>
        reconcileDeadline(current, deadlineFrom(view.next_round_in)),
      );
      setPokerDeadline((current) =>
        reconcileDeadline(current, deadlineFrom(view.poker?.seconds_left ?? null)),
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
  const nextRoundIn = useCountdown(nextRoundDeadline, poke);
  /**
   * The poker table's clock, whichever one it is running -- betting, answering
   * or the wait for the next hand. Ticked here rather than read off the view so
   * the number moves between polls, and so `onExpire` knocks: the server acts
   * on a deadline only when a request finds it passed.
   */
  const pokerSecondsLeft = useCountdown(pokerDeadline, poke);

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

  /**
   * The count-in before a round, in the same escalating cue the turn clock
   * uses. Unlike that one it plays on every device at once, which is the
   * point — it is the one moment in the game where the whole table is being
   * counted in together, and hearing it is what makes people look up.
   */
  useEffect(() => {
    if (nextRoundIn === null || nextRoundIn <= 0) return;
    if (nextRoundIn > HURRY_FROM) return;
    playCountdown(nextRoundIn);
  }, [nextRoundIn]);

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

  /**
   * A running game gets a smaller version of the room header.
   *
   * The lobby code is what the screen is *for* while people are still joining,
   * and once they have joined it is a label nobody reads again — but the
   * controls beside it (leave, sound) have to stay reachable. So it shrinks
   * rather than goes, and only where height is being fought over.
   */
  const playing = lobby.status === "playing" || lobby.status === "reviewing";

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p
          className={cn(
            "text-muted-foreground text-sm",
            playing && "lg:hidden",
          )}
        >
          Lobby code
        </p>
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
              playing && "lg:text-xl",
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
      /* Tight enough that the start button is on the screen with the settings
         it starts: a host who has to scroll to it has to scroll back to change
         their mind. */
      <div className="mx-auto w-full max-w-2xl space-y-4">
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
                      localSetup.mode,
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
      <div className="mx-auto w-full max-w-2xl space-y-4">
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
          <CardFooter>
            <NewRound
              isHost={Boolean(me?.is_host)}
              hostName={hostName}
              busy={busy}
              onRestart={() =>
                playerId && act(() => restartLobby(code, playerId))
              }
            />
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

  if (lobby.poker) {
    return (
      <div className="space-y-3">
        {header}
        <PokerTable
          lobby={lobby}
          poker={lobby.poker}
          playerId={playerId}
          secondsLeft={pokerSecondsLeft}
          busy={busy}
          onAct={(action, amount) =>
            act(() => pokerAct(code, playerId, action, amount))
          }
          onAnswer={(itemId) => act(() => pokerAnswer(code, playerId, itemId))}
          onBack={(backedId) => act(() => pokerBack(code, playerId, backedId))}
        />
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
      {/*
        From `lg` up the board is sized to the screen rather than to its own
        contents: the shell hands this column the exact height that is left, the
        parts that must be read whole (the turn bar, the question) take what they
        need, and the categories divide the remainder between them. Below that
        breakpoint none of it applies — a phone cannot fit a board however it is
        laid out, and pretending otherwise would shrink the answers to nothing
        rather than let the page scroll like a page.
      */}
      {/*
        And it takes the whole screen, not the reading measure the rest of the
        app is set in.

        Everywhere else a column of prose wants to stay narrow. A board is the
        opposite: width is what buys height back, because every extra column of
        categories is one row fewer to find room for. On a 1440-wide screen that
        is the difference between four rows of cards and three, and between the
        answers wrapping onto a second line and not.
      */}
      <div className="mx-auto w-full max-w-5xl space-y-3 lg:flex lg:min-h-0 lg:max-w-[110rem] lg:flex-1 lg:flex-col lg:gap-2 lg:space-y-0">
        <div className="lg:shrink-0">{header}</div>

        <div className="grid gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="min-w-0 space-y-3 lg:flex lg:min-h-0 lg:flex-col lg:gap-3 lg:space-y-0">
            <div className="sticky top-0 z-20 lg:static lg:shrink-0">
              <TurnBar
                isMyTurn={isMyTurn}
                isOut={Boolean(me && !me.is_active)}
                isCatchUp={lobby.is_catch_up}
                reviewing={reviewing}
                hasSelection={selectedItemId !== null}
                currentName={currentPlayer?.nickname ?? null}
                nextName={nextPlayer?.nickname ?? null}
                quiet={lobby.current_player_quiet}
                readyCount={lobby.ready_ids.length}
                readyNeeded={lobby.ready_needed}
                nextRoundIn={reviewing ? nextRoundIn : null}
                secondsLeft={reviewing ? nextRoundIn : turnSecondsLeft}
                totalSeconds={reviewing ? NEXT_ROUND_SECONDS : lobby.turn_seconds}
                deadline={reviewing ? nextRoundDeadline : turnDeadline}
              />
            </div>

            <Card
              className={cn(
                /* `overflow-visible` against the base card, which hides it.
                   The answers inside lift and scale on hover and grow an
                   outline when picked, and all of that happens at the edge of
                   this card -- clipped here, the chip on the end of a row loses
                   the very outline that says it is the one selected. The glow
                   below still needs clipping, so it gets its own clipper rather
                   than the card wearing one for it. */
                "animate-quiz-rise relative isolate overflow-visible",
                "lg:shrink-0 lg:[--card-spacing:--spacing(3)]",
                lit && "border-primary/50 shadow-lg",
              )}
            >
              <div
                className="pointer-events-none absolute inset-0 overflow-hidden rounded-xl"
                aria-hidden
              >
                <div className={cn("quiz-ambient", lit && "quiz-ambient--yours")} />
              </div>
              <CardHeader className="space-y-1.5 text-center lg:space-y-1">
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
                {/* Deliberately smaller from `lg` than below it: on a phone
                    this headline has the screen to itself, on a laptop it is
                    sharing a fixed height with the board it belongs to. */}
                <h1 className="text-3xl font-black tracking-tight text-balance sm:text-4xl lg:text-2xl xl:text-3xl">
                  {round.title}
                </h1>
                {round.description ? (
                  <p
                    className={cn(
                      "mx-auto max-w-prose text-base text-balance lg:text-sm xl:text-base",
                      overGlow,
                    )}
                  >
                    {round.description}
                  </p>
                ) : null}
                <div className="flex items-center justify-center gap-2 pt-1">
                  {round.subject_name ? (
                    <Badge variant="outline">{round.subject_name}</Badge>
                  ) : null}
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
                  <div className="flex flex-col items-center gap-4 text-center lg:gap-2">
                    {/* A signpost for a screen you have to scroll. Where the
                        answers are already in view it is only taking their
                        room, and the turn bar has said "Round over" anyway. */}
                    <p className="flex items-center gap-2 text-base font-semibold lg:hidden">
                      <BookOpen className="size-4 shrink-0" aria-hidden />
                      Round over — the answers are below
                    </p>
                    <SourceLink source={justFinished?.source ?? null} />
                    <NextRoundVote
                      ready={Boolean(playerId && lobby.ready_ids.includes(playerId))}
                      readyCount={lobby.ready_ids.length}
                      readyNeeded={lobby.ready_needed}
                      secondsLeft={nextRoundIn}
                      busy={busy}
                      onReady={() =>
                        playerId && act(() => readyForNextRound(code, playerId))
                      }
                    />
                  </div>
                ) : (
                  <>
                    <AnswerPool
                      items={remainingItems}
                      selectedId={selectedItemId}
                      disabled={!isMyTurn || busy}
                      onSelect={setSelectedItemId}
                    />
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

            {/*
              Wrapping flex rather than a grid, because a grid leaves a short
              last row hanging off the left edge under the row above it — ten
              categories seven to a row put three of them there. Wrapped lines
              can be centred, so the board stays a block whatever the count
              divides into.

              The height left over is divided between the lines: `content-stretch`
              hands each an equal share of what is spare, and the cards may be
              shorter than their contents (`min-h-0`), so the pictures give way
              rather than the board growing past the screen. `overflow-y-auto` is
              the last resort and nothing more — ten categories on a laptop in
              landscape will still find the floor.

              That scroller is why this has padding. Asking for one scrolling
              axis gives you clipping on both, and an armed card lifts and scales
              outside its own box — against a bare edge the whole top row was
              shaved flat, which read as the zoom being broken rather than as the
              board being tight. The padding is the room the transform needs;
              content is clipped at the padding box, not the border box.
            */}
            <div className="grid gap-4 sm:grid-cols-2 lg:flex lg:min-h-0 lg:flex-1 lg:flex-wrap lg:content-stretch lg:justify-center lg:gap-3 lg:overflow-y-auto lg:p-2">
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

          <aside className="space-y-4 lg:flex lg:min-h-0 lg:flex-col lg:gap-3 lg:space-y-0">
            <Card className="lg:shrink-0">
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
              <Card className="lg:min-h-0 lg:flex-1">
                <CardHeader className="pb-3 lg:shrink-0">
                  <CardTitle className="flex items-center gap-1.5 text-sm">
                    <History className="size-4" aria-hidden />
                    This round
                  </CardTitle>
                </CardHeader>
                {/* The one list on the board with no end to it, so it takes
                    whatever the column has left and scrolls inside that. */}
                <CardContent className="max-h-72 space-y-1 overflow-y-auto lg:max-h-none lg:min-h-0 lg:flex-1">
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

      {reviewing && nextRoundIn !== null ? (
        <NextRoundCountdown secondsLeft={nextRoundIn} />
      ) : null}
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
 * The zoom is a scale and nothing else -- no rotation, no travel. The chip
 * swells around its own centre and settles back, so the eye is drawn to it
 * without anything appearing to leave its place. It goes on the button rather
 * than the contents, or the label would grow out past a pill that stayed put.
 * The held `scale-105` and the animation can share the button because they
 * drive different properties, `scale` and `transform`, which compose instead of
 * overwriting each other -- on one property the chip would snap back to
 * unscaled the moment the animation ended. It replays whenever the class
 * returns, which is exactly once per selection, and it plays for the players
 * watching the host pick as much as for the host: a chip that reacts is how the
 * change announces itself on somebody else's screen.
 *
 * The tick keeps its slot whether or not it is showing. Letting it in and out of
 * the flow would resize the chip by the width of an icon, and in a wrapping row
 * that shoves every later chip sideways and sometimes onto another line -- the
 * whole block jumping each time one thing is ticked.
 *
 * `muted` is not `disabled`. Disabled is what the chip does; muted is what it
 * looks like it does, and the two only coincide for the players watching. The
 * host's own last difficulty is disabled too -- unticking it would leave nothing
 * to draw from -- and dimming that one would say the whole row had gone away
 * rather than that this single chip is holding the floor.
 */
function Chip({
  selected,
  disabled,
  muted,
  onClick,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  /** Show as out of reach: somebody else's control, not yours to click. */
  muted?: boolean;
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
          ? "bg-primary text-primary-foreground border-primary animate-quiz-zoom scale-105 shadow-sm"
          : "bg-surface border-hairline text-foreground",
        !disabled &&
          !selected &&
          "hover:border-primary/40 hover:bg-surface-strong cursor-pointer",
        !disabled && selected && "cursor-pointer",
        disabled && "cursor-default",
        muted && "opacity-60 shadow-none saturate-50",
      )}
    >
      <span className="flex items-center gap-1.5">
        <Check
          className={cn(
            "ease-(--ease-soft) size-3.5 shrink-0 transition-opacity duration-200",
            selected ? "opacity-100" : "opacity-0",
          )}
          aria-hidden
        />
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
function Segmented<T extends string | number>({
  options,
  value,
  disabled,
  muted,
  onSelect,
  format = String,
}: {
  options: T[];
  value: T;
  disabled?: boolean;
  /** Show as out of reach: somebody else's control, not yours to click. */
  muted?: boolean;
  onSelect: (value: T) => void;
  format?: (value: T) => string;
}) {
  return (
    <div
      className={cn(
        "bg-surface border-hairline inline-flex rounded-4xl border p-1",
        muted && "opacity-60 saturate-50",
      )}
    >
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
 * still says what was chosen, which is the whole point of showing it. It is
 * also dimmed, because a control that looks live and does nothing reads as a
 * broken screen rather than somebody else's turn to choose -- and the dimming
 * stops at the controls. The labels, the counts and the wording stay at full
 * strength, since those are what the players came to this card to read.
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
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {readOnly ? "The game being set up" : "Set up the game"}
          {readOnly ? (
            <Badge variant="outline" className="gap-1 font-normal">
              <Lock className="size-3" aria-hidden />
              Host only
            </Badge>
          ) : null}
        </CardTitle>
        <CardDescription>
          {readOnly
            ? `${hostName ?? "The host"} chooses these — they change as they are picked.`
            : "Questions are drawn at random from whatever you choose, spread as evenly as possible across them."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <section className="space-y-2.5">
          <SetupLabel title="Game mode" />
          <Segmented
            options={MODE_CHOICES}
            value={setup.mode}
            disabled={readOnly}
            muted={readOnly}
            format={(mode) => MODE_LABELS[mode]}
            onSelect={(mode) => patch({ mode })}
          />
        </section>

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
                  muted={readOnly}
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
                  muted={readOnly}
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

        <div className="grid gap-4 sm:grid-cols-2">
          <section className="space-y-2.5">
            <SetupLabel title="Rounds" />
            <Segmented
              options={ROUND_CHOICES}
              value={setup.round_count}
              disabled={readOnly}
              muted={readOnly}
              onSelect={(n) => patch({ round_count: n })}
            />
          </section>

          <section className="space-y-2.5">
            <SetupLabel title="Seconds per turn" />
            <Segmented
              options={TURN_CHOICES}
              value={setup.turn_seconds}
              disabled={readOnly}
              muted={readOnly}
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

/**
 * The way out of a review: a button on every screen, and a tally of who has
 * pressed it.
 *
 * It used to be the host's alone, which put the one decision everybody at the
 * table has an opinion about — "are we done reading?" — in the hands of the
 * person least likely to still be reading, and left every other screen with
 * nothing to press. So the button is on all of them, it is the size of the
 * decision rather than the size of a toolbar control, and half of those present
 * carry it.
 *
 * Once they do it stops being a button at all and becomes the count-in, in the
 * same place and at the same size. Nothing moves on the screen and there is
 * nothing left to click: what was being asked has been answered, and the only
 * thing left to do is look up.
 */
function NextRoundVote({
  ready,
  readyCount,
  readyNeeded,
  secondsLeft,
  busy,
  onReady,
}: {
  /** You have already asked, so the button is spent — for you. */
  ready: boolean;
  readyCount: number;
  /** How many asks start the countdown: half of those present, rounded up. */
  readyNeeded: number;
  /** Seconds until the round begins, or null while nothing is counting. */
  secondsLeft: number | null;
  busy: boolean;
  onReady: () => void;
}) {
  const counting = secondsLeft !== null;

  return (
    <div className="w-full max-w-sm space-y-3 lg:space-y-2">
      {counting ? (
        <div className="border-primary bg-primary text-primary-foreground animate-quiz-glow flex h-16 w-full items-center justify-center gap-3 rounded-(--radius) border lg:h-12">
          <span className="text-sm font-bold tracking-wide uppercase">
            Next round in
          </span>
          <span
            key={secondsLeft}
            className="animate-quiz-pop font-mono text-4xl leading-none font-black tabular-nums"
          >
            {Math.max(secondsLeft, 0)}
          </span>
        </div>
      ) : (
        <Button
          size="lg"
          variant={ready ? "outline" : "default"}
          className={cn(
            "ease-(--ease-soft) h-16 w-full text-xl font-bold transition-all duration-200 lg:h-12",
            !ready &&
              "quiz-shine hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-xl active:translate-y-0 active:scale-[0.99]",
          )}
          disabled={busy || ready}
          onClick={onReady}
        >
          {busy ? (
            <Loader2 className="size-5 animate-spin" aria-hidden />
          ) : ready ? (
            <Check className="size-5" aria-hidden />
          ) : null}
          {ready ? "You are ready" : "Next round"}
        </Button>
      )}

      <Progress
        value={(Math.min(readyCount, readyNeeded) / Math.max(readyNeeded, 1)) * 100}
        className="h-1.5"
      />
      <p className="text-muted-foreground text-sm">
        {counting
          ? "Everybody get ready…"
          : `${readyCount} of ${readyNeeded} ready — ${
              ready
                ? "waiting for the others"
                : "press it once you have read the answers"
            }`}
      </p>
    </div>
  );
}

/**
 * The count-in, over the whole screen.
 *
 * The point of the three seconds is that everybody spends them looking at the
 * same number, and a number inside a card is something you have to already be
 * looking at to see. This is deliberately impossible to miss and deliberately
 * brief.
 *
 * It does not take the pointer: the answers underneath stay readable and
 * clickable for the seconds that are left, and there is nothing here to press
 * anyway. It is silent to a screen reader too — the turn bar is a live region
 * and already says the same thing, and announcing it twice a second would bury
 * everything else.
 */
function NextRoundCountdown({ secondsLeft }: { secondsLeft: number }) {
  const shown = secondsLeft > 0 ? String(secondsLeft) : "Go!";

  /**
   * The number that has just been replaced, kept on screen while it leaves.
   *
   * Re-keying one element swaps the text within a single frame: the old number
   * is gone before the new one has started, which is the cut this avoids. Two
   * elements in the same grid cell can overlap instead, the outgoing one fading
   * out over the incoming one's rise.
   *
   * It is never unmounted — its animation ends at opacity zero and stays there,
   * and re-keying it is what replays that. Clearing it on a timer would buy an
   * invisible element's worth of nothing, and cost a timer per second.
   */
  const [swap, setSwap] = useState({ shown, leaving: null as string | null });
  if (swap.shown !== shown) setSwap({ shown, leaving: swap.shown });

  const size = (value: string) =>
    value === "Go!"
      ? "text-6xl sm:text-8xl"
      : "font-mono text-[7rem] tabular-nums sm:text-[10rem]";

  return (
    <div
      className="bg-background/70 pointer-events-none fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 backdrop-blur-sm"
      aria-hidden
    >
      <p className="text-muted-foreground text-xs font-bold tracking-[0.3em] uppercase">
        Next round
      </p>
      <span className="grid place-items-center">
        {swap.leaving !== null ? (
          <span
            key={`out-${swap.leaving}`}
            className={cn(
              "animate-quiz-count-out text-primary col-start-1 row-start-1 leading-none font-black",
              size(swap.leaving),
            )}
          >
            {swap.leaving}
          </span>
        ) : null}
        <span
          key={shown}
          className={cn(
            "animate-quiz-count-in text-primary col-start-1 row-start-1 leading-none font-black",
            size(shown),
          )}
        >
          {shown}
        </span>
      </span>
    </div>
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
  readyCount,
  readyNeeded,
  nextRoundIn,
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
  /** How many have asked for the next round, and how many it takes. */
  readyCount: number;
  readyNeeded: number;
  /** Seconds until the round begins, or null while nothing is counting. */
  nextRoundIn: number | null;
  secondsLeft: number | null;
  /** What the clock started from, for the bar. */
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
            ? nextRoundIn !== null
              ? "Get ready"
              : "Round over"
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
            ? nextRoundIn !== null
              ? `The next round starts in ${Math.max(nextRoundIn, 0)}…`
              : `${readyCount} of ${readyNeeded} ready for the next round`
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
        "lg:min-h-0 lg:[--card-spacing:--spacing(2)]",
        /* The card carries its own width now that the parent names no tracks,
           and it is stated as a share of the line rather than in pixels:
           `100%/n` less the gaps that n cards leave between them.

           That is what makes the board fill its column instead of floating in
           the middle of it — a fixed basis left ~90px of dead air down each
           side while the question card above ran edge to edge. Growing into the
           line instead would fill it, but only line by line: a last row of two
           came out wider than the four above it. A share of the line is the
           same width on every row, so the remainder is simply centred and short
           rather than centred and wrong.

           Column counts are chosen against what the column is actually wide —
           the 18rem of turn order beside it means `xl` here is roughly `lg`
           elsewhere. A board of ten then falls 4+4+2, and 5+5 once there is
           room for five. */
        "lg:min-w-0 lg:grow-0",
        "lg:basis-[calc(33.333%_-_0.5rem)]",
        "xl:basis-[calc(25%_-_0.5625rem)]",
        "2xl:basis-[calc(20%_-_0.6rem)]",
        armed &&
          /* Lifted, it overlaps its neighbours, and the ones after it in the
             board would otherwise paint over the lift. */
          "ring-primary/60 hover:ring-primary relative cursor-pointer hover:z-10 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-xl",
        full && !reveal && "bg-muted/50 opacity-60",
        missed && "border-amber-500/50",
      )}
      style={{ animationDelay: `${enterDelayMs}ms` }}
      onClick={armed ? onPlace : undefined}
      aria-disabled={full || undefined}
    >
      {image ? (
        /*
         * The picture is the give in a category card. Everything else on it is
         * words that have to stay whole, so on a board sized to the screen the
         * photograph takes what is left of the card instead of dictating the
         * card's height — a fixed 4:3 in a row that has to fit would push the
         * labels off the bottom. Below `lg` the board is not height-bound and
         * the aspect ratio is what stops the image from collapsing.
         */
        /* A floor, so a picture round never ends up with no pictures — scaled
           to how much height there is to give. Under it the grid scrolls, which
           on a board of ten photographs is the honest outcome. */
        <div className="px-6 lg:min-h-16 lg:flex-1 lg:px-4 lg:[@media(min-height:860px)]:min-h-20">
          <CategoryPicture
            image={image}
            label={title ?? "Bild"}
            armed={armed}
            className="aspect-[4/3] w-full rounded-(--radius-sm) lg:aspect-auto lg:h-full"
          />
        </div>
      ) : null}
      <CardHeader className="lg:shrink-0">
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
      <CardContent className="min-h-14 space-y-2 lg:min-h-8 lg:shrink-0">
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

/**
 * The one thing left to do once a game is over: ask for another round.
 *
 * Only the host can restart, so for everybody else the button sends nothing.
 * It does not need to — the restart lands on every screen at once, and the
 * lobby it lands in is this same lobby, so there is nothing to re-join and no
 * request worth inventing. What the others get from pressing it is the answer
 * to the only question they have, which is whether anything is happening.
 *
 * The asking is held here rather than in the room, so going back to the lobby
 * unmounts it and there is nothing to clear.
 */
function NewRound({
  isHost,
  hostName,
  busy,
  onRestart,
}: {
  isHost: boolean;
  hostName: string | null;
  busy: boolean;
  onRestart: () => void;
}) {
  const [asked, setAsked] = useState(false);
  const waiting = !isHost && asked;

  return (
    <div className="w-full space-y-2.5">
      <Button
        size="lg"
        className="h-14 w-full text-lg font-bold"
        disabled={busy || waiting}
        onClick={() => (isHost ? onRestart() : setAsked(true))}
      >
        {busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : null}
        New round?
      </Button>
      {waiting ? (
        <p
          className="text-muted-foreground flex items-center justify-center gap-2 text-sm"
          aria-live="polite"
        >
          <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
          Waiting for {hostName ?? "the host"} to re-create the lobby…
        </p>
      ) : null}
    </div>
  );
}
