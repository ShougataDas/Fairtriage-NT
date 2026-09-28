import path from "node:path";
import type { NextConfig } from "next";

// All logic lives in the FastAPI service. The web app only calls its JSON API,
// proxied under the same origin so the browser never needs CORS.
const API = process.env.FAIRTRIAGE_API ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // a stray lockfile higher up the disk must not be taken as the project root
  turbopack: { root: path.join(__dirname) },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
