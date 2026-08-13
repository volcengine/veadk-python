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

const state = await loadTypeScriptModule(
  "../src/create/comparison/debugVariantState.ts",
);

function change(overrides = {}) {
  return {
    id: "root:model",
    modelName: "root-model",
    modelProvider: "openai",
    modelApiBase: "https://models.example.com/v1",
    apiKey: "",
    apiKeyLocked: false,
    apiKeyVisible: false,
    instruction: "Root prompt",
    selectedSkills: [],
    agentKey: "root",
    dimension: "model",
    ...overrides,
  };
}

function variant(overrides = {}) {
  return {
    ...change(),
    additionalChanges: [],
    ...overrides,
  };
}

function variantChanges(candidate) {
  return [
    change({
      ...candidate,
      id: `${candidate.agentKey}:${candidate.dimension}`,
      additionalChanges: undefined,
    }),
    ...candidate.additionalChanges,
  ].map(({ additionalChanges: _additionalChanges, ...item }) => item);
}

function summaryKeys(summary) {
  return summary.flatMap((group) =>
    group.changes.map(
      ({ change: item }) => `${item.agentKey}:${item.dimension}`,
    ),
  );
}

test("switching Agents restores each Agent and dimension edit", () => {
  const rootBaseline = change();
  const workerBaseline = change({
    id: "0:model",
    agentKey: "0",
    modelName: "worker-model",
    instruction: "Worker prompt",
  });
  const editedRoot = variant({ modelName: "root-candidate" });

  const editingWorker = state.switchPrimaryDebugChange(
    editedRoot,
    rootBaseline,
    workerBaseline,
  );
  const editedWorker = { ...editingWorker, modelName: "worker-candidate" };
  const editingRootAgain = state.switchPrimaryDebugChange(
    editedWorker,
    workerBaseline,
    rootBaseline,
  );

  assert.equal(editingRootAgain.agentKey, "root");
  assert.equal(editingRootAgain.dimension, "model");
  assert.equal(editingRootAgain.modelName, "root-candidate");
  assert.deepEqual(
    editingRootAgain.additionalChanges.map((item) => ({
      agentKey: item.agentKey,
      dimension: item.dimension,
      modelName: item.modelName,
    })),
    [{ agentKey: "0", dimension: "model", modelName: "worker-candidate" }],
  );
});

test("temporary credentials survive dimension switching without storing untouched defaults", () => {
  const modelBaseline = change();
  const instructionBaseline = change({
    id: "root:instruction",
    dimension: "instruction",
  });

  const untouched = state.switchPrimaryDebugChange(
    variant(),
    modelBaseline,
    instructionBaseline,
  );
  assert.deepEqual(untouched.additionalChanges, []);

  const withTemporaryCredential = state.switchPrimaryDebugChange(
    variant({ apiKey: "temporary-key", apiKeyVisible: true }),
    modelBaseline,
    instructionBaseline,
  );
  const backOnModel = state.switchPrimaryDebugChange(
    withTemporaryCredential,
    instructionBaseline,
    modelBaseline,
  );

  assert.equal(backOnModel.apiKey, "temporary-key");
  assert.equal(backOnModel.apiKeyVisible, true);
  assert.deepEqual(backOnModel.additionalChanges, []);
});

test("the complete change summary stays stable while the editor focus moves", () => {
  const rootBaseline = change();
  const workerInstructionBaseline = change({
    id: "worker:instruction",
    agentKey: "worker",
    dimension: "instruction",
    instruction: "Worker prompt",
  });
  const candidate = variant({
    modelName: "root-candidate",
    additionalChanges: [
      {
        ...workerInstructionBaseline,
        instruction: "Worker candidate prompt",
      },
      change({
        id: "worker:skills",
        agentKey: "worker",
        dimension: "skills",
        selectedSkills: [{ name: "web-search" }],
      }),
    ],
  });

  const before = state.summarizeDebugChanges(
    variantChanges(candidate),
    ["root", "worker"],
    candidate.agentKey,
    candidate.dimension,
  );
  const editingWorker = state.switchPrimaryDebugChange(
    candidate,
    rootBaseline,
    workerInstructionBaseline,
  );
  const after = state.summarizeDebugChanges(
    variantChanges(editingWorker),
    ["root", "worker"],
    editingWorker.agentKey,
    editingWorker.dimension,
  );

  assert.deepEqual(summaryKeys(before), [
    "root:model",
    "worker:instruction",
    "worker:skills",
  ]);
  assert.deepEqual(summaryKeys(after), summaryKeys(before));
  assert.deepEqual(
    before.map((group) => [group.agentKey, group.changes.length]),
    after.map((group) => [group.agentKey, group.changes.length]),
  );
  assert.equal(
    before.flatMap((group) => group.changes).find((item) => item.active)
      .change.agentKey,
    "root",
  );
  assert.equal(
    after.flatMap((group) => group.changes).find((item) => item.active)
      .change.agentKey,
    "worker",
  );
});

test("previews the first three stable changes without losing Agent groups", () => {
  const summary = state.summarizeDebugChanges(
    [
      change({
        id: "writer:skills",
        agentKey: "writer",
        dimension: "skills",
      }),
      change({
        id: "researcher:instruction",
        agentKey: "researcher",
        dimension: "instruction",
      }),
      change({
        id: "researcher:model",
        agentKey: "researcher",
        dimension: "model",
      }),
      change({
        id: "writer:model",
        agentKey: "writer",
        dimension: "model",
      }),
    ],
    ["researcher", "writer"],
    "writer",
    "skills",
  );

  const preview = state.previewDebugChangeSummary(summary, 3);
  assert.deepEqual(summaryKeys(preview.groups), [
    "researcher:model",
    "researcher:instruction",
    "writer:model",
  ]);
  assert.equal(preview.hiddenCount, 1);
  assert.deepEqual(state.previewDebugChangeSummary(summary, 0), {
    groups: [],
    hiddenCount: 4,
  });
  assert.equal(state.previewDebugChangeSummary(summary, 99).hiddenCount, 0);
});

test("removing a change handles both the focused editor and stored changes", () => {
  const rootBaseline = change();
  const workerInstruction = change({
    id: "worker:instruction",
    agentKey: "worker",
    dimension: "instruction",
    instruction: "Worker candidate prompt",
  });
  const candidate = variant({
    modelName: "root-candidate",
    additionalChanges: [workerInstruction],
  });

  const withoutFocusedChange = state.removeDebugChange(
    candidate,
    rootBaseline,
  );
  assert.equal(withoutFocusedChange.modelName, rootBaseline.modelName);
  assert.deepEqual(withoutFocusedChange.additionalChanges, [workerInstruction]);

  const withoutStoredChange = state.removeDebugChange(
    candidate,
    change({
      id: "worker:instruction",
      agentKey: "worker",
      dimension: "instruction",
      instruction: "Worker prompt",
    }),
  );
  assert.equal(withoutStoredChange.modelName, "root-candidate");
  assert.deepEqual(withoutStoredChange.additionalChanges, []);
});

test("semantic configuration edits preserve the previous Session evidence", () => {
  const previousSession = variant({
    modelName: "old-model",
    messages: [
      { role: "user", content: "Compare this" },
      { role: "assistant", content: "Previous answer", error: "tool timeout" },
    ],
    ttftMs: 120,
    latencyMs: 840,
    toolCalls: 3,
    tokens: 512,
    error: "Previous environment warning",
    verdict: "采用候选",
    verdictReason: "Previous evidence was stronger",
  });

  const edited = state.updateDebugVariantConfiguration(previousSession, {
    modelName: "new-model",
    messages: [],
    ttftMs: null,
    latencyMs: null,
    toolCalls: null,
    tokens: null,
    error: null,
    verdict: "",
    verdictReason: "",
  });

  assert.equal(edited.modelName, "new-model");
  assert.deepEqual(edited.messages, previousSession.messages);
  assert.equal(edited.ttftMs, 120);
  assert.equal(edited.latencyMs, 840);
  assert.equal(edited.toolCalls, 3);
  assert.equal(edited.tokens, 512);
  assert.equal(edited.error, "Previous environment warning");
  assert.equal(edited.verdict, "采用候选");
  assert.equal(edited.verdictReason, "Previous evidence was stronger");
});
