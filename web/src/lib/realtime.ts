"use client";

/**
 * Hearing that the lobby changed, instead of asking every few seconds.
 *
 * This is the frontend's only connection to Supabase, and it is worth being
 * exact about what it is: a WebSocket that carries one message per change,
 * whose entire payload is `{"version": 7}`. It subscribes to a channel named
 * after the lobby and calls back. That is all it can do.
 *
 * It is *not* a database connection. Nothing here reads a table, and nothing
 * could: the anon key it holds is subject to row level security that has no
 * policies, so it returns zero rows from every table in the schema. All game
 * data still comes from the API, which remains the only thing that decides
 * what a given player is allowed to see. The socket is a doorbell.
 *
 * Deliberately `@supabase/realtime-js` rather than `@supabase/supabase-js`.
 * The full SDK bundles clients for Postgres, auth, storage and edge functions
 * -- roughly 4.5 MB of dependency for features this app never calls, some of
 * which `createClient` instantiates whether you use them or not. This is the
 * one piece that does the job, and depending on only it keeps the frontend
 * honest about what it talks to.
 *
 * Everything here is best effort. If Supabase is not configured, or the socket
 * never connects, `subscribe` returns a no-op teardown and the room keeps
 * working on its slower poll. A realtime outage should cost latency, not a
 * game.
 */

import { RealtimeClient, type RealtimeChannel } from "@supabase/realtime-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
// The publishable key. Safe in the browser because of the RLS position above,
// and not the service-role key, which never leaves the API.
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const realtimeConfigured = Boolean(url && anonKey);

let client: RealtimeClient | null = null;

function getClient(): RealtimeClient | null {
  if (!realtimeConfigured) return null;
  // One socket per tab, shared by every channel, rather than one per lobby.
  client ??= new RealtimeClient(`${url!.replace(/\/+$/, "")}/realtime/v1`, {
    params: { apikey: anonKey! },
  });
  return client;
}

/**
 * Call `onChange` whenever the lobby changes. Returns a teardown function.
 *
 * Safe to call when realtime is not configured -- it simply never fires.
 */
export function subscribeToLobby(code: string, onChange: () => void): () => void {
  const socket = getClient();
  if (!socket) return () => {};

  const channel: RealtimeChannel = socket.channel(`lobby:${code.toUpperCase()}`);
  channel.on("broadcast", { event: "lobby-changed" }, () => onChange()).subscribe();

  return () => {
    void socket.removeChannel(channel);
  };
}
