import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy the ADK API server routes to the backend started with
// `veadk frontend --dev` (default port 8000), so the app uses relative URLs
// in both dev and production (where it is served same-origin).
const API_TARGET = process.env.VEADK_API_TARGET ?? "http://127.0.0.1:8000";
// Volcengine Skill Hub (findskill.com backend). Proxied because it sends no
// CORS headers, so the browser cannot call it cross-origin directly.
const SKILLHUB_TARGET = "https://skills.volces.com";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/list-apps": API_TARGET,
      "/apps": API_TARGET,
      "/run_sse": API_TARGET,
      "/run": API_TARGET,
      "/debug": API_TARGET,
      "/oauth2": API_TARGET,
      "/web": API_TARGET,
      "/skillhub": {
        target: SKILLHUB_TARGET,
        changeOrigin: true,
        secure: true,
        rewrite: (p) => p.replace(/^\/skillhub/, ""),
      },
    },
  },
  build: {
    // Build straight into the Python package so `veadk frontend` ships the UI
    // with the wheel and works for pip-installed users.
    outDir: "../veadk/webui",
    emptyOutDir: true,
  },
});
