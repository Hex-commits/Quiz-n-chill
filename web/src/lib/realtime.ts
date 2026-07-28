"use client";

/**
 * Hearing that the lobby changed, instead of asking every second and a half.
 *
 * The API publishes one message per actual change on a channel named after the
 * lobby code. This subscribes to it and calls back; the caller then fetches the
 * view from the API exactly as it always did.
 *
 * The message carries a version number and nothing else, by design on the
 * server side -- the lobby holds the answer key, so a notification that
 * contained state would hand players the solutions. This module never reads the
 * payload for that reason: it is a doorbell, and the API is still the only
 * thing that decides what a player is allowed to see.
 *
 * Everything here is best effort. If Supabase is not configured, or the socket
 * never connects, `subscribe` returns a no-op teardown and the room keeps
 * working on its slow poll. A realtime outage should cost latency, not a game.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
// The publishable key. Safe in the browser: every table has row level security
// on with no policies, so it reads nothing. It is not the service-role key,
// which never leaves the API.
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const realtimeConfigured = Boolean(url && anonKey);

let client: SupabaseClient | null = null;

function getClient(): SupabaseClient | null {
  if (!realtimeConfigured) return null;
  // One socket per tab, shared by every channel, rather than one per lobby.
  client ??= createClient(url!, anonKey!, {
    auth: { persistSession: false },
    realtime: { params: { eventsPerSecond: 5 } },
  });
  return client;
}

/**
 * Call `onChange` whenever the lobby changes. Returns a teardown function.
 *
 * Safe to call when realtime is not configured -- it simply never fires.
 */
export function subscribeToLobby(code: string, onChange: () => void): () => void {
  const supabase = getClient();
  if (!supabase) return () => {};

  const channel = supabase
    .channel(`lobby:${code.toUpperCase()}`)
    .on("broadcast", { event: "lobby-changed" }, () => onChange())
    .subscribe();

  return () => {
    void supabase.removeChannel(channel);
  };
}
