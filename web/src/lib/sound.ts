"use client";

/**
 * The game's sounds: chords rather than beeps.
 *
 * The first version was a set of electronic cues — a sawtooth glide for a wrong
 * answer, a square wave at 1.2 kHz for the clock. Both are the shapes with the
 * most high harmonics, which is exactly what makes a sound fatiguing, and the
 * clock ticks five times a turn for the length of a game. Written for a demo,
 * not for anyone who has to sit through them.
 *
 * So these are built the way a small ensemble would be:
 *
 * **Triads, not single tones.** Three notes an interval apart beat gently
 * against each other and read as warm; one tone alone reads as a device.
 *
 * **Sine and triangle only.** No sawtooth, no square. Almost no energy above
 * the fundamental, so nothing is shrill however often it plays.
 *
 * **Consonance carries the meaning.** Right is a major triad, wrong is the same
 * shape in the minor and lower down — the language a listener already knows,
 * so it never needs to be harsh to be understood. Nothing here is dissonant;
 * being wrong is disappointing enough without being stabbed at.
 *
 * **A lowpass over everything.** One filter on the master bus at 2 kHz takes
 * the edge off the attack of every note at once. It is the difference between
 * an instrument and a buzzer.
 *
 * **Slow attacks and long tails.** 30 ms in and a exponential decay, so notes
 * bloom and fade instead of clicking on and cutting off.
 *
 * Two browser rules shape the rest: an `AudioContext` made before a user
 * gesture starts suspended, so it is built lazily and `unlock()` is called from
 * a real click. And there is no `prefers-reduced-sound`, so the mute toggle is
 * the whole control — and it is remembered, because someone who turns this off
 * has said so once already.
 */

const STORAGE_KEY = "quiz.sound.muted";

/** Master level, deliberately low. Everything below is relative to it. */
const VOLUME = 0.13;

/**
 * The master lowpass. Around two octaves above the highest note used here, so
 * it never dulls the pitch — it only removes the click of the attack and the
 * brightness that makes repeated sounds tiring.
 */
const TONE_HZ = 2000;

/** Equal temperament, A4 = 440. Named so the chords below can be read. */
const N = {
  C3: 130.81,
  G3: 196.0,
  A3: 220.0,
  C4: 261.63,
  D4: 293.66,
  E4: 329.63,
  F4: 349.23,
  G4: 392.0,
  A4: 440.0,
  B4: 493.88,
  C5: 523.25,
  D5: 587.33,
  E5: 659.25,
  F5: 698.46,
  Gb5: 739.99,
  G5: 783.99,
  Ab5: 830.61,
  A5: 880.0,
  Bb5: 932.33,
  C6: 1046.5,
} as const;

export type Note = {
  freq: number;
  /** Seconds. Long tails are most of why these sound like instruments. */
  duration: number;
  /** Seconds. Spreading a chord slightly is what makes it bloom. */
  delay?: number;
  type?: OscillatorType;
  gain?: number;
};

/**
 * The whole palette. Exported so `sound.test.ts` can hold it to the rules in
 * this file's header -- a cue at 3 kHz or on a sawtooth would be exactly the
 * sound this module was rewritten to get rid of, and nothing else would catch
 * it until somebody played a game with the volume up.
 */
export const CUES = {
  /**
   * F major, spread. A plain major triad, arriving rather than announcing —
   * this plays on every correct answer, so it has to bear repetition.
   */
  correct: [
    { freq: N.F4, duration: 0.7, gain: 0.7 },
    { freq: N.A4, duration: 0.66, delay: 0.035, gain: 0.6 },
    { freq: N.C5, duration: 0.62, delay: 0.07, gain: 0.5 },
  ],

  /**
   * D minor, lower and shorter. The minor third is doing all the work: no
   * dissonance, no falling glide, nothing that reads as a buzzer. It says the
   * answer was wrong the way a cadence says a phrase has ended.
   */
  wrong: [
    { freq: N.D4, duration: 0.5, gain: 0.55 },
    { freq: N.F4, duration: 0.46, delay: 0.03, gain: 0.45 },
    { freq: N.A3, duration: 0.54, delay: 0.015, gain: 0.4 },
  ],

  /**
   * A rising fourth with the fifth underneath — a horn call, the traditional
   * "attention" figure. Distinct from `correct` at a glance because it moves
   * upward in two steps rather than blooming in place.
   */
  yourTurn: [
    { freq: N.G4, duration: 0.28, gain: 0.5 },
    { freq: N.C5, duration: 0.62, delay: 0.16, gain: 0.55 },
    { freq: N.G5, duration: 0.5, delay: 0.2, gain: 0.22 },
  ],

  /**
   * A perfect cadence, V–I: G major resolving to C major. The most settled
   * ending two chords can make, which is what the end of a round wants to say.
   */
  roundEnd: [
    { freq: N.G4, duration: 0.34, gain: 0.5 },
    { freq: N.B4, duration: 0.32, delay: 0.02, gain: 0.42 },
    { freq: N.D5, duration: 0.3, delay: 0.04, gain: 0.36 },
    { freq: N.C4, duration: 1.1, delay: 0.32, gain: 0.6 },
    { freq: N.E4, duration: 1.05, delay: 0.35, gain: 0.5 },
    { freq: N.G4, duration: 1.0, delay: 0.38, gain: 0.42 },
    { freq: N.C5, duration: 0.95, delay: 0.41, gain: 0.3 },
  ],

  /**
   * The same cadence with the subdominant in front of it — IV–V–I, the full
   * close. Longer and an octave wider, because it happens once a game.
   */
  gameEnd: [
    { freq: N.F4, duration: 0.34, gain: 0.45 },
    { freq: N.A4, duration: 0.32, delay: 0.02, gain: 0.38 },
    { freq: N.C5, duration: 0.3, delay: 0.04, gain: 0.32 },
    { freq: N.G4, duration: 0.34, delay: 0.3, gain: 0.45 },
    { freq: N.B4, duration: 0.32, delay: 0.32, gain: 0.38 },
    { freq: N.D5, duration: 0.3, delay: 0.34, gain: 0.32 },
    { freq: N.C4, duration: 1.6, delay: 0.62, gain: 0.6 },
    { freq: N.E4, duration: 1.55, delay: 0.65, gain: 0.48 },
    { freq: N.G4, duration: 1.5, delay: 0.68, gain: 0.4 },
    { freq: N.C6, duration: 1.4, delay: 0.72, gain: 0.16 },
  ],
  /**
   * Chips pushed in. Two short sines a fifth apart, and quiet.
   *
   * The one cue in here that fires many times a hand -- every call, every
   * raise, every stake put behind another player -- so it is built to be heard
   * and then forgotten. Sine at 70 ms has no attack to speak of and no
   * harmonics to tire of; the fifth on top is what stops it reading as a beep.
   */
  chip: [
    { freq: N.C5, duration: 0.07, type: "sine", gain: 0.22 },
    { freq: N.G5, duration: 0.06, delay: 0.045, type: "sine", gain: 0.13 },
  ],

  /**
   * Everything in. Open fifths stacking upward from the bottom of the range.
   *
   * No third in it, deliberately: fifths alone are neither major nor minor, so
   * a shove sounds like a shove rather than like good news or bad. The table
   * finds out which it was a minute later.
   */
  allIn: [
    { freq: N.C3, duration: 0.55, type: "sine", gain: 0.5 },
    { freq: N.G3, duration: 0.5, delay: 0.07, gain: 0.4 },
    { freq: N.C4, duration: 0.45, delay: 0.14, gain: 0.3 },
    { freq: N.G4, duration: 0.4, delay: 0.21, gain: 0.18 },
  ],

  /**
   * A fold: a falling minor third, low and brief. The smallest gesture in the
   * set. Somebody stepping out of a hand is not an event, and a cue that
   * announced it would be wrong about the game.
   */
  fold: [
    { freq: N.F4, duration: 0.16, type: "sine", gain: 0.28 },
    { freq: N.D4, duration: 0.3, delay: 0.1, type: "sine", gain: 0.24 },
  ],

  /**
   * One step of the reveal: the subject, then the topic. A rising fourth,
   * quiet and short -- the same interval `yourTurn` opens with, an octave down
   * and without the arrival. Something was said; it is not your turn yet.
   */
  step: [
    { freq: N.C4, duration: 0.16, type: "sine", gain: 0.3 },
    { freq: N.F4, duration: 0.26, delay: 0.08, type: "sine", gain: 0.26 },
  ],

  /**
   * The round where the question itself turns over. C major spread as wide as
   * the range allows -- root, fifth, then the third an octave up. An opening
   * rather than a resolution: it is the moment the hand has been building to,
   * and there is still betting to come.
   */
  reveal: [
    { freq: N.C4, duration: 0.55, gain: 0.42 },
    { freq: N.G4, duration: 0.52, delay: 0.09, gain: 0.34 },
    { freq: N.E5, duration: 0.62, delay: 0.18, gain: 0.28 },
  ],

  /**
   * The pot coming your way. C major, fuller and longer than `correct`, with
   * two sines above it for the chips.
   *
   * Deliberately not the same cue as answering correctly: at this table those
   * are different things. Being right and being paid can happen apart -- a pot
   * splits, a backer takes a cut of somebody else's answer -- and the sound
   * that means "chips" should never be the one that means "you knew it".
   */
  potWon: [
    { freq: N.C4, duration: 0.9, gain: 0.55 },
    { freq: N.E4, duration: 0.86, delay: 0.03, gain: 0.44 },
    { freq: N.G4, duration: 0.82, delay: 0.06, gain: 0.38 },
    { freq: N.C5, duration: 0.78, delay: 0.09, gain: 0.28 },
    { freq: N.G5, duration: 0.45, delay: 0.16, type: "sine", gain: 0.13 },
    { freq: N.C6, duration: 0.38, delay: 0.2, type: "sine", gain: 0.09 },
  ],
} satisfies Record<string, Note[]>;

export type Cue = keyof typeof CUES;

/**
 * The last five seconds of a turn, one entry per second remaining.
 *
 * The cue this replaces was a single soft tock at 196 Hz — identical every
 * second, and written to be ignorable. That is the wrong instruction: five
 * identical sounds say "time is passing", and what the player needs to hear is
 * "time is *running out*".
 *
 * So every parameter moves in the same direction as the clock, and each is a
 * device a listener already reads as tension without any of them being harsh:
 *
 * * **Pitch climbs** — C5 up to Bb5. Rising pitch is the oldest urgency signal
 *   there is, and it means the five sounds form a line rather than a repetition.
 * * **Dissonance arrives late** — from three seconds a minor second is stacked
 *   on top, the interval two notes make when they are too close to agree. The
 *   module's other cues are deliberately consonant; this is the one place where
 *   discomfort is the message.
 * * **It gets louder and drier** — gain rises, tails shorten. A long tail is
 *   relaxed; a clipped one is not.
 * * **The last two seconds double-strike** — two hits inside one second, so the
 *   pulse itself accelerates even though the clock does not. A heart rate, not
 *   a metronome.
 *
 * What deliberately does *not* change is the timbre. Still triangle and sine
 * through the same 2 kHz lowpass, because a sawtooth would be louder in the way
 * a smoke alarm is louder, and this plays five times a turn for a whole game.
 * Urgency here is carried by *what* the notes are, never by making them shrill.
 */
export const HURRY: Record<number, Note[]> = {
  5: [
    { freq: N.C5, duration: 0.16, gain: 0.28 },
    { freq: N.C3, duration: 0.13, type: "sine", gain: 0.3 },
  ],
  4: [
    { freq: N.D5, duration: 0.15, gain: 0.34 },
    { freq: N.C3, duration: 0.13, type: "sine", gain: 0.34 },
  ],
  3: [
    { freq: N.E5, duration: 0.14, gain: 0.4 },
    { freq: N.F5, duration: 0.12, gain: 0.16 },
    { freq: N.C3, duration: 0.13, type: "sine", gain: 0.38 },
  ],
  2: [
    { freq: N.Gb5, duration: 0.12, gain: 0.46 },
    { freq: N.G5, duration: 0.11, gain: 0.22 },
    { freq: N.C3, duration: 0.12, type: "sine", gain: 0.42 },
    { freq: N.Gb5, duration: 0.1, delay: 0.3, gain: 0.32 },
    { freq: N.C3, duration: 0.1, delay: 0.3, type: "sine", gain: 0.3 },
  ],
  1: [
    { freq: N.A5, duration: 0.11, gain: 0.52 },
    { freq: N.Bb5, duration: 0.1, gain: 0.3 },
    { freq: N.C3, duration: 0.12, type: "sine", gain: 0.5 },
    { freq: N.A5, duration: 0.1, delay: 0.26, gain: 0.42 },
    { freq: N.Bb5, duration: 0.09, delay: 0.26, gain: 0.24 },
    { freq: N.C3, duration: 0.1, delay: 0.26, type: "sine", gain: 0.4 },
  ],
};

/** How many seconds out the countdown starts. Matches the `urgent` styling. */
export const HURRY_FROM = 5;

let context: AudioContext | null = null;
let bus: GainNode | null = null;
let muted = false;
let restored = false;

/** Subscribers, so the toggle can render from this rather than mirror it. */
const listeners = new Set<() => void>();

function ensureRestored(): void {
  if (restored || typeof window === "undefined") return;
  restored = true;
  muted = window.localStorage.getItem(STORAGE_KEY) === "true";
}

export function isMuted(): boolean {
  ensureRestored();
  return muted;
}

/** Always false on the server, which has no localStorage to read. */
export function isMutedOnServer(): boolean {
  return false;
}

/**
 * For `useSyncExternalStore`. This is external state React does not own, and
 * subscribing is how a component tracks it without an effect that renders once
 * with the wrong answer and once with the right one.
 */
export function subscribeMuted(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function setMuted(next: boolean): void {
  ensureRestored();
  muted = next;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, String(next));
  }
  for (const listener of listeners) listener();
}

/**
 * Build (or resume) the audio context and its master chain. Call from a real
 * user gesture. Safe to call repeatedly, and safe to call when muted.
 */
export function unlock(): void {
  if (typeof window === "undefined") return;
  try {
    if (!context) {
      context = new AudioContext();
      const filter = context.createBiquadFilter();
      filter.type = "lowpass";
      filter.frequency.value = TONE_HZ;
      filter.Q.value = 0.6;

      bus = context.createGain();
      bus.gain.value = VOLUME;
      bus.connect(filter).connect(context.destination);
    }
    if (context.state === "suspended") void context.resume();
  } catch {
  }
}

export function play(cue: Cue): void {
  sound(CUES[cue] as Note[]);
}

/**
 * The urgency cue for one second of the closing countdown.
 *
 * Takes the seconds remaining rather than a cue name because the sound is
 * different every second — that escalation is the whole point, and five named
 * cues would only be this table with worse names. Anything outside the last
 * five seconds is silent, so the caller does not have to guard the range twice.
 */
export function playCountdown(secondsLeft: number): void {
  const notes = HURRY[secondsLeft];
  if (notes) sound(notes);
}

function sound(notes: Note[]): void {
  ensureRestored();
  if (muted || typeof window === "undefined") return;

  unlock();
  if (!context || !bus || context.state !== "running") return;

  const now = context.currentTime;
  for (const note of notes) {
    voice(context, bus, note, now);
  }
}

/** Attack. Long enough that a note swells rather than clicks. */
const ATTACK = 0.03;

function voice(ctx: AudioContext, out: GainNode, note: Note, now: number): void {
  const start = now + (note.delay ?? 0);
  const end = start + note.duration;

  const osc = ctx.createOscillator();
  osc.type = note.type ?? "triangle";
  osc.frequency.setValueAtTime(note.freq, start);

  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(note.gain ?? 0.5, start + ATTACK);
  gain.gain.exponentialRampToValueAtTime(0.0001, end);

  osc.connect(gain).connect(out);
  osc.start(start);
  osc.stop(end + 0.03);
}
