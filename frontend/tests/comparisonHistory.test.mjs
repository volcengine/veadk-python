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
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
}

const history = await loadTypeScriptModule(
  "../src/create/comparison/comparisonHistory.ts",
);

test("keeps only the latest 20 comparison records per Draft", () => {
  let records = [];
  for (let index = 0; index < 21; index += 1) {
    records = history.appendComparisonRecord(records, {
      timestamp: index,
      fingerprint: `fp-${index}`,
      candidateName: `候选 ${index}`,
      configDiffs: [],
      metrics: { latencyMs: null, tokens: null },
      verdict: "持平",
      reason: "test",
      runId: `run-${index}`,
      sessionId: `session-${index}`,
    });
  }
  assert.equal(records.length, 20);
  assert.equal(records[0].fingerprint, "fp-20");
  assert.equal(records.at(-1).fingerprint, "fp-1");
});

test("serializes only the evidence summary and excludes secrets and full evidence", () => {
  const serialized = history.serializeComparisonRecords([
    {
      timestamp: 1,
      fingerprint: "fp",
      candidateName: "候选 A",
      configDiffs: [{ agentKey: "root", dimension: "model" }],
      metrics: { latencyMs: 123, tokens: 456 },
      verdict: "胜出",
      reason: "better",
      runId: "run-1",
      sessionId: "session-1",
      apiKey: "must-not-persist",
      fullOutput: "must-not-persist",
      trace: { secret: "must-not-persist" },
    },
  ]);
  assert.equal(serialized.includes("must-not-persist"), false);
  assert.equal(serialized.includes("run-1"), true);
});
