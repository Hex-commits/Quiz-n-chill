"use client";

/**
 * A countdown that runs in the browser, from a deadline the server set.
 *
 * The server sends a *remaining duration* — "14 seconds left" — as of the
 * moment it answered. Rendering that number directly means it only moves when a
 * request happens, so the display freezes between polls and the game feels
 * broken even when it is working. Turning it into a wall-clock deadline once,
 * then ticking locally, costs no requests at all.
 *
 * A deadline rather than a decrementing counter because a backgrounded tab
 * stops firing timers: on return `Date.now()` has moved on and the remaining
 * time is still right, where a counter would have lost however long the tab
 * slept.
 *
 * `onExpire` fires once when the deadline passes. That matters because the
 * server has no timers of its own — it acts on a deadline only when a request
 * arrives and finds it passed, and on serverless there is no process between
 * requests that could do otherwise. Something has to knock.
 */

import { useEffect, useRef, useState } from "react";

/** How often the displayed number is recomputed. Twice a second so a whole
 *  second is never visibly skipped, without re-rendering on every frame. */
const TICK_MS = 500;

/** Grace added before `onExpire` fires, so the server has certainly passed its
 *  own deadline by the time it is asked to act on it. */
const GRACE_MS = 200;

export function useCountdown(
  deadline: number | null,
  onExpire?: () => void,
): number | null {
  const [now, setNow] = useState(() => Date.now());

  // Held in a ref so a caller passing an inline arrow does not re-arm the
  // timer on every render.
  const expire = useRef(onExpire);
  useEffect(() => {
    expire.current = onExpire;
  }, [onExpire]);

  useEffect(() => {
    if (deadline === null) return;
    const tick = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(tick);
  }, [deadline]);

  useEffect(() => {
    if (deadline === null) return;
    const timer = setTimeout(
      () => expire.current?.(),
      Math.max(0, deadline - Date.now()) + GRACE_MS,
    );
    return () => clearTimeout(timer);
  }, [deadline]);

  if (deadline === null) return null;
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

/** Server seconds -> a wall-clock deadline. Call where the view arrives. */
export function deadlineFrom(secondsLeft: number | null): number | null {
  return secondsLeft === null ? null : Date.now() + secondsLeft * 1000;
}

/**
 * How far the server's answer may differ from the running clock before it is
 * believed. Comfortably above the noise, comfortably below a real change.
 *
 * The noise is unavoidable: the server rounds up to whole seconds and its reply
 * spent time in flight, so two consecutive answers about the same deadline
 * routinely disagree by up to a second.
 */
const RESYNC_MS = 1_500;

/**
 * Decide whether an arriving deadline should replace the one already running.
 *
 * Adopting every answer looks worse than trusting the local clock: a poll every
 * few seconds re-pins the deadline slightly later each time — rounding up, plus
 * however long the reply took to arrive — so the displayed number stalls or
 * repeats rather than counting down. The browser's own clock is the better
 * instrument *between* syncs; the server is only needed to say when something
 * has actually changed.
 *
 * So it is adopted when it means something: the clock starting, the clock
 * stopping, a new turn or round beginning (the deadline jumps by seconds), or
 * genuine drift worth correcting. Small disagreements are ignored.
 */
export function reconcileDeadline(
  current: number | null,
  next: number | null,
): number | null {
  // Starting or stopping is always news.
  if (next === null || current === null) return next;
  return Math.abs(next - current) > RESYNC_MS ? next : current;
}
