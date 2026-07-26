"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createLobby, joinLobby } from "@/lib/api";
import { recallNickname, rememberNickname, rememberPlayer } from "@/lib/identity";
import { useStored } from "@/lib/use-stored";

export function JoinForm() {
  const router = useRouter();
  // The field starts from last game's nickname and switches to whatever the
  // player types. Keeping "typed" separate avoids an effect that would
  // overwrite their input on every render.
  const storedNickname = useStored(recallNickname, "");
  const [typed, setTyped] = useState<string | null>(null);
  const nickname = typed ?? storedNickname;

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"create" | "join" | null>(null);

  async function go(action: "create" | "join") {
    const name = nickname.trim();
    if (!name) {
      toast.error("Pick a nickname first.");
      return;
    }

    setBusy(action);
    try {
      const identity =
        action === "create"
          ? await createLobby(name)
          : await joinLobby(code.trim().toUpperCase(), name);

      rememberNickname(name);
      rememberPlayer(identity.code, identity.player_id);
      router.push(`/lobby/${identity.code}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Something failed.");
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your nickname</CardTitle>
          <CardDescription>
            Shown to the other players. Nothing about you is stored in the
            database.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Label htmlFor="nickname" className="sr-only">
            Nickname
          </Label>
          <Input
            id="nickname"
            value={nickname}
            onChange={(event) => setTyped(event.target.value)}
            placeholder="e.g. Anna"
            maxLength={40}
            autoComplete="nickname"
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="text-base">Open a lobby</CardTitle>
            <CardDescription>You become the host.</CardDescription>
          </CardHeader>
          <CardFooter className="mt-auto">
            <Button
              className="w-full"
              onClick={() => go("create")}
              disabled={busy !== null}
            >
              {busy === "create" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : null}
              Create
            </Button>
          </CardFooter>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="text-base">Join a lobby</CardTitle>
            <CardDescription>Enter the four-letter code.</CardDescription>
          </CardHeader>
          <CardContent>
            <Label htmlFor="code" className="sr-only">
              Lobby code
            </Label>
            <Input
              id="code"
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              onKeyDown={(event) => {
                if (event.key === "Enter") go("join");
              }}
              placeholder="ABCD"
              maxLength={8}
              className="font-mono tracking-widest uppercase"
            />
          </CardContent>
          <CardFooter className="mt-auto">
            <Button
              className="w-full"
              variant="outline"
              onClick={() => go("join")}
              disabled={busy !== null || code.trim().length === 0}
            >
              {busy === "join" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : null}
              Join
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
