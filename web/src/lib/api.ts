/**
 * The only module that knows the backend exists.
 *
 * Components import typed functions from here and never call `fetch` directly,
 * so when the API moves (different host, auth headers, a proxy route) exactly
 * one file changes.
 */

import type {
  Assignment,
  CheckResult,
  LobbyIdentity,
  LobbyView,
  QuizDetail,
  QuizSummary,
  Subject,
} from "@/lib/types";

/**
 * Server components run inside the container and reach the API over the compose
 * network; the browser has to go through the published port on the host. Same
 * API, two different addresses -- picking the wrong one is the classic
 * "works on the server, ECONNREFUSED in the browser" bug.
 */
function baseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_URL ?? DEFAULT_API_URL;
  }
  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;
}

/**
 * Matches `API_PORT` in .env. Defaulting to the dockerized API means running
 * `npm run dev:web` on the host needs no environment setup at all.
 */
const DEFAULT_API_URL = "http://localhost:8001";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    options?: { cause?: unknown },
  ) {
    super(message, options);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
      // Quiz content changes rarely but must not be stale after an edit, so
      // opt out of Next's fetch cache and let page-level revalidation decide.
      cache: "no-store",
    });
  } catch (cause) {
    // Keep the original cause attached -- "fetch failed" alone does not
    // distinguish a refused connection from a DNS miss.
    throw new ApiError(
      `Cannot reach the API at ${baseUrl()}. Is the backend running?`,
      503,
      "api_unreachable",
      { cause },
    );
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message =
      body?.error?.message ??
      (typeof body?.detail === "string" ? body.detail : null) ??
      `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, body?.error?.code);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

// --- Quizzes ---------------------------------------------------------------

export function listSubjects(): Promise<Subject[]> {
  return request<Subject[]>("/subjects");
}

export function listQuizzes(subjectSlugs?: string[]): Promise<QuizSummary[]> {
  const query = subjectSlugs?.length
    ? `?${subjectSlugs.map((s) => `subject=${encodeURIComponent(s)}`).join("&")}`
    : "";
  return request<QuizSummary[]>(`/quizzes${query}`);
}

export function getQuiz(slugOrId: string): Promise<QuizDetail> {
  return request<QuizDetail>(`/quizzes/${encodeURIComponent(slugOrId)}`);
}

// --- Checking --------------------------------------------------------------

/**
 * Grade an assignment. Stateless on the server: nothing about this attempt is
 * stored, so the result is the only record of it.
 */
export function checkAssignment(
  slugOrId: string,
  assignments: Assignment[],
): Promise<CheckResult> {
  return request<CheckResult>(
    `/quizzes/${encodeURIComponent(slugOrId)}/check`,
    {
      method: "POST",
      body: JSON.stringify({ assignments }),
    },
  );
}

// --- Lobbies ---------------------------------------------------------------
//
// Lobby state lives in the API process, not the database. It is gone when the
// backend restarts, and it needs a single long-lived process -- see the README
// note about Vercel's serverless runtime.

export function createLobby(nickname: string): Promise<LobbyIdentity> {
  return request<LobbyIdentity>("/lobbies", {
    method: "POST",
    body: JSON.stringify({ nickname }),
  });
}

export function joinLobby(
  code: string,
  nickname: string,
): Promise<LobbyIdentity> {
  return request<LobbyIdentity>(`/lobbies/${encodeURIComponent(code)}/join`, {
    method: "POST",
    body: JSON.stringify({ nickname }),
  });
}

/**
 * Poll lobby state. Passing `playerId` also checks that player in: the poll is
 * the heartbeat, so a tab that stops polling is treated as gone.
 */
export function getLobby(
  code: string,
  playerId?: string | null,
): Promise<LobbyView> {
  const query = playerId
    ? `?player_id=${encodeURIComponent(playerId)}`
    : "";
  return request<LobbyView>(`/lobbies/${encodeURIComponent(code)}${query}`);
}

/**
 * Tell the server this tab is closing, so the turn moves on without waiting
 * out the presence timeout.
 *
 * `keepalive` lets the request outlive the page. Browsers do not guarantee it
 * is delivered, which is why the server also times players out; treat this
 * purely as a latency improvement. Failures are swallowed deliberately -- the
 * page is going away and there is nobody left to tell.
 */
export function markAway(code: string, playerId: string): void {
  const url = `${baseUrl()}/lobbies/${encodeURIComponent(code)}/away`;
  try {
    void fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Ignore: unload is not a place to surface errors.
  }
}

/**
 * Start a game. The host chooses subjects and a length; the server picks which
 * questions come up, spread evenly across those subjects.
 */
export function startGame(
  code: string,
  playerId: string,
  subjectSlugs: string[],
  roundCount: number,
): Promise<LobbyView> {
  return request<LobbyView>(`/lobbies/${encodeURIComponent(code)}/start`, {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId,
      subject_slugs: subjectSlugs,
      round_count: roundCount,
    }),
  });
}

export function submitTurn(
  code: string,
  playerId: string,
  itemId: string,
  categoryId: string,
): Promise<LobbyView> {
  return request<LobbyView>(`/lobbies/${encodeURIComponent(code)}/turns`, {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId,
      item_id: itemId,
      category_id: categoryId,
    }),
  });
}

/** Host cuts the between-rounds review short. It ends on its own timer anyway. */
export function skipReview(code: string, playerId: string): Promise<LobbyView> {
  return request<LobbyView>(`/lobbies/${encodeURIComponent(code)}/next-round`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId }),
  });
}

/** Drop out. Resolves with nothing -- the server answers 204. */
export function leaveLobby(code: string, playerId: string): Promise<void> {
  return request<void>(`/lobbies/${encodeURIComponent(code)}/leave`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId }),
  });
}

export function restartLobby(
  code: string,
  playerId: string,
): Promise<LobbyView> {
  return request<LobbyView>(`/lobbies/${encodeURIComponent(code)}/restart`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId }),
  });
}
