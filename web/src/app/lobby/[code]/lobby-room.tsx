"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  Crown,
  Loader2,
  LogOut,
  TriangleAlert,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { ApiErrorNotice } from "@/components/api-error-notice";
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
  startGame,
  submitTurn,
} from "@/lib/api";
import { forgetPlayer, recallPlayer } from "@/lib/identity";
import type { LobbyView, Subject } from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { cn } from "@/lib/utils";

import { RejoinForm } from "./rejoin-form";

const POLL_MS = 1500;

const ROUND_CHOICES = [3, 5, 7, 10];

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

  // Polling and turn submission race: a poll started before a turn can land
  // after it and show pre-turn state. Applying only newer versions fixes it.
  const versionRef = useRef(-1);

  const apply = useCallback((view: LobbyView) => {
    if (view.version < versionRef.current) return;
    versionRef.current = view.version;
    setLobby(view);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        // Passing the player id makes this poll double as a heartbeat.
        const view = await getLobby(code, playerId);
        if (!cancelled) {
          apply(view);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Unknown error");
        }
      }
    }

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [code, playerId, apply]);

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

  function play(categoryId: string | null) {
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
            </CardContent>
            <CardFooter>
              <Button
                onClick={() =>
                  playerId &&
                  act(() =>
                    startGame(code, playerId, chosenSubjects, roundCount),
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
              <Link href="/quizzes">Browse topics</Link>
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  // --- Playing -------------------------------------------------------------

  const round = lobby.round_view;
  if (!round) return null;

  const currentPlayer = lobby.players.find(
    (player) => player.id === lobby.current_player_id,
  );
  const total = round.remaining_items.length + round.solved_items.length;
  const solvedIn = (categoryId: string | null) =>
    round.solved_items.filter((item) => item.category_id === categoryId);

  return (
    <div className="space-y-6">
      {header}

      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-2xl font-bold tracking-tight">{round.title}</h1>
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isMyTurn
              ? selectedItemId
                ? "Now pick a category"
                : "Your turn — pick an answer"
              : `Waiting for ${currentPlayer?.nickname ?? "the next player"}…`}
          </CardTitle>
          <CardDescription>
            {me && !me.is_active
              ? "You are out for this round. You are back in at the next topic."
              : "One placement per turn. Get it wrong and you sit out the rest of the round."}
          </CardDescription>
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

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {round.categories.map((category) => (
          <CategoryCard
            key={category.id}
            title={category.label}
            solved={solvedIn(category.id)}
            armed={isMyTurn && selectedItemId !== null && !busy}
            onPlace={() => play(category.id)}
          />
        ))}
        <CategoryCard
          title="No category"
          description="For answers that fit nowhere"
          icon={<TriangleAlert className="size-4" aria-hidden />}
          solved={solvedIn(null)}
          armed={isMyTurn && selectedItemId !== null && !busy}
          onPlace={() => play(null)}
        />
      </div>
    </div>
  );
}

function CategoryCard({
  title,
  description,
  icon,
  solved,
  armed,
  onPlace,
}: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  solved: { item_id: string; label: string }[];
  armed: boolean;
  onPlace: () => void;
}) {
  return (
    <Card
      className={cn("transition-colors", armed && "border-primary cursor-pointer")}
      onClick={armed ? onPlace : undefined}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex min-h-14 flex-wrap gap-2">
        {solved.length === 0 ? (
          <p className="text-muted-foreground text-sm">Empty</p>
        ) : (
          solved.map((item) => (
            <Badge key={item.item_id} variant="secondary">
              {item.label}
            </Badge>
          ))
        )}
      </CardContent>
    </Card>
  );
}
