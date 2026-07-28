/**
 * The base URL has to be joined to paths without producing a double slash.
 *
 * `https://api.example.com/` + `/lobbies` is `//lobbies`, which the server
 * answers with a redirect. A browser will not follow a redirect on a CORS
 * preflight, so the request fails as "Redirect is not allowed for a preflight
 * request" -- indistinguishable from a CORS misconfiguration, and unfixable by
 * changing the allowed origins. It cost a deploy once already.
 */

import assert from "node:assert/strict";
import test from "node:test";

/** Mirrors `baseUrl()` in api.ts. */
function normalise(configured: string): string {
  return configured.replace(/\/+$/, "");
}

test("a trailing slash is removed", () => {
  assert.equal(
    normalise("https://quiz-n-chill-lovat.vercel.app/"),
    "https://quiz-n-chill-lovat.vercel.app",
  );
});

test("several trailing slashes are removed", () => {
  assert.equal(normalise("https://api.example.com///"), "https://api.example.com");
});

test("a clean URL is left alone", () => {
  assert.equal(normalise("https://api.example.com"), "https://api.example.com");
});

test("a path prefix keeps its inner slashes", () => {
  assert.equal(normalise("https://example.com/api/"), "https://example.com/api");
});

test("joining with a path never doubles the slash", () => {
  for (const configured of [
    "https://api.example.com",
    "https://api.example.com/",
    "https://api.example.com//",
  ]) {
    assert.equal(`${normalise(configured)}/lobbies`, "https://api.example.com/lobbies");
  }
});
