import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/mpaCronTasks.test.tsx", "tests/mpaManagement.test.tsx"],
    coverage: {
      provider: "v8",
      include: [
        "src/adk/mpaCronTasks.ts",
        "src/cronjobs/Mpa*.tsx",
        "src/cronjobs/mpaSchedule.ts",
      ],
      reporter: ["text", "json-summary", "json"],
      thresholds: { lines: 96, statements: 96, functions: 96, branches: 96 },
    },
  },
});
