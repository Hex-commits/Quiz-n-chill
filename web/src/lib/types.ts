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
  category_count: number;
  item_count: number;
  created_at: string;
}

export interface QuizDetail {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  created_at: string;
  categories: Category[];
  items: Item[];
}

/** `category_id: null` means the player declared the item a fake. */
export interface Assignment {
  item_id: string;
  category_id: string | null;
}

export interface ItemResult {
  item_id: string;
  label: string;
  assigned_category_id: string | null;
  correct_category_id: string | null;
  is_fake: boolean;
  is_correct: boolean;
}

export interface CheckResult {
  quiz_id: string;
  score: number;
  max_score: number;
  results: ItemResult[];
}

export interface ApiErrorBody {
  error?: { code: string; message: string };
  detail?: string;
}

// --- Lobbies (ephemeral, never stored in the database) ---------------------

export type LobbyStatus = "lobby" | "playing" | "finished";

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
  category_id: string | null;
  solved_by: string;
}

export interface LastMove {
  player_id: string;
  nickname: string;
  item_label: string;
  category_id: string | null;
  was_correct: boolean;
}

export interface RoundView {
  quiz_id: string;
  slug: string;
  title: string;
  description: string | null;
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
  round_view: RoundView | null;
  last_move: LastMove | null;
  winner_ids: string[];
  /** Bumped on every mutation, so polling can skip unchanged state. */
  version: number;
}

export interface LobbyIdentity {
  code: string;
  player_id: string;
}
