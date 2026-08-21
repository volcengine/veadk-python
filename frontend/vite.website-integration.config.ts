import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "../veadk/webui",
    emptyOutDir: false,
    lib: {
      entry: "src/website-integration/main.tsx",
      name: "VeadkWebsiteIntegration",
      formats: ["iife"],
      fileName: () => "website-integration.js",
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        assetFileNames: "assets/widget/[name]-[hash][extname]",
      },
    },
  },
});
