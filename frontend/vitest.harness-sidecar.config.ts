import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/harnessSidecarCoverage.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/create/harnessSidecarOptions.ts"],
      reporter: ["text", "json-summary"],
      thresholds: {
        statements: 91,
        branches: 91,
        functions: 91,
        lines: 91,
      },
    },
  },
});
