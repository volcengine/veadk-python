import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/a2aWaiting.test.tsx"],
    coverage: { provider: "v8", include: ["src/blocks.ts", "src/ui/Blocks.tsx"], reporter: ["json"], reportsDirectory: "/tmp/studio-a2a-coverage" },
  },
});
