import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy the ADK API server routes to the backend started with
// `veadk frontend --dev` (default port 8000), so the app uses relative URLs
// in both dev and production (where it is served same-origin).
const API_TARGET = process.env.VEADK_API_TARGET ?? "http://127.0.0.1:8000";
// Volcengine Skill Hub (findskill.com backend). Proxied because it sends no
// CORS headers, so the browser cannot call it cross-origin directly.
const SKILLHUB_TARGET = "https://skills.volces.com";

export default defineConfig(({ mode }) => {
  // Only expose the WebPro browser credentials from the repository-level .env.
  // Vite's usual VITE_* passthrough is intentionally not enabled for other keys.
  const env = loadEnv(mode, "..", "");
  return {
    plugins: [react()],
    define: {
      __APMPLUS_AID__: JSON.stringify(env.APM_APP_ID ?? ""),
      __APMPLUS_TOKEN__: JSON.stringify(env.APM_APP_TOKEN ?? ""),
      __APMPLUS_ENABLED__: JSON.stringify(env.APM_ENABLED ?? "true"),
      __APMPLUS_ENV__: JSON.stringify(env.APM_ENV ?? mode),
    },
    server: {
      port: 5173,
      proxy: {
        "/list-apps": API_TARGET,
        "/apps": API_TARGET,
        "/run_sse": API_TARGET,
        "/run": API_TARGET,
        "/debug": API_TARGET,
        "/dev": API_TARGET,
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
  };
});
