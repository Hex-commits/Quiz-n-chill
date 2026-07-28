"use client";

import { useSyncExternalStore } from "react";
import { Volume2, VolumeX } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  isMuted,
  isMutedOnServer,
  play,
  setMuted,
  subscribeMuted,
  unlock,
} from "@/lib/sound";

/**
 * Turn the game's sounds off, and keep them off.
 *
 * Subscribed rather than mirrored into state: the answer lives in
 * localStorage, which the server render cannot see. An effect that corrected it
 * after mount would render once wrong and once right, and `useSyncExternalStore`
 * takes a separate server snapshot so SSR and hydration agree by construction.
 * Same reasoning as `useStored`, which does this for the player id.
 */
export function SoundToggle() {
  const muted = useSyncExternalStore(subscribeMuted, isMuted, isMutedOnServer);

  function toggle() {
    const next = !muted;
    setMuted(next);
    if (!next) {
      // This click is a user gesture, which is the only moment the browser will
      // let an AudioContext start -- and a confirmation is the natural thing to
      // hear when you switch sound back on.
      unlock();
      play("correct");
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-pressed={muted}
      aria-label={muted ? "Turn sound on" : "Turn sound off"}
      title={muted ? "Sound off" : "Sound on"}
    >
      {muted ? (
        <VolumeX className="size-4" aria-hidden />
      ) : (
        <Volume2 className="size-4" aria-hidden />
      )}
    </Button>
  );
}
