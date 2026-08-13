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

const comparison = await loadTypeScriptModule(
  "../src/create/comparison/draftComparison.ts",
);

function draft(overrides = {}) {
  return {
    name: "root_agent",
    description: "Root",
    instruction: "Root prompt",
    agentType: "llm",
    modelName: "root-model",
    modelProvider: "openai",
    modelApiBase: "https://models.example.com/v1",
    tools: ["root_tool"],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
    selectedSkills: [],
    ...overrides,
  };
}

test("lists only configurable local LLM agents with stable snapshot paths", () => {
  const source = draft({
    subAgents: [
      draft({ name: "worker" }),
      draft({
        name: "pipeline",
        agentType: "sequential",
        subAgents: [draft({ name: "nested_worker" })],
      }),
      draft({ name: "remote", agentType: "a2a", a2aUrl: "https://a2a.example" }),
    ],
  });

  assert.deepEqual(comparison.listConfigurableAgents(source), [
    { key: "root", path: [], name: "root_agent" },
    { key: "0", path: [0], name: "worker" },
    { key: "1.0", path: [1, 0], name: "nested_worker" },
  ]);
});

test("selects the first configurable child when the root is a collaboration container", () => {
  const source = draft({
    agentType: "sequential",
    subAgents: [
      draft({ name: "researcher", modelName: "researcher-model" }),
      draft({ name: "writer", modelName: "writer-model" }),
    ],
  });

  assert.deepEqual(comparison.firstConfigurableAgent(source), {
    key: "0",
    path: [0],
    name: "researcher",
  });
});

test("builds a candidate from the baseline without changing locked fields", () => {
  const source = draft({
    knowledgebase: true,
    subAgents: [draft({ name: "worker", tools: ["locked_tool"] })],
  });
  const candidate = comparison.buildCandidateDraft(source, [
    {
      agentKey: "root",
      dimensions: ["model"],
      model: {
        modelName: "candidate-model",
        modelProvider: "custom",
        modelApiBase: "https://custom.example.com/v1",
      },
    },
    {
      agentKey: "0",
      dimensions: ["instruction", "skills"],
      instruction: "Candidate worker prompt",
      selectedSkills: [
        {
          source: "skillspace",
          folder: "review",
          name: "Review",
          skillSpaceId: "space-1",
          skillId: "skill-1",
          version: "3",
        },
      ],
    },
  ]);

  assert.equal(candidate.modelName, "candidate-model");
  assert.equal(candidate.modelProvider, "custom");
  assert.equal(candidate.modelApiBase, "https://custom.example.com/v1");
  assert.equal(candidate.instruction, "Root prompt");
  assert.equal(candidate.knowledgebase, true);
  assert.deepEqual(candidate.tools, ["root_tool"]);
  assert.equal(candidate.subAgents[0].instruction, "Candidate worker prompt");
  assert.deepEqual(candidate.subAgents[0].tools, ["locked_tool"]);
  assert.equal(candidate.subAgents[0].selectedSkills[0].version, "3");
  assert.equal(source.modelName, "root-model");
  assert.equal(source.subAgents[0].instruction, "Root prompt");
});

test("filters unchanged dimensions before a comparison can run", () => {
  const source = draft({
    selectedSkills: [
      {
        source: "local",
        folder: "review",
        name: "Review",
      },
    ],
  });
  const unchanged = [
    {
      agentKey: "root",
      dimensions: ["model"],
      model: {
        modelName: "root-model",
        modelProvider: "openai",
        modelApiBase: "https://models.example.com/v1",
      },
    },
    {
      agentKey: "root",
      dimensions: ["instruction"],
      instruction: "Root prompt",
    },
    {
      agentKey: "root",
      dimensions: ["skills"],
      selectedSkills: source.selectedSkills,
    },
  ];

  assert.deepEqual(
    comparison.effectiveComparisonOverrides(source, unchanged),
    [],
  );
  assert.deepEqual(
    comparison.effectiveComparisonOverrides(source, [
      ...unchanged,
      {
        agentKey: "root",
        dimensions: ["instruction"],
        instruction: "Changed prompt",
      },
    ]),
    [
      {
        agentKey: "root",
        dimensions: ["instruction"],
        instruction: "Changed prompt",
      },
    ],
  );
});

test("applies a candidate atomically only while the source snapshot matches", async () => {
  const source = draft({ subAgents: [draft({ name: "worker" })] });
  const fingerprint = await comparison.fingerprintDraft(source);
  const overrides = [
    {
      agentKey: "0",
      dimensions: ["instruction"],
      instruction: "Applied prompt",
    },
  ];

  const applied = await comparison.applyCandidateAtomically(
    source,
    fingerprint,
    overrides,
  );
  assert.equal(applied.ok, true);
  assert.equal(applied.draft.subAgents[0].instruction, "Applied prompt");

  const changedSource = { ...source, description: "edited after comparison" };
  const conflict = await comparison.applyCandidateAtomically(
    changedSource,
    fingerprint,
    overrides,
  );
  assert.deepEqual(conflict, {
    ok: false,
    reason: "当前 Draft 已变化，请基于最新配置重新创建对照。",
  });
  assert.equal(changedSource.subAgents[0].instruction, "Root prompt");
});

test("keeps the Draft unchanged when any candidate node is no longer valid", async () => {
  const source = draft({ subAgents: [draft({ name: "worker" })] });
  const fingerprint = await comparison.fingerprintDraft(source);
  const result = await comparison.applyCandidateAtomically(source, fingerprint, [
    {
      agentKey: "9",
      dimensions: ["instruction"],
      instruction: "must not apply",
    },
  ]);

  assert.deepEqual(result, {
    ok: false,
    reason: "候选配置已失效：Agent path does not exist: 9",
  });
  assert.equal(source.subAgents[0].instruction, "Root prompt");
});
