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

/**
 * A photograph on a category, and the credit that has to appear under it.
 *
 * `src` is a ready-to-load Commons URL. Credit and licence are always present:
 * a category is the board, shown from the first frame, so there is nothing to
 * time the attribution against — and CC BY-SA requires it wherever the work
 * appears.
 */
export interface CategoryImage {
  src: string;
  credit: string | null;
  licence: string | null;
  licence_url: string | null;
}

export interface Category {
  id: string;
  label: string;
  position: number;
  /** The photograph, for a picture question. Null for a worded category. */
  image: CategoryImage | null;
}

export interface Item {
  id: string;
  /** Always present. Answers are words for every kind of question. */
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
  /**
   * How `quiz_count` splits by rating. Absent keys mean none at that rating, so
   * read it with `?? 0` — the API omits empty buckets rather than sending zeros.
   */
  difficulty_counts: Partial<Record<Difficulty, number>>;
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
  /** Always named: answers are words, readable in the pool either way. */
  item_label: string;
  /** Where it was placed — always a real category, right or wrong. */
  category_id: string;
  was_correct: boolean;
}

/** One category and its answer, revealed once the round is over. */
export interface ResolvedPair {
  category_label: string;
  item_label: string;
  /** The category's photograph, so the review shows what was being asked. */
  image: CategoryImage | null;
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
  /** "image" means every category is a photograph. Answers are words either way. */
  category_kind: "text" | "image";
  categories: Category[];
  /** Still unplaced, and carrying no hint of where they belong. */
  remaining_items: Item[];
  solved_items: SolvedItem[];
}

/**
 * The game the host has set up, before there is a game to play.
 *
 * Lives on the lobby rather than in the host's browser, so the players waiting
 * can see what they are about to play and someone joining late has missed
 * nothing. Only the host may write it — see `updateLobbySettings`.
 */
export interface LobbySettings {
  subject_slugs: string[];
  difficulties: Difficulty[];
  round_count: number;
  turn_seconds: number;
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
  /**
   * Who plays after them. Null when the turn would come straight back to the
   * same player, which is not "next" in any useful sense.
   */
  next_player_id: string | null;
  /**
   * The short settling round after the last question, played only by whoever
   * the rotation short-changed over the game. `round_index` means nothing
   * while this is true — it is not one of the numbered rounds.
   */
  is_catch_up: boolean;
  /** Turns still owed, by player id, during that round. Empty otherwise. */
  catch_up_left: Record<string, number>;
  /** The player on the clock has gone silent but has not timed out yet. */
  current_player_quiet: boolean;
  /**
   * Seconds the player on the clock has left, and how long they got. Both null
   * when nobody is on the clock. Sent as a remaining duration, not a deadline,
   * so a client with a wrong clock still counts down correctly.
   */
  turn_seconds_left: number | null;
  turn_seconds: number | null;
  /**
   * Who has asked for the next round while the answers are up, in seat order.
   * Only players who are still connected — a vote from a tab that has gone
   * away stops counting, so it can never hold a review open on its own.
   */
  ready_ids: string[];
  /** How many of those asks start the countdown: half of those present, rounded up. */
  ready_needed: number;
  /**
   * Seconds until the next round begins, once enough have asked. Null while
   * nothing is counting. A remaining duration rather than a deadline, so a
   * device with a wrong clock still counts down correctly.
   */
  next_round_in: number | null;
  /** Who last lost their turn to the clock. Cleared by the next real move. */
  timed_out: string | null;
  /** Every placement this round, oldest first. Reset when a round starts. */
  history: LastMove[];
  round_view: RoundView | null;
  finished_rounds: FinishedRound[];
  last_move: LastMove | null;
  winner_ids: string[];
  settings: LobbySettings;
  /** Bumped on every mutation, so polling can skip unchanged state. */
  version: number;
}

export interface LobbyIdentity {
  code: string;
  player_id: string;
}
