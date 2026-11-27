import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The UI is a plain client app. Exporting it as static files lets the API serve it from the same origin:
  // one service, one URL, no CORS. `npm run dev` still works against a separately running API.
  output: "export",
  trailingSlash: true, // /styleguide/ is served as styleguide/index.html by the static file server
};

export default nextConfig;
