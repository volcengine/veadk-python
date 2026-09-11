import { componentApiPlugin } from "./scripts/componentApiPlugin";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    componentApiPlugin(),
    {
      name: "components-preview-entry",
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          if (request.url === "/") {
            response.writeHead(302, { Location: "/components-preview/" });
            response.end();
            return;
          }
          next();
        });
      },
    },
  ],
  cacheDir: "node_modules/.vite-components",
  optimizeDeps: { entries: ["components-preview/index.html"] },
  server: { host: "127.0.0.1", port: 5186, strictPort: true },
});
