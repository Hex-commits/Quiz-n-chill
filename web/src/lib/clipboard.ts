/**
 * Copy text, with a fallback for browsers that will not hand out the async
 * clipboard.
 *
 * `navigator.clipboard` only exists in a secure context, so it is there in
 * production (Vercel, HTTPS) and missing whenever the dev server is opened from
 * a phone on the LAN over plain `http://192.168.x.x` -- which is exactly how a
 * lobby gets tested. The hidden-textarea route still works there.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    // Guarded rather than try/caught alone: on an insecure origin
    // `navigator.clipboard` is undefined, and reading `.writeText` off it
    // throws before any promise exists.
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Denied permission or a browser that refuses outside a user gesture it
    // recognises -- fall through and try the old way.
  }

  try {
    const field = document.createElement("textarea");
    field.value = text;
    // Off-screen rather than `display: none`: a hidden field cannot be
    // selected, and without a selection there is nothing to copy.
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.top = "-1000px";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(field);
    return copied;
  } catch {
    return false;
  }
}
