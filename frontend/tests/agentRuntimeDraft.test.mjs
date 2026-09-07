import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const require = createRequire(import.meta.url);

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "cjs",
    platform: "node",
    target: "node20",
    write: false,
  });
  const tempDir = mkdtempSync(join(tmpdir(), "veadk-agent-runtime-test-"));
  const modulePath = join(tempDir, "module.cjs");
  writeFileSync(modulePath, result.outputFiles[0].contents);
  return require(modulePath);
}

const { draftToYaml, yamlToDraft } = await loadTypeScriptModule(
  "../src/create/configYaml.ts",
);
const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
);
const { runtimeAgentDraftFromCloud } = await loadTypeScriptModule(
  "../src/create/runtimeModelName.ts",
);

test("agent runtime round-trips through YAML only for non-default LLM nodes", () => {
  const draft = normalizeDraft({
    name: "runtime_root",
    description: "Runtime root",
    instruction: "Coordinate work.",
    agentType: "loop",
    runtime: "codex",
    maxIterations: 3,
    subAgents: [
      {
        name: "coder",
        description: "Writes code",
        instruction: "Edit code.",
        agentType: "llm",
        runtime: "codex",
      },
      {
        name: "reviewer",
        description: "Reviews code",
        instruction: "Review code.",
        agentType: "llm",
        runtime: "piagent",
      },
      {
        name: "summarizer",
        description: "Summarizes",
        instruction: "Summarize.",
        agentType: "llm",
      },
    ],
  });

  assert.equal(draft.runtime, "adk");
  assert.equal(draft.subAgents[0].runtime, "codex");
  assert.equal(draft.subAgents[1].runtime, "piagent");
  assert.equal(draft.subAgents[2].runtime, "adk");

  const yaml = draftToYaml(draft, {
    heading: "Test",
    importHint: "Import again.",
  });
  assert.match(yaml, /runtime: codex/);
  assert.match(yaml, /runtime: piagent/);
  assert.doesNotMatch(yaml, /agentType: loop[\s\S]{0,120}runtime: codex/);
  assert.doesNotMatch(yaml, /name: summarizer[\s\S]{0,120}runtime: adk/);

  const restored = yamlToDraft(yaml);
  assert.equal(restored.runtime, "adk");
  assert.equal(restored.subAgents[0].runtime, "codex");
  assert.equal(restored.subAgents[1].runtime, "piagent");
  assert.equal(restored.subAgents[2].runtime, "adk");
});

test("legacy runtime graph restores LLM agent loop runtime metadata", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "runtime_root",
      graph: {
        name: "runtime_root",
        type: "loop",
        children: [
          {
            name: "coder",
            type: "llm",
            runtime: "codex",
            model: "openai/gpt-5-codex",
            children: [],
          },
          {
            name: "reviewer",
            type: "llm",
            runtime: "piagent",
            model: "openai/gpt-5",
            children: [],
          },
        ],
      },
    },
    "volcengine",
  );

  assert.equal(restored.runtime, "adk");
  assert.equal(restored.subAgents[0].runtime, "codex");
  assert.equal(restored.subAgents[1].runtime, "piagent");
});
