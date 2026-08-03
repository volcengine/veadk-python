import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const client = readFileSync(new URL("../src/adk/client.ts", import.meta.url), "utf8");

test("a stale 404 session does not fail hydration of the entire sidebar", () => {
  assert.match(app, /Promise\.allSettled\(/);
  assert.match(app, /get session failed:\\s\*404/);
  assert.match(app, /result\.status === "fulfilled" \? \[result\.value\] : \[\]/);
});

test("session and run errors preserve upstream response details", () => {
  assert.match(client, /httpErrorMessage\(res, "读取会话失败"\)/);
  assert.match(client, /httpErrorMessage\(res, "运行会话失败"\)/);
  assert.match(client, /sessions\/\$\{encodeURIComponent\(sessionId\)\}/);
});
