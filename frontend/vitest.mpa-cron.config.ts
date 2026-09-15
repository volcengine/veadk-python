import { defineConfig } from "vitest/config";
export default defineConfig({ test: {
  environment: "jsdom", include: ["tests/mpaCronTasks.test.tsx"],
  coverage: { provider: "v8", include: ["src/adk/mpaCronTasks.ts", "src/cronjobs/MpaCronTasks.tsx"],
    reporter: ["text", "json-summary"], thresholds: { lines: 96, statements: 96, functions: 96, branches: 96 } },
} });
