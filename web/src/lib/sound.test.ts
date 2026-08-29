/**
 * The house rules from `sound.ts`, held to.
 *
 * Every cue in there is written to the same three constraints: sine and
 * triangle only, nothing bright enough for the master lowpass to be doing the
 * work alone, and a level that survives being heard many times a game. None of
 * that shows up as a bug -- it shows up as a game that is tiring to sit
 * through, an hour after somebody added a cue in a hurry.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { CUES, HURRY, type Note } from "./sound.ts";

/** The master lowpass corner. A cue above this is asking to be filtered. */
const TONE_HZ = 2000;

/* `CUES` is `satisfies`-typed, so each entry keeps its literal shape and only
   some of them mention `type` or `gain`. Widened here to the one shape they all
   satisfy, which is what the rules below are about. */
const everything: [string, Note][] = [
  ...Object.entries(CUES).flatMap(([name, notes]) =>
    (notes as Note[]).map((note): [string, Note] => [name, note]),
  ),
  ...Object.entries(HURRY).flatMap(([name, notes]) =>
    notes.map((note): [string, Note] => [`countdown ${name}`, note]),
  ),
];

test("every note is a sine or a triangle", () => {
  for (const [name, note] of everything) {
    const type = note.type ?? "triangle";
    assert.ok(
      type === "sine" || type === "triangle",
      `${name} uses ${type}: sawtooth and square are what this module removed`,
    );
  }
});

test("nothing is pitched above the master lowpass", () => {
  for (const [name, note] of everything) {
    assert.ok(note.freq <= TONE_HZ, `${name} is at ${note.freq} Hz`);
  }
});

test("every note has a real duration and a sane level", () => {
  for (const [name, note] of everything) {
    assert.ok(note.duration > 0, `${name} has no duration`);
    const gain = note.gain ?? 0.5;
    assert.ok(gain > 0 && gain <= 0.7, `${name} is at gain ${gain}`);
  }
});

test("the poker cues are all there", () => {
  for (const cue of ["chip", "allIn", "fold", "step", "reveal", "potWon"]) {
    assert.ok(cue in CUES, `${cue} is missing`);
  }
});

test("the countdown escalates rather than repeating", () => {
  const pitch = [5, 4, 3, 2, 1].map((second) => HURRY[second][0].freq);
  assert.deepEqual(pitch, [...pitch].sort((a, b) => a - b), "pitch must climb");

  const level = [5, 4, 3, 2, 1].map((second) => HURRY[second][0].gain ?? 0.5);
  assert.deepEqual(level, [...level].sort((a, b) => a - b), "and get louder");
});
