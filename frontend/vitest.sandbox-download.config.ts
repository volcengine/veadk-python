import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/sandboxDownload*.test.*"],
    coverage: {
      provider: "v8",
      include: ["src/ui/SandboxFileLink.tsx", "src/ui/Markdown.tsx", "src/adk/client.ts"],
      reporter: ["text", "json", "json-summary"],
      thresholds: { "src/ui/SandboxFileLink.tsx": { lines: 96, statements: 96, functions: 96, branches: 96 } },
    },
  },
});
