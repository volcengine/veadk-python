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

test("shows trace actions for variants with real completed debug output", () => {
  assert.match(customCreateSource, /onOpenTrace: \(id: string\) => void/);
  assert.match(
    customCreateSource,
    /const traceableVariants = variants\.filter[\s\S]*?message\.role === "assistant" && !message\.error/,
  );
  assert.match(
    customCreateSource,
    /\{traceableVariants\.length > 0 && \([\s\S]*?className="cw-ab-verdict"/,
  );
  assert.match(
    customCreateSource,
    /traceableVariants\.map[\s\S]*?onClick=\{\(\) => onOpenTrace\(variant\.id\)\}[\s\S]*?调用链路/,
  );
  assert.doesNotMatch(customCreateSource, /本轮裁判推荐|1\.8s|2\.3s/);
  assert.match(customCreateSource, /testRunId=\{debugTraceTarget\.runId\}/);
});
