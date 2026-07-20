import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);

test("shows session metadata only after the conversation starts", () => {
  assert.match(appSource, /showMeta=\{turns\.length > 0\}/);
  assert.match(
    composerSource,
    /\{showMeta && \(\s*<div className="composer-meta">/,
  );
});
