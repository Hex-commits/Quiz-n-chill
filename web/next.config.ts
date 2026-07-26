import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits `.next/standalone` with a minimal server bundle. Used by the
  // production stage of the Dockerfile; harmless on Vercel, which ignores it.
  output: "standalone",
};

export default nextConfig;
