/**
 * When an arriving deadline should replace the running one.
 *
 * The failure this prevents is subtle and very visible: adopting the server's
 * answer on every poll makes the countdown stall or repeat a number, because
 * each answer is rounded up to a whole second and spent time in flight. The
 * clock looked "deliberately re-syncing" rather than counting down.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { reconcileDeadline } from "./use-countdown.ts";

const NOW = 1_800_000_000_000;

test("a clock starting is adopted", () => {
  assert.equal(reconcileDeadline(null, NOW + 30_000), NOW + 30_000);
});

test("a clock stopping is adopted", () => {
  assert.equal(reconcileDeadline(NOW + 30_000, null), null);
});

test("rounding noise is ignored", () => {
  // The server rounds up, so its answer routinely lands within a second of the
  // running deadline. Adopting that is what made the display stutter.
  const running = NOW + 12_000;
  assert.equal(reconcileDeadline(running, NOW + 12_900), running);
  assert.equal(reconcileDeadline(running, NOW + 11_200), running);
});

test("a reply that arrived slightly late is ignored", () => {
  const running = NOW + 8_000;
  // Server said 8s, but the answer took 400ms to arrive, so it reads as 7.6s.
  assert.equal(reconcileDeadline(running, NOW + 7_600), running);
});

test("a new turn is adopted", () => {
  // The previous player had 3s left; the next gets a full 30.
  assert.equal(reconcileDeadline(NOW + 3_000, NOW + 30_000), NOW + 30_000);
});

test("real drift is corrected", () => {
  // A tab that slept, or a clock that wandered. Worth believing the server.
  assert.equal(reconcileDeadline(NOW + 25_000, NOW + 4_000), NOW + 4_000);
});

test("the boundary is exclusive, so exactly the threshold is still noise", () => {
  const running = NOW + 10_000;
  assert.equal(reconcileDeadline(running, NOW + 11_500), running);
  assert.notEqual(reconcileDeadline(running, NOW + 11_501), running);
});
