/**
 * The Quiz & Chill mark and wordmark.
 *
 * Borrowed from the Netflix logo, which does two things this app can use:
 *
 * **The letterform is a strip of material.** A face turned away from the light
 * is simply a different flat colour — no gradient, no bevel, no soft shadow.
 * The ring is a strip that twists at top and bottom, so the right half and the
 * tail are the same side of it and share a tone. Two colours, not three: the
 * tail was never a separate object.
 *
 * **The wordmark is heavy, condensed and very tight.** Almost touching, which
 * is what makes it read as one object rather than a row of letters.
 *
 * What is deliberately *not* borrowed is the red, the actual N, and the splayed
 * perspective of the real wordmark. The colour is the app's own amber; the
 * arch is offered as a variant below but is off by default, because at header
 * size it costs more legibility than it buys character.
 *
 * The mark is duplicated here rather than imported from `public/logo-mark.svg`:
 * inline SVG can take `currentColor` and size in `em`, and an `<img>` cannot.
 * The file in `public/` is the standalone copy for the favicon and anywhere
 * outside React — if the geometry changes, change both.
 */

import { cn } from "@/lib/utils";

/**
 * Two tones, because there are two faces.
 *
 * The lit face and the face turned away. The tail is not a third thing — it is
 * the back face continuing out of the ring, so it takes the same colour.
 */
const RIBBON = {
  front: "#FFB43C",
  back: "#E58200",
} as const;

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="48 48 160 160"
      className={cn("size-6 shrink-0", className)}
      role="img"
      aria-label="Quiz & Chill"
    >
      <g fill="none" strokeWidth={34} strokeLinecap="butt">
        <path d="M122 70 A 52 52 0 0 0 122 174" stroke={RIBBON.front} />
        <path d="M122 70 A 52 52 0 0 1 122 174" stroke={RIBBON.back} />
        <path d="M138 138 L190 190" stroke={RIBBON.back} />
      </g>
    </svg>
  );
}

export function Logo({
  className,
  /**
   * The splayed arch of the real Netflix wordmark. Genuinely more characterful
   * at hero size and genuinely worse at 14px, so it is opt-in rather than the
   * default — the header is the place this renders most often.
   */
  arched = false,
}: {
  className?: string;
  arched?: boolean;
}) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark className="size-[1.35em]" />
      <span
        className={cn(
          "font-black tracking-[-0.055em] uppercase",
          arched && "inline-block [transform:perspective(320px)_rotateX(14deg)]",
        )}
      >
        Quiz <span className="text-primary">&amp;</span> Chill
      </span>
    </span>
  );
}
