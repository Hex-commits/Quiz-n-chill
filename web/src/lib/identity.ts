/**
 * Who this browser is, per lobby.
 *
 * The player id doubles as the secret for submitting turns, so it lives in
 * localStorage keyed by lobby code. That survives a refresh mid-game, which
 * matters when someone's phone locks. It is not sensitive beyond the lifetime
 * of one game -- the server forgets the whole lobby on restart.
 */

const KEY_PREFIX = "quiz-quiz:player:";
const NICKNAME_KEY = "quiz-quiz:nickname";

export function rememberPlayer(code: string, playerId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(`${KEY_PREFIX}${code.toUpperCase()}`, playerId);
}

export function recallPlayer(code: string): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(`${KEY_PREFIX}${code.toUpperCase()}`);
}

export function forgetPlayer(code: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(`${KEY_PREFIX}${code.toUpperCase()}`);
}

/** Remembered only so the nickname field can prefill next time. */
export function rememberNickname(nickname: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(NICKNAME_KEY, nickname);
}

export function recallNickname(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(NICKNAME_KEY) ?? "";
}
