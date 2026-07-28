import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // There is a package-lock.json at the repo root as well as in here, and
  // Turbopack otherwise walks up and picks the repo as its workspace root.
  // That matters on Vercel, which clones the whole repository before building
  // this directory -- so the parent lockfile is present there too, and module
  // resolution would differ from a local build for no visible reason.
  turbopack: { root: process.cwd() },

  // Emits `.next/standalone` with a minimal server bundle. Used by the
  // production stage of the Dockerfile; harmless on Vercel, which ignores it.
  output: "standalone",

  // There is no landing page: the root goes straight to the join screen.
  // Handled here rather than by a page that calls redirect(), so the server
  // answers with a 307 before any React rendering happens.
  //
  // `permanent: false` on purpose -- a 308 would be cached by browsers
  // indefinitely, making a future landing page impossible to reintroduce for
  // anyone who had already visited.
  async redirects() {
    return [{ source: "/", destination: "/play", permanent: false }];
  },
};

export default nextConfig;
