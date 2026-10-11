import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

async function load(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true, format: "cjs", platform: "node", target: "node20", write: false,
  });
  const directory = mkdtempSync(join(tmpdir(), "veadk-context-draft-"));
  try {
    const path = join(directory, "module.cjs");
    writeFileSync(path, result.outputFiles[0].contents);
    return createRequire(import.meta.url)(path);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

const { emptyDraft } = await load("../src/create/types.ts");
const { normalizeDraft } = await load("../src/create/normalizeDraft.ts");
const { draftToYaml, yamlToDraft } = await load("../src/create/configYaml.ts");

test("new drafts default to auto without enabling a sidecar", () => {
  for (const provider of ["volcengine", "byteplus"]) {
    const draft = emptyDraft(provider);
    assert.deepEqual(draft.contextCompression, { mode: "auto" });
    assert.ok(!draft.harnessSidecar?.enabled);
  }
});

test("missing policies on root and nested drafts default to auto through save and YAML", () => {
  const draft = normalizeDraft({ name: "legacy", subAgents: [{ name: "child" }] });
  for (const restored of [draft, normalizeDraft(JSON.parse(JSON.stringify(draft))), yamlToDraft(draftToYaml(draft))]) {
    assert.deepEqual(restored.contextCompression, { mode: "auto" });
    assert.deepEqual(restored.subAgents[0].contextCompression, { mode: "auto" });
  }
});

test("explicit modes and capacity survive copy, save, and nested YAML", () => {
  const policy = { mode: "auto", context_window: 32000, input_limit: 24000, output_reserve: 4000, trigger_ratio: 0.75, summary_trigger_ratio: 0.9, target_ratio: 0.5 };
  const root = { ...emptyDraft(), name: "root", contextCompression: policy,
    subAgents: [{ ...emptyDraft(), name: "child", contextCompression: { mode: "off", context_window: 16000 } }] };
  for (const restored of [normalizeDraft(JSON.parse(JSON.stringify(root))), yamlToDraft(draftToYaml(root))]) {
    assert.deepEqual(restored.contextCompression, policy);
    assert.deepEqual(restored.subAgents[0].contextCompression, root.subAgents[0].contextCompression);
  }
  root.contextCompression.context_window = 12345;
  assert.equal(policy.context_window, 12345);
  assert.deepEqual(emptyDraft().contextCompression, { mode: "auto" });
});

test("invalid compression input is rejected rather than silently disabled", () => {
  for (const policy of ["auto", null, { mode: "other" }, { mode: "auto", context_window: -1 },
    { mode: "auto", output_reserve: 1.5 }, { mode: "auto", context_window: "32000" },
    { mode: "auto", context_window: true }, { mode: "auto", unknown: 1 }]) {
    assert.throws(() => normalizeDraft({ contextCompression: policy }), /contextCompression/);
  }
});

for (const policy of [
  { trigger_ratio: 0 }, { target_ratio: 0.9 }, { trigger_ratio: 0.96 },
  { trigger_ratio: "0.8" }, { target_ratio: true }, { summary_trigger_ratio: Infinity },
  { target_ratio: 0.8, trigger_ratio: 0.8 },
]) {
  test(`reject invalid thresholds ${JSON.stringify(policy)}`, () => {
    assert.throws(() => normalizeDraft({ contextCompression: { mode: "auto", ...policy } }), /contextCompression/);
  });
}


test("generated model placeholder has a reviewed capacity", async () => {
  const { MODEL_ENV } = await load("../src/create/veadkCatalog.ts");
  const model = MODEL_ENV.find((item) => item.key === "MODEL_AGENT_NAME").placeholder;
  const config = JSON.parse(readFileSync(new URL("../../veadk/context/model_capacities.json", import.meta.url), "utf8"));
  assert.ok(config.models.some((row) => row.model_id === model), `Missing capacity: ${model}`);
});
