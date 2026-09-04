import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("session creation surfaces the backend error detail with its status", () => {
  assert.match(clientSource, /const fallback = adkT\("client\.createSessionFailedWithStatus", \{ status: res\.status \}\)/);
  assert.match(
    clientSource,
    /const detail = await httpErrorMessage\(res, adkT\("client\.createSessionFailed"\)\)/,
  );
  assert.match(
    clientSource,
    /detail === fallback \? fallback : adkT\("common\.fallbackWithDetail", \{ fallback, detail \}\)/,
  );
});

test("runtime listing surfaces HTTP status and backend detail", () => {
  assert.match(clientSource, /const detail = await httpErrorMessage\(res, adkT\("client\.loadRuntimeFailed"\)\)/);
  assert.match(clientSource, /throw new Error\(detail\)/);
  assert.doesNotMatch(clientSource, /`\$\{summary\}：\$\{detail\}`/);
});
