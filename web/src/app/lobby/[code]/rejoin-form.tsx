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
import { joinLobby } from "@/lib/api";
import { recallNickname, rememberNickname, rememberPlayer } from "@/lib/identity";
import { useStored } from "@/lib/use-stored";

/**
 * Shown when this browser has no identity for the lobby -- a new device, or
 * one whose storage was cleared.
 *
 * The same `join` call covers both cases: the server hands back the existing
 * seat if that nickname belongs to a disconnected player, and a fresh one
 * otherwise. So this form is "join" and "come back" at once.
 */
export function RejoinForm({ code }: { code: string }) {
  const router = useRouter();
  const storedNickname = useStored(recallNickname, "");
  const [typed, setTyped] = useState<string | null>(null);
  const nickname = typed ?? storedNickname;
  const [busy, setBusy] = useState(false);

  async function submit() {
    const name = nickname.trim();
    if (!name) {
      toast.error("Enter the nickname you were playing under.");
      return;
    }

    setBusy(true);
    try {
      const identity = await joinLobby(code, name);
      rememberNickname(name);
      rememberPlayer(identity.code, identity.player_id);
      // Reload so the room picks the identity up from storage.
      router.refresh();
      window.location.reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not join.");
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Join lobby {code}</CardTitle>
        <CardDescription>
          If you were already playing here, enter the same nickname to pick up
          your score and your place in the turn order.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Label htmlFor="rejoin-nickname">Nickname</Label>
        <Input
          id="rejoin-nickname"
          value={nickname}
          onChange={(event) => setTyped(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") submit();
          }}
          placeholder="e.g. Anna"
          maxLength={40}
          autoComplete="nickname"
        />
      </CardContent>
      <CardFooter>
        <Button onClick={submit} disabled={busy}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          Continue
        </Button>
      </CardFooter>
    </Card>
  );
}
