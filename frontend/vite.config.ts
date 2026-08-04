import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In dev, proxy the ADK API server routes to the backend started with
// `veadk frontend --dev` (default port 8000), so the app uses relative URLs
// in both dev and production (where it is served same-origin).
const API_TARGET = process.env.VEADK_API_TARGET ?? "http://127.0.0.1:8000";

function localApiProxy(): ProxyOptions {
  return {
    target: API_TARGET,
    configure(proxy) {
      proxy.on("proxyReq", (proxyRequest) => {
        // The browser talks to Vite same-origin. Do not forward browser-only
        // metadata that makes the backend classify the proxy hop as CORS.
        proxyRequest.removeHeader("origin");
        proxyRequest.removeHeader("referer");
      });
    },
  };
}

// Volcengine Skill Hub (findskill.com backend). Proxied because it sends no
// CORS headers, so the browser cannot call it cross-origin directly.
const SKILLHUB_TARGET = "https://skills.volces.com";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/list-apps": localApiProxy(),
      "/apps": localApiProxy(),
      "/run_sse": localApiProxy(),
      "/run": localApiProxy(),
      "/harness": localApiProxy(),
      "/debug": localApiProxy(),
      "/dev": localApiProxy(),
      "/oauth2": localApiProxy(),
      "/web": localApiProxy(),
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
