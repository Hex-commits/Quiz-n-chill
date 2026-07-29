/**
 * Which questions this browser has already seen.
 *
 * **Why the client and not the server.** "What have we played" is a property of
 * a group of friends on a sofa, not of an account — and this game has no
 * accounts. Keeping it server-side would mean inventing an identity to hang it
 * on, and the only candidate is a nickname, which is not a credential: two
 * different tables with an "Anna" would poison each other's history. The
 * browser that hosts the games is the closest thing to the right owner, so it
 * holds the list and sends it with the request that needs it.
 *
 * The cost, stated plainly: it is per-browser. A different device, a cleared
 * cache, or a different host in the group starts fresh. For a party game that
 * is a fair trade for storing nothing about anybody.
 *
 * The list is a *preference*. The server sorts these to the back of each
 * subject's pool rather than removing them, so a group that has worked through
 * the pool still gets a full-length game — see `draw_balanced`.
 */

const KEY = "quiz-quiz:played";

// Enough for a very long history and still a small payload; the API refuses
// more than 500. Oldest go first, which is also the order you would want them
// forgotten in.
const MAX_REMEMBERED = 400;

function read(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    // Shape-checked rather than trusted: this is user-writable storage that may
    // also hold a value written by an older version of the app, and a bad read
    // must cost the exclusion rather than the page.
    return Array.isArray(parsed)
      ? parsed.filter((slug): slug is string => typeof slug === "string")
      : [];
  } catch {
    return [];
  }
}

/**
 * Cached so the value is `Object.is`-stable between renders — `useStored` calls
 * its reader on every render and would loop forever on a fresh array each time.
 * Invalidated by the two functions that write.
 */
let cache: string[] | null = null;

export function playedSlugs(): string[] {
  cache ??= read();
  return cache;
}

/** The empty array, hoisted for the same stability reason. */
export const NO_PLAYED: string[] = [];

export function rememberPlayed(slugs: string[]): void {
  if (typeof window === "undefined" || slugs.length === 0) return;
  // Set semantics, insertion-ordered: re-playing something moves it to the most
  // recent end rather than duplicating it.
  const merged = [...new Set([...playedSlugs(), ...slugs])];
  cache = merged.slice(-MAX_REMEMBERED);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    // Quota or a private-mode refusal. The game does not depend on this.
  }
}

export function forgetPlayed(): void {
  cache = [];
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // As above.
  }
}
