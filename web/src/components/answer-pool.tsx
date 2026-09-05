"use client";

/**
 * The answers, as a row of chips you pick one of.
 *
 * Shared, because both games ask the same question of a player -- "which of
 * these" -- and there is no reason for the answer to look like one thing on a
 * Zuordnung board and another at the poker table. What differs between them is
 * what a pick *does*: Classic then places it in a category, Poker locks it in
 * against a pot. Neither of those is in here.
 *
 * Everything in the styling is doing a job, and the two that look like taste
 * are not:
 *
 * The gap is `3`, not `2.5`. A picked chip scales, lifts, and grows a 2px
 * outline 2px clear of its own box; at `gap-2.5` two neighbours' outlines met
 * in the middle.
 *
 * The pick is an outline, not a ring. The gap an outline leaves is transparent,
 * so the card shows between the fill and the edge. A ring at the same offset
 * paints its own backdrop over the card and reads as one thick smear.
 *
 * An answer may be a photograph rather than a word -- Poker chooses between the
 * categories, and on a picture round those are pictures. The photo is drawn
 * plainly, with no magnifier and no lightbox: both are buttons, and a button
 * inside a button is neither valid nor clickable. The credits sit under the
 * pool instead of on each chip for the same reason -- a licence link cannot
 * live inside the chip that answers the question -- and they have to be there,
 * because CC BY-SA wants attribution wherever the work is shown.
 */

import { useEffect, useRef } from "react";

import { ImageCredit } from "@/components/category-image";
import { Button } from "@/components/ui/button";
import type { CategoryImage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { wobble } from "@/lib/wobble";

export type Answer = {
  id: string;
  /** Held back while naming it would answer the question. */
  label: string | null;
  image?: CategoryImage | null;
};

export function AnswerPool({
  items,
  selectedId,
  correctId,
  disabled,
  onSelect,
  onPick,
  pulse,
}: {
  items: Answer[];
  selectedId: string | null;
  /**
   * The right answer, once there is no longer anything to lose by saying it.
   * Setting it turns the pool into the reveal: the answer goes green, a pick
   * that missed it goes red, and nothing takes a click any more.
   */
  correctId?: string | null;
  disabled?: boolean;
  /** Called with null when the pick is being taken back. */
  onSelect: (itemId: string | null) => void;
  /**
   * The chip that was clicked, whichever way the selection went -- so a pick
   * being taken back is still a click, and still reportable. `onSelect` says
   * what the pool now holds; this says what the player just pressed.
   */
  onPick?: (itemId: string) => void;
  /**
   * A pick made on somebody else's screen, to wiggle on this one too.
   *
   * A fresh object every time, even for the same chip twice: identity is what
   * fires it, because an id on its own cannot tell a repeat from a re-render.
   */
  pulse?: { id: string } | null;
}) {
  /* Held so an incoming pick can be wiggled the same way a local one is --
     there is one chip per answer, and a pick from either side moves it. */
  const chips = useRef(new Map<string, HTMLButtonElement>());

  useEffect(() => {
    if (pulse) wobble(chips.current.get(pulse.id));
  }, [pulse]);

  /* Mapped rather than filtered, so the narrowing survives: a `.filter` on a
     truthy field still hands back the optional type. */
  const credits = items.flatMap((item) =>
    item.image ? [{ id: item.id, image: item.image }] : [],
  );

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-center gap-3 sm:gap-3.5">
        {items.map((item) => {
          const picked = selectedId === item.id;
          const right = correctId != null && correctId === item.id;
          const wrong = correctId != null && picked && !right;
          return (
            <Button
              key={item.id}
              ref={(el) => {
                if (el) chips.current.set(item.id, el);
                else chips.current.delete(item.id);
              }}
              size="lg"
              className={cn(
                "quiz-shine h-auto min-h-12 px-5 py-2.5 text-base font-semibold whitespace-normal",
                item.image && "flex-col gap-1.5 px-2 py-2",
                "ease-(--ease-soft) transition-all duration-200",
                /* A lifted or picked chip reaches outside its own box, and
                   `quiz-shine` positions every chip, so without a z-index the
                   next chip along paints over the edge that says which one is
                   picked. */
                "hover:z-10 hover:-translate-y-0.5 hover:scale-[1.03] hover:shadow-lg",
                "active:translate-y-0 active:scale-[0.98] active:duration-75",
                picked &&
                  "outline-primary z-10 scale-[1.03] shadow-lg outline-solid outline-2 outline-offset-2",
                /* The answer is the loudest chip in the pool -- filled, lifted
                   and outlined, whether or not anybody picked it. */
                right &&
                  "bg-success text-success-foreground hover:bg-success outline-success z-10 scale-[1.03] shadow-lg outline-solid outline-2 outline-offset-2",
                wrong && "outline-destructive z-10 outline-solid outline-2 outline-offset-2",
                /* A revealed pool is a statement, not a question. Left visible
                   rather than `disabled`, which would fade the answer just as
                   it is being made. */
                correctId != null && "pointer-events-none",
              )}
              variant={wrong ? "destructive" : picked || right ? "default" : "outline"}
              disabled={disabled}
              aria-pressed={picked}
              onClick={(event) => {
                wobble(event.currentTarget);
                onPick?.(item.id);
                onSelect(picked ? null : item.id);
              }}
            >
              {item.image ? (
                /* Absolute inside a sized frame, as the category cards do it: in
                   flow a photograph reports its own scaled height as a minimum,
                   and a chip that cannot give way pushes the pool off screen. */
                <span className="relative block h-20 w-28 overflow-hidden rounded-md sm:h-24 sm:w-36">
                  <img
                    src={item.image.src}
                    alt={item.label ?? "Answer"}
                    loading="lazy"
                    className="absolute inset-0 h-full w-full object-cover"
                  />
                </span>
              ) : null}
              {item.label}
            </Button>
          );
        })}
      </div>

      {credits.length > 0 ? (
        <div className="flex flex-wrap justify-center gap-x-3 gap-y-0.5">
          {credits.map((credit) => (
            <ImageCredit key={credit.id} image={credit.image} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
