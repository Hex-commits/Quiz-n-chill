"use client";

/**
 * The photograph on a category, and the way to see it properly.
 *
 * Three things here are not styling decisions.
 *
 * **Zoom must not steal the placement click.** A category card is itself a
 * button — with an answer selected, clicking it places that answer, and losing
 * that click to a lightbox would break the game to look at a picture. So the
 * magnifier is its own button with `stopPropagation`, and tapping the photo
 * body only zooms while the card is *not* armed. Armed, the whole card is a
 * drop target and the magnifier is the one way in.
 *
 * **The alt text can name the subject.** Unlike the earlier design, where the
 * photograph was the answer and naming it gave the round away, a category is
 * the question. Its label is drawn beside the picture anyway, so putting it in
 * the accessibility tree costs nothing and is the only thing that makes a
 * picture round describable at all.
 *
 * **The credit is a licence obligation, not a caption.** Most Commons images
 * are CC BY-SA, which requires attribution wherever the work is shown. It is
 * rendered from the first frame because that is when the work is shown.
 *
 * `next/image` is deliberately not used: these come straight from Commons,
 * which already serves a CDN-cached thumbnail at the width we ask for, so the
 * optimiser would add a rewrite through our own origin and buy nothing.
 */

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, X } from "lucide-react";

import type { CategoryImage } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Commons serves any width; ask for a big one only for the enlarged view. */
function atWidth(src: string, width: number) {
  return src.replace(/([?&]width=)\d+/, `$1${width}`);
}

export function CategoryPicture({
  image,
  label,
  /** True when a click on the card would place an answer, so the body must not zoom. */
  armed = false,
  className,
}: {
  image: CategoryImage;
  label: string;
  armed?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <span
        className={cn("group relative block overflow-hidden", className)}
        onClick={
          armed
            ? undefined
            : (event) => {
                event.stopPropagation();
                setOpen(true);
              }
        }
      >
        <img
          src={image.src}
          alt={label}
          loading="lazy"
          className="h-full w-full object-cover"
        />
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setOpen(true);
          }}
          aria-label={`${label} vergrößern`}
          className={cn(
            "absolute top-1.5 right-1.5 rounded-md bg-black/55 p-1.5 text-white",
            "opacity-0 transition-opacity duration-150",
            "group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100",
          )}
        >
          <Maximize2 className="size-3.5" aria-hidden />
        </button>
      </span>

      {open ? (
        <Lightbox image={image} label={label} onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}

/**
 * The enlarged view. Deliberately not a Radix dialog: the project has no dialog
 * primitive, and this needs exactly three behaviours — close on Escape, close
 * on backdrop, and don't let the page scroll underneath.
 *
 * **Rendered through a portal, and it has to be.** `position: fixed` is
 * measured against the viewport only while no ancestor has a transform — any
 * `transform`, `filter` or `will-change` on a parent makes that parent the
 * containing block instead, and the overlay is then trapped inside the card,
 * clipped by its `overflow-hidden`. Every category card carries
 * `animate-quiz-rise` (which animates `transform`) and grows another one on
 * hover while armed, so this was the difference between filling the screen and
 * filling a thumbnail. A portal moves the node to `document.body`, where there
 * is nothing above it to capture it.
 */
function Lightbox({
  image,
  label,
  onClose,
}: {
  image: CategoryImage;
  label: string;
  onClose: () => void;
}) {
  const close = useCallback(() => onClose(), [onClose]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [close]);

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onClick={close}
      className={cn(
        "fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 p-4 sm:p-8",
        "bg-black/80 backdrop-blur-sm",
        "animate-in fade-in duration-150",
      )}
    >
      <button
        type="button"
        onClick={close}
        aria-label="Schließen"
        className="absolute top-4 right-4 rounded-md bg-white/10 p-2 text-white hover:bg-white/20"
      >
        <X className="size-5" aria-hidden />
      </button>

      <img
        src={atWidth(image.src, 1280)}
        alt={label}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[80vh] max-w-full rounded-lg object-contain shadow-2xl"
      />

      <div className="max-w-2xl text-center text-white/85">
        <p className="text-sm font-medium">{label}</p>
        <ImageCredit image={image} className="text-white/60" />
      </div>
    </div>,
    document.body,
  );
}

/**
 * The attribution line. Renders nothing when there is no licence, which for a
 * stored picture cannot happen — `categories_image_is_complete` refuses a file
 * without one — but a missing licence must never print a bare photograph.
 */
export function ImageCredit({
  image,
  className,
}: {
  image: CategoryImage;
  className?: string;
}) {
  if (!image.licence) return null;
  return (
    <p className={cn("text-muted-foreground text-[10px] leading-tight", className)}>
      {image.credit ? `${image.credit} · ` : null}
      {image.licence_url ? (
        <a
          href={image.licence_url}
          target="_blank"
          rel="noreferrer noopener"
          onClick={(event) => event.stopPropagation()}
          className="underline underline-offset-2"
        >
          {image.licence}
        </a>
      ) : (
        image.licence
      )}
    </p>
  );
}
