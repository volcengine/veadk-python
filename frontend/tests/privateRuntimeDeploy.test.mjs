import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("AgentKit deploy accepts private runtimes that only return runtimeId", () => {
  assert.doesNotMatch(clientSource, /!final\.url\s*\|\|\s*!final\.agentName/);
  assert.match(clientSource, /if \(!final\.agentName\)/);
  assert.match(clientSource, /if \(!final\.runtimeId && !final\.url\)/);
  assert.match(clientSource, /url:\s*final\.url \?\? ""/);
});
