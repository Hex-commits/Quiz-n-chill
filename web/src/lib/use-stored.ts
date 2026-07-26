"use client";

import { useSyncExternalStore } from "react";

/** localStorage does not change under us during a session, so nothing to subscribe to. */
const NO_SUBSCRIBE = () => () => {};

/**
 * Read a value that lives outside React (here: localStorage) without a
 * `useEffect` + `setState` dance.
 *
 * The effect version renders once with the wrong value and once with the right
 * one, which flashes and trips the React Compiler's set-state-in-effect rule.
 * `useSyncExternalStore` takes a separate server snapshot instead, so SSR and
 * hydration agree by construction.
 *
 * `read` must return a value that is `Object.is`-stable across calls or React
 * will re-render forever -- fine for the strings and nulls used here.
 */
export function useStored<T>(read: () => T, serverValue: T): T {
  return useSyncExternalStore(NO_SUBSCRIBE, read, () => serverValue);
}
