/**
 * The three properties the board relies on: the order moves, it does not move
 * again on the next poll, and it does not move when an answer is solved.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { shuffleBySeed } from "./shuffle.ts";

const id = (entry: string) => entry;

// Enough entries that "unchanged" cannot pass by luck: a board of ten has 3.6
// million orders.
const BOARD = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"];

test("the written order is broken up", () => {
  assert.notDeepEqual(shuffleBySeed(BOARD, "round-1", id), BOARD);
});

test("the same seed gives the same order", () => {
  // This is what holds the board still between polls, and what keeps every
  // player at the table looking at the same board.
  assert.deepEqual(
    shuffleBySeed(BOARD, "round-1", id),
    shuffleBySeed(BOARD, "round-1", id),
  );
});

test("a different seed gives a different order", () => {
  assert.notDeepEqual(
    shuffleBySeed(BOARD, "round-1", id),
    shuffleBySeed(BOARD, "round-2", id),
  );
});

test("the order the entries arrived in does not matter", () => {
  const reversed = [...BOARD].reverse();
  assert.deepEqual(
    shuffleBySeed(reversed, "round-1", id),
    shuffleBySeed(BOARD, "round-1", id),
  );
});

test("solving an answer leaves the rest where they are", () => {
  // The one that would bite hardest in play: answers leave the pool as they are
  // placed, and a shuffle that re-dealt the survivors would move the buttons
  // out from under whoever is on the clock.
  const full = shuffleBySeed(BOARD, "round-1", id);
  const solved = full[3];
  const rest = shuffleBySeed(
    BOARD.filter((entry) => entry !== solved),
    "round-1",
    id,
  );
  assert.deepEqual(rest, full.filter((entry) => entry !== solved));
});

test("nothing is lost or duplicated", () => {
  const shuffled = shuffleBySeed(BOARD, "round-1", id);
  assert.equal(shuffled.length, BOARD.length);
  assert.deepEqual([...shuffled].sort(), [...BOARD].sort());
});

test("the input is left alone", () => {
  const board = [...BOARD];
  shuffleBySeed(board, "round-1", id);
  assert.deepEqual(board, BOARD);
});

test("empty and single-entry lists are fine", () => {
  assert.deepEqual(shuffleBySeed([], "round-1", id), []);
  assert.deepEqual(shuffleBySeed(["a"], "round-1", id), ["a"]);
});

test("entries are placed by id, not by their contents", () => {
  // The board holds objects, and two answers with the same label are still two
  // different answers.
  const entries = [
    { id: "1", label: "same" },
    { id: "2", label: "same" },
  ];
  const shuffled = shuffleBySeed(entries, "round-1", (entry) => entry.id);
  assert.deepEqual(
    [...shuffled].map((entry) => entry.id).sort(),
    ["1", "2"],
  );
});

test("uuids sharing a prefix are spread out", () => {
  // Real ids, hashed against a shared seed, are near-identical strings. A hash
  // that kept them in neighbouring buckets would sort them almost back into the
  // order they came in -- which is the order being hidden.
  const uuids = Array.from(
    { length: 12 },
    (_, i) => `0191f2a4-7c3d-7b8e-9f10-aabbccdd${String(i).padStart(4, "0")}`,
  );
  const shuffled = shuffleBySeed(uuids, "round-1", id);
  const moved = shuffled.filter((entry, i) => entry !== uuids[i]).length;
  assert.ok(moved >= uuids.length - 2, `only ${moved} of ${uuids.length} moved`);
});
