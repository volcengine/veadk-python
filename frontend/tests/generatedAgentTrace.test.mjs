import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const traceDrawerSource = readFileSync(
  new URL("../src/ui/TraceDrawer.tsx", import.meta.url),
  "utf8",
);

test("loads generated-agent traces through the run-scoped API", () => {
  assert.match(clientSource, /export async function getGeneratedAgentTestTrace/);
  assert.match(
    clientSource,
    /generated-agent-test-runs\/\$\{encodeURIComponent\(runId\)\}\/trace\/session\/\$\{encodeURIComponent\(sessionId\)\}/,
  );
  assert.match(traceDrawerSource, /getGeneratedAgentTestTrace\(testRunId, sessionId\)/);
});

test("shows a per-variant trace action only after a completed debug turn", () => {
  assert.match(customCreateSource, /onOpenTrace: \(id: string\) => void/);
  assert.match(customCreateSource, /className="cw-ab-trace"/);
  assert.match(customCreateSource, /disabled=\{!traceAvailable\}/);
  assert.match(customCreateSource, /onClick=\{\(\) => onOpenTrace\(variant\.id\)\}/);
  assert.match(customCreateSource, /testRunId=\{debugTraceTarget\.runId\}/);
});
