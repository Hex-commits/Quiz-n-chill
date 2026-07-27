import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
