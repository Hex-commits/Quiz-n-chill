/**
 * Mirrors `api/app/schemas.py`. Keep the two in sync by hand for now.
 *
 * When the shapes start moving often, generate this instead:
 *   npx openapi-typescript http://localhost:8001/openapi.json -o src/lib/api-types.ts
 *
 * Note what is absent: `Item` has no `categoryId`. An item's category IS the
 * answer, so the backend never sends it before submission and the frontend has
 * no way to leak it. Solutions arrive only in `CheckResult`.
 */

export type Difficulty = "easy" | "medium" | "hard";

/**
 * Where a question was written from. Present only on payloads a player sees
 * *after* answering — during play, a link to the source is a link to the
 * answers, so the API does not send it.
 */
export interface Source {
  url: string;
  title: string | null;
}

export interface Category {
  id: string;
  label: string;
  position: number;
}

export interface Item {
  id: string;
  label: string;
}

/**
 * A quiz-pool area (Geografie, Musik). Distinct from `Category`, which is a
 * bucket *inside* one question.
 */
export interface Subject {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  position: number;
  quiz_count: number;
}

export interface QuizSummary {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  subject_slug: string | null;
  subject_name: string | null;
  difficulty: Difficulty;
  category_count: number;
  item_count: number;
  created_at: string;
}

export interface QuizDetail {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  difficulty: Difficulty;
  created_at: string;
  categories: Category[];
  items: Item[];
}

/** `category_id: null` means the player has not placed this answer yet. */
export interface Assignment {
  item_id: string;
  category_id: string | null;
}

export interface ItemResult {
  item_id: string;
  label: string;
  assigned_category_id: string | null;
  correct_category_id: string;
  is_correct: boolean;
  /**
   * One line on why this answer belongs where it does. Revealed with the
   * grading and never before — it gives the answer away. Null for questions
   * written before the ingest pipeline produced explanations.
   */
  explanation: string | null;
}

export interface CheckResult {
  quiz_id: string;
  score: number;
  max_score: number;
  difficulty: Difficulty;
  /** Revealed here and nowhere earlier. */
  source: Source | null;
  results: ItemResult[];
}

export interface ApiErrorBody {
  error?: { code: string; message: string };
  detail?: string;
}

// --- Lobbies (ephemeral, never stored in the database) ---------------------

export type LobbyStatus = "lobby" | "playing" | "reviewing" | "finished";

export interface PlayerPublic {
  id: string;
  nickname: string;
  score: number;
  /** False once the player has answered wrongly; resets every round. */
  is_active: boolean;
  /** False when their client stopped checking in — a closed tab. Persists across rounds. */
  is_connected: boolean;
  is_host: boolean;
}

export interface SolvedItem {
  item_id: string;
  label: string;
  category_id: string;
  solved_by: string;
}

export interface LastMove {
  player_id: string;
  nickname: string;
  item_label: string;
  /** Where it was placed — always a real category, right or wrong. */
  category_id: string;
  was_correct: boolean;
}

/** One category and its answer, revealed once the round is over. */
export interface ResolvedPair {
  category_label: string;
  item_label: string;
  /** Why it belongs there. Null for questions seeded before the explain step. */
  explanation: string | null;
  /** Who placed it, or null if the round ended with this one still open. */
  solved_by: string | null;
}

/** A round that is over, so its source and answer key can be shown. */
export interface FinishedRound {
  quiz_id: string;
  slug: string;
  title: string;
  difficulty: Difficulty;
  source: Source | null;
  solution: ResolvedPair[];
}

export interface RoundView {
  quiz_id: string;
  slug: string;
  title: string;
  description: string | null;
  difficulty: Difficulty;
  categories: Category[];
  /** Still unplaced, and carrying no hint of where they belong. */
  remaining_items: Item[];
  solved_items: SolvedItem[];
}

export interface LobbyView {
  code: string;
  status: LobbyStatus;
  players: PlayerPublic[];
  quiz_slugs: string[];
  subject_names: string[];
  round_index: number;
  round_count: number;
  current_player_id: string | null;
  /** The player on the clock has gone silent but has not timed out yet. */
  current_player_quiet: boolean;
  /** Seconds until the next round starts. Only set while reviewing. */
  review_seconds_left: number | null;
  round_view: RoundView | null;
  finished_rounds: FinishedRound[];
  last_move: LastMove | null;
  winner_ids: string[];
  /** Bumped on every mutation, so polling can skip unchanged state. */
  version: number;
}

export interface LobbyIdentity {
  code: string;
  player_id: string;
}
