/**
 * Wiggle an element, the way the lobby code wiggles when you copy it.
 *
 * By hand rather than by a rendered class, because the class alone only ever
 * fires once: React leaves it on the element between clicks, and an animation
 * that is already applied does not restart when it is applied again. Taking it
 * off, reading a layout property to make the removal take, and putting it back
 * is how you say "again" to CSS.
 *
 * The delay is cleared because the element may have entered on a stagger -- a
 * category card comes in on one, up to a third of a second of it -- and
 * `animation-delay` set inline for that entrance would hold the reply to a
 * click for just as long. See `.animate-quiz-wobble` in `globals.css` for the
 * other half of sharing an element with an entrance.
 */
export function wobble(el: HTMLElement | null | undefined) {
  if (!el) return;
  el.classList.remove("animate-quiz-wobble");
  void el.offsetWidth;
  el.style.animationDelay = "0s";
  el.classList.add("animate-quiz-wobble");
}
