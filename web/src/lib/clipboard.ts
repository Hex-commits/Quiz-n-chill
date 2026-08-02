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
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
  }

  try {
    const field = document.createElement("textarea");
    field.value = text;
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
