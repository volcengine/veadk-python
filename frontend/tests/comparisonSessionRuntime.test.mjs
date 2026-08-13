import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

async function loadTypeScriptModule(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  return import(moduleUrl);
}

const runtime = await loadTypeScriptModule(
  "../src/create/comparison/comparisonSessionRuntime.ts",
);

test("preserves the backend reason when a comparison environment cannot start", () => {
  const reason =
    "调试环境并发数已达上限 (4/4)，请稍后重试或关闭不再使用的调试页面。";

  assert.equal(runtime.debugRuntimeFailureMessage(new Error(reason)), reason);
  assert.equal(
    runtime.debugRuntimeFailureMessage({ reason }),
    "调试环境启动失败，请稍后重试。",
  );
});

test("stages every comparison runtime before returning success", async () => {
  const result = await runtime.stageComparisonRuntimes(
    [{ id: "baseline" }, { id: "variant-1" }],
    async ({ id }) => ({ runId: `run-${id}`, sessionId: `session-${id}` }),
    async () => assert.fail("cleanup must not run on success"),
  );
  assert.equal(result.ok, true);
  assert.deepEqual([...result.runtimes.keys()], ["baseline", "variant-1"]);
});

test("waits for all groups and cleans every staged success after one failure", async () => {
  const cleaned = [];
  const result = await runtime.stageComparisonRuntimes(
    [{ id: "baseline" }, { id: "variant-1" }, { id: "variant-2" }],
    async ({ id }) => {
      if (id === "variant-1") throw new Error("session failed");
      return { runId: `run-${id}` };
    },
    async (value) => cleaned.push(value.runId),
  );
  assert.equal(result.ok, false);
  assert.equal(result.failedTargetId, "variant-1");
  assert.deepEqual(cleaned.sort(), ["run-baseline", "run-variant-2"]);
});

test("cleanup errors never replace the primary creation failure", async () => {
  const result = await runtime.stageComparisonRuntimes(
    [{ id: "baseline" }, { id: "variant-1" }],
    async ({ id }) => {
      if (id === "variant-1") throw new Error("primary failure");
      return { runId: "run-baseline" };
    },
    async () => { throw new Error("cleanup failure"); },
  );
  assert.equal(result.ok, false);
  assert.equal(result.error.message, "primary failure");
});

test("continues cleanup after a synchronous cleanup error", async () => {
  const cleaned = [];
  const primaryFailure = new Error("primary failure");
  const result = await runtime.stageComparisonRuntimes(
    [{ id: "baseline" }, { id: "variant-1" }, { id: "variant-2" }],
    async ({ id }) => {
      if (id === "variant-1") throw primaryFailure;
      return { runId: `run-${id}` };
    },
    (value) => {
      cleaned.push(value.runId);
      if (value.runId === "run-baseline") throw new Error("cleanup failure");
      return Promise.resolve();
    },
  );
  assert.equal(result.ok, false);
  assert.equal(result.error, primaryFailure);
  assert.deepEqual(cleaned, ["run-baseline", "run-variant-2"]);
});
