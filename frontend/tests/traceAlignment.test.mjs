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

const trace = await loadTypeScriptModule(
  "../src/create/comparison/traceAlignment.ts",
);

test("aligns trace evidence only with exact invocation or tool call identities", () => {
  const result = trace.alignTraceEvidence(
    [
      { id: "b1", name: "model", invocationId: "inv-1" },
      { id: "b2", name: "search", toolCallId: "call-1" },
      { id: "b3", name: "similar wording" },
    ],
    [
      { id: "c1", name: "model", invocationId: "inv-1" },
      { id: "c2", name: "different label", toolCallId: "call-1" },
      { id: "c3", name: "similar wording changed" },
    ],
  );
  assert.deepEqual(result.matches, [
    { baselineId: "b1", candidateId: "c1", key: "invocation:inv-1:model" },
    { baselineId: "b2", candidateId: "c2", key: "tool:call-1" },
  ]);
  assert.deepEqual(result.unmatchedBaselineIds, ["b3"]);
  assert.deepEqual(result.unmatchedCandidateIds, ["c3"]);
});

test("aligns independent runs by deterministic logical span paths", () => {
  const result = trace.alignTraceEvidence(
    [
      { id: "b1", name: "invocation", invocationId: "inv-baseline", startTime: 1 },
      { id: "b2", name: "invoke_agent", invocationId: "inv-baseline", parentId: "b1", startTime: 2 },
      { id: "b3", name: "call_llm", invocationId: "inv-baseline", parentId: "b2", startTime: 3 },
      { id: "b4", name: "generate_content openai/doubao-seed-2-1-pro-260628", invocationId: "inv-baseline", parentId: "b3", startTime: 4 },
    ],
    [
      { id: "c1", name: "invocation", invocationId: "inv-candidate", startTime: 11 },
      { id: "c2", name: "invoke_agent", invocationId: "inv-candidate", parentId: "c1", startTime: 12 },
      { id: "c3", name: "call_llm", invocationId: "inv-candidate", parentId: "c2", startTime: 13 },
      { id: "c4", name: "generate_content openai/doubao-seed-2-0-lite-260428", invocationId: "inv-candidate", parentId: "c3", startTime: 14 },
    ],
  );

  assert.deepEqual(result.matches, [
    { baselineId: "b1", candidateId: "c1", key: "path:invocation[0]" },
    { baselineId: "b2", candidateId: "c2", key: "path:invocation[0]/invoke_agent[0]" },
    { baselineId: "b3", candidateId: "c3", key: "path:invocation[0]/invoke_agent[0]/call_llm[0]" },
    { baselineId: "b4", candidateId: "c4", key: "path:invocation[0]/invoke_agent[0]/call_llm[0]/generate_content[0]" },
  ]);
  assert.deepEqual(result.unmatchedBaselineIds, []);
  assert.deepEqual(result.unmatchedCandidateIds, []);
});

test("attributes evidence to a dimension only for one Agent, one dimension, and shared input", () => {
  assert.equal(
    trace.attributionLevel({ agentCount: 1, dimensionCount: 1, inputDiverged: false }),
    "dimension",
  );
  assert.equal(
    trace.attributionLevel({ agentCount: 2, dimensionCount: 1, inputDiverged: false }),
    "scheme",
  );
  assert.equal(
    trace.attributionLevel({ agentCount: 1, dimensionCount: 1, inputDiverged: true }),
    "scheme",
  );
});
