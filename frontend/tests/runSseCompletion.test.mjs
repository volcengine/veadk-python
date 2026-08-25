import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);

test("conversation reports a completed stream that has no final displayable reply", () => {
  assert.match(appSource, /let hasCompletedReply = false/);
  assert.match(
    appSource,
    /event\.partial !== true &&[\s\S]*?turnHasVisibleContent\(\{ role: "assistant", blocks \}\)[\s\S]*?hasCompletedReply = true/,
  );
  assert.match(
    appSource,
    /!ctrl\.signal\.aborted && !streamFailed && !hasCompletedReply[\s\S]*?RUN_SSE_INCOMPLETE_RESPONSE_ERROR[\s\S]*?setError/,
  );
  assert.match(
    appSource,
    /finally \{[\s\S]*?!ctrl\.signal\.aborted &&[\s\S]*?streamFailed &&[\s\S]*?text\.trim\(\)[\s\S]*?setInput\(\(current\) => current\.trim\(\) \? current : text\)/,
  );
});

test("conversation keeps aborts separate from unexpected stream failures", () => {
  assert.match(
    appSource,
    /\(e as Error\)\?\.name !== "AbortError"[\s\S]*?!ctrl\.signal\.aborted/,
  );
  assert.match(
    appSource,
    /e instanceof Error \? e\.message : String\(e\)/,
  );
  assert.match(appSource, /streamFailed = true;\s*streamError = e;/);
});

test("function-response recovery rejects partial-only and empty resumed streams", () => {
  const onAuthSource = appSource.slice(
    appSource.indexOf("async function onAuth"),
    appSource.indexOf("// Hooks must stay above", appSource.indexOf("async function onAuth")),
  );
  assert.match(onAuthSource, /let streamFailed = false;[\s\S]*?let hasCompletedReply = false/);
  assert.match(
    onAuthSource,
    /event\.partial !== true &&[\s\S]*?turnHasVisibleContent\(\{ role: "assistant", blocks: acc\.blocks \}\)[\s\S]*?hasCompletedReply = true/,
  );
  assert.match(
    onAuthSource,
    /!ctrl\.signal\.aborted && !streamFailed && !hasCompletedReply[\s\S]*?RUN_SSE_INCOMPLETE_RESPONSE_ERROR[\s\S]*?setError/,
  );
  assert.match(onAuthSource, /catch \(e\) \{\s*streamFailed = true;/);
  assert.match(onAuthSource, /setError\(e instanceof Error \? e\.message : String\(e\)\)/);
});
