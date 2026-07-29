import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);

test("debug errors support full expansion, copying, and footer restart", () => {
  assert.match(
    source,
    /import \{ DeploymentErrorMessage \} from "\.\.\/ui\/DeploymentErrorMessage"/,
  );
  assert.match(source, /className="cw-debug-error-detail"/);
  assert.match(source, /className="cw-debug-msg-error"/);
  assert.match(
    source,
    /className="cw-ab-start cw-ab-footer-start"[\s\S]*?onClick=\{\(\) => onStartVariant\(variant\.id\)\}/,
  );
});

test("debug test runs are persisted and reclaimed after refresh", () => {
  assert.match(source, /const DEBUG_TEST_RUN_STORAGE_KEY = "veadk\.generatedAgentTestRuns"/);
  assert.match(source, /window\.sessionStorage\.getItem\(DEBUG_TEST_RUN_STORAGE_KEY\)/);
  assert.match(source, /window\.sessionStorage\.setItem\(/);
  assert.match(source, /function rememberDebugTestRun\(runId: string\)/);
  assert.match(source, /function forgetDebugTestRun\(runId: string\)/);
  assert.match(source, /async function cleanupStoredDebugRuns\(\)/);
  assert.match(
    source,
    /const activeRunIds = new Set\([\s\S]*?debugRunsRef\.current\.values\(\)[\s\S]*?run\.runId/,
  );
  assert.match(
    source,
    /await cleanupStoredDebugRuns\(\);[\s\S]*?createdRun = await createGeneratedAgentTestRun/,
  );
  assert.match(source, /rememberDebugTestRun\(createdRun\.runId\)/);
  assert.match(source, /forgetDebugTestRun\(runtime\.run\.runId\)/);
});
