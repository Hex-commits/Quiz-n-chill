"use client";

/**
 * The lobby, streamed.
 *
 * This is the frontend's only connection to Supabase: a WebSocket carrying one
 * message per change, on a channel named after the lobby.
 *
 * It used to be a doorbell — the payload was `{"version": 7}` and every client
 * answered it with an HTTP fetch. That made the socket a *trigger* for a poll
 * rather than a replacement for one, and left the round trip it existed to
 * remove exactly where it was. Now the message carries the state and the room
 * renders it as it lands.
 *
 * What arrives is `LobbyView`, the same redacted object `GET /lobbies/:code`
 * returns — answers still in the pool do not name their category and no
 * explanation appears before its round is over. The API decides that, here as
 * before; this file only unwraps what it sent.
 *
 * It is still *not* a database connection. Nothing here reads a table, and
 * nothing could: the anon key it holds is subject to row level security with no
 * policies, so it returns zero rows from every table in the schema.
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

import type { LobbyView } from "@/lib/types";

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
 * Call `onChange` whenever the lobby changes, with the new state when it came
 * along. Returns a teardown function.
 *
 * `view` is null when the API sent the version alone, which it does for a state
 * too large to put in a frame -- a long game accumulates an answer key per
 * finished round. The caller fetches in that case, exactly as it used to for
 * every message.
 *
 * Safe to call when realtime is not configured -- it simply never fires.
 */
export function subscribeToLobby(
  code: string,
  onChange: (view: LobbyView | null) => void,
): () => void {
  const socket = getClient();
  if (!socket) return () => {};

  const channel: RealtimeChannel = socket.channel(`lobby:${code.toUpperCase()}`);
  channel
    .on("broadcast", { event: "lobby-changed" }, (message) => {
      // Shape-checked rather than trusted: this crosses a socket, and a
      // malformed frame should cost a fetch, not a crashed room.
      const state = (message?.payload as { state?: unknown } | undefined)?.state;
      const view =
        state && typeof state === "object" && "version" in state
          ? (state as LobbyView)
          : null;
      onChange(view);
    })
    .subscribe();

  return () => {
    void socket.removeChannel(channel);
  };
}
