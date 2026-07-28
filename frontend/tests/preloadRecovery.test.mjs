import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const mainSource = readFileSync(
  new URL("../src/main.tsx", import.meta.url),
  "utf8",
);

test("reloads once when a stale lazy-loaded asset is missing", () => {
  assert.match(mainSource, /addEventListener\("vite:preloadError"/);
  assert.match(mainSource, /event\.preventDefault\(\)/);
  assert.match(mainSource, /sessionStorage\.setItem\(PRELOAD_RECOVERY_KEY/);
  assert.match(mainSource, /window\.location\.reload\(\)/);
  assert.ok(
    mainSource.indexOf('addEventListener("vite:preloadError"') <
      mainSource.indexOf("ReactDOM.createRoot"),
  );
});
