import type { NextConfig } from "next";

// In production the FastAPI service owns /api on the same domain. Locally (or when the API is a
// separate deployment), set API_ORIGIN and Next proxies /api/* to it, so the browser code is identical.
const apiOrigin = process.env.API_ORIGIN;

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return apiOrigin ? [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }] : [];
  },
};

export default nextConfig;
