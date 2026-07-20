import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../vite.config.ts", import.meta.url),
  "utf8",
);

test("proxies the session trace API in development", () => {
  assert.match(source, /["']\/dev["']\s*:\s*API_TARGET/);
});
