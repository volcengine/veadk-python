import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

const {
  hydrateRuntimeModelSelection,
  isRuntimeModelSelectionEnv,
  resolvedModelSource,
} = await loadTypeScriptModule("../src/create/modelSource.ts");
const {
  applyRuntimeAgentIntrospection,
  classifyRuntimeModelSources,
  modelConfigurationFromRuntime,
  modelNameFromRuntime,
} = await loadTypeScriptModule("../src/create/runtimeModelName.ts");

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const runtimeModelNameSource = readFileSync(
  new URL("../src/create/runtimeModelName.ts", import.meta.url),
  "utf8",
);

function draft(overrides = {}) {
  return {
    name: "agent",
    agentType: "llm",
    modelName: "saved-model",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
    ...overrides,
  };
}

test("splits provider-qualified runtime model names at the first slash", () => {
  assert.equal(modelNameFromRuntime("openai/saved-model"), "saved-model");
  assert.equal(modelNameFromRuntime("saved-model"), "saved-model");
  assert.equal(modelNameFromRuntime(undefined), "");
  assert.deepEqual(modelConfigurationFromRuntime("anthropic/claude-sonnet"), {
    modelName: "claude-sonnet",
    modelProvider: "anthropic",
  });
  assert.deepEqual(modelConfigurationFromRuntime("openrouter/meta/llama"), {
    modelName: "meta/llama",
    modelProvider: "openrouter",
  });
});

test("hydrates a legacy runtime model name without changing its provider", () => {
  const restored = hydrateRuntimeModelSelection(
    draft({
      modelName: "openai/saved-model",
      modelSource: "custom",
      modelProvider: "openai",
      modelApiBase: "https://models.example.com/v1",
    }),
    [],
  );

  assert.equal(restored.modelName, "saved-model");
  assert.equal(restored.modelProvider, "openai");
  assert.equal(restored.modelSource, "custom");
});

test("uses the provider prefix from the live Runtime model", () => {
  const restored = hydrateRuntimeModelSelection(
    draft({
      modelName: "openrouter/meta/llama",
      modelSource: "custom",
      modelProvider: "openai",
      modelApiBase: "https://models.example.com/v1",
    }),
    [],
  );

  assert.equal(restored.modelName, "meta/llama");
  assert.equal(restored.modelProvider, "openrouter");
  assert.equal(restored.modelSource, "custom");
});

test("uses deployed Agent introspection instead of cached draft identity", () => {
  const restored = applyRuntimeAgentIntrospection(
    draft({
      name: "runtime-name-with-suffix-a1b2c3",
      modelName: "",
      modelProvider: "stale-provider",
      subAgents: [draft({ name: "child", modelName: "" })],
    }),
    {
      name: "agent-name",
      model: "openai/root-model",
      children: [{ model: "openrouter/meta/child-model" }],
    },
  );

  assert.equal(restored.name, "agent-name");
  assert.equal(restored.modelName, "root-model");
  assert.equal(restored.modelProvider, "openai");
  assert.equal(restored.subAgents[0].modelName, "meta/child-model");
  assert.equal(restored.subAgents[0].modelProvider, "openrouter");
});

test("classifies Runtime models only by ModelArk catalog membership", () => {
  const matched = classifyRuntimeModelSources(
    draft({
      modelName: "doubao-seed-2-1-pro-260628",
      modelSource: "custom",
    }),
    new Set(["doubao-seed-2-1-pro-260628"]),
  );
  const unmatched = classifyRuntimeModelSources(
    draft({
      modelName: "private-model",
      modelSource: "ark",
      modelProvider: "custom-provider",
    }),
    new Set(["doubao-seed-2-1-pro-260628"]),
  );

  assert.equal(matched.modelSource, "ark");
  assert.equal(unmatched.modelSource, "custom");
  assert.equal(unmatched.modelProvider, "custom-provider");
});

test("keeps a legacy runtime custom while restoring its model configuration", () => {
  const restored = hydrateRuntimeModelSelection(
    draft({
      modelName: "anthropic/saved-model",
      modelSource: undefined,
      modelProvider: "",
      modelApiBase: "",
    }),
    [],
  );

  assert.equal(restored.modelSource, "custom");
  assert.equal(restored.modelName, "saved-model");
  assert.equal(restored.modelProvider, "anthropic");
});

test("restores a saved ModelArk API Key and keeps the saved model selection", () => {
  const restored = hydrateRuntimeModelSelection(
    draft({
      modelSource: "ark",
      deployment: {
        modelApiKeyId: "saved-id",
        modelApiKeyName: "saved-key",
      },
    }),
    [
      { key: "MODEL_AGENT_API_KEY_ID", value: "runtime-id" },
      { key: "MODEL_AGENT_API_KEY_NAME", value: "runtime-key" },
    ],
  );

  assert.equal(restored.modelSource, "ark");
  assert.equal(restored.modelName, "saved-model");
  assert.equal(restored.deployment.modelApiKeyId, "saved-id");
  assert.equal(restored.deployment.modelApiKeyName, "saved-key");
});

test("fills a missing saved Key name only when the Runtime ID is the same", () => {
  const matching = hydrateRuntimeModelSelection(
    draft({ modelSource: "ark", deployment: { modelApiKeyId: "same-id" } }),
    [
      { key: "MODEL_AGENT_API_KEY_ID", value: "same-id" },
      { key: "MODEL_AGENT_API_KEY_NAME", value: "matching-key" },
    ],
  );
  const mismatched = hydrateRuntimeModelSelection(
    draft({ modelSource: "ark", deployment: { modelApiKeyId: "saved-id" } }),
    [
      { key: "MODEL_AGENT_API_KEY_ID", value: "different-id" },
      { key: "MODEL_AGENT_API_KEY_NAME", value: "different-key" },
    ],
  );

  assert.equal(matching.deployment.modelApiKeyName, "matching-key");
  assert.equal(mismatched.deployment.modelApiKeyId, "saved-id");
  assert.equal(mismatched.deployment.modelApiKeyName, "");
});

test("uses an ID marker to recognize a legacy ModelArk runtime", () => {
  const restored = hydrateRuntimeModelSelection(
    draft({ modelProvider: "openai", modelApiBase: "https://ark.example/v3" }),
    [
      { key: "MODEL_AGENT_API_KEY_ID", value: "ark-key-id" },
      { key: "MODEL_AGENT_API_KEY_NAME", value: "production-key" },
    ],
  );

  assert.equal(restored.modelSource, "ark");
  assert.equal(restored.modelName, "saved-model");
  assert.equal(restored.modelProvider, "openai");
  assert.equal(restored.modelApiBase, "https://ark.example/v3");
  assert.equal(restored.deployment.modelApiKeyId, "ark-key-id");
  assert.equal(restored.deployment.modelApiKeyName, "production-key");
});

test("does not let stale runtime markers override an explicit custom model", () => {
  const restored = hydrateRuntimeModelSelection(
    draft({
      modelSource: "custom",
      modelProvider: "openai",
      modelApiBase: "https://models.example.com/v1",
    }),
    [
      { key: "MODEL_AGENT_API_KEY_ID", value: "stale-id" },
      { key: "MODEL_AGENT_API_KEY_NAME", value: "stale-name" },
    ],
  );

  assert.equal(restored.modelSource, "custom");
  assert.equal(restored.modelName, "saved-model");
  assert.equal(restored.modelProvider, "openai");
  assert.equal(restored.modelApiBase, "https://models.example.com/v1");
});

test("keeps legacy hand-written models custom when there is no ID marker", () => {
  const legacy = draft({
    modelProvider: "openai",
    modelApiBase: "https://models.example.com/v1",
  });
  const restored = hydrateRuntimeModelSelection(legacy, [
    { key: "MODEL_AGENT_API_KEY_NAME", value: "legacy-default-name" },
  ]);

  assert.equal(restored.modelSource, "custom");
  assert.equal(resolvedModelSource(legacy, "volcengine"), "custom");
  assert.equal(restored.modelName, "saved-model");
  assert.equal(restored.modelProvider, "openai");
  assert.equal(
    restored.modelApiBase,
    "https://models.example.com/v1",
  );
});

test("keeps the official endpoint fallback compatible with older Ark drafts", () => {
  const legacyArk = draft({
    modelProvider: "openai",
    modelApiBase: "https://ark.cn-beijing.volces.com/api/v3/",
  });
  const restored = hydrateRuntimeModelSelection(legacyArk, []);

  assert.equal(resolvedModelSource(legacyArk, "volcengine"), "ark");
  assert.equal(restored.modelSource, "ark");
});

test("restores BytePlus Ark selections without misclassifying legacy custom models", () => {
  const bytePlusArk = draft({
    cloudProvider: "byteplus",
    modelApiBase: "https://ark.ap-southeast.bytepluses.com/api/v3",
  });
  const restoredArk = hydrateRuntimeModelSelection(bytePlusArk, [
    { key: "MODEL_AGENT_API_KEY_ID", value: "byteplus-key-id" },
    { key: "MODEL_AGENT_API_KEY_NAME", value: "byteplus-key" },
  ]);
  const bytePlusCustom = draft({
    cloudProvider: "byteplus",
    modelProvider: "openai",
    modelApiBase: "https://models.byteplus.example/v1",
  });
  const restoredCustom = hydrateRuntimeModelSelection(bytePlusCustom, []);

  assert.equal(restoredArk.modelSource, "ark");
  assert.equal(restoredArk.modelName, "saved-model");
  assert.equal(restoredArk.deployment.modelApiKeyId, "byteplus-key-id");
  assert.equal(restoredArk.deployment.modelApiKeyName, "byteplus-key");
  assert.equal(resolvedModelSource(bytePlusArk, "byteplus"), "ark");
  assert.equal(restoredCustom.modelSource, "custom");
  assert.equal(restoredCustom.modelName, "saved-model");
  assert.equal(restoredCustom.modelProvider, "openai");
  assert.equal(
    restoredCustom.modelApiBase,
    "https://models.byteplus.example/v1",
  );
});

test("hydrates Runtime updates through safe selection metadata", () => {
  assert.match(appSource, /hydrateRuntimeModelSelection\(/);
  assert.match(
    appSource,
    /capability\.runtime\.envs[\s\S]*?filter\(\(\{ key \}\) => !isRuntimeModelSelectionEnv\(key\)\)/,
  );
  assert.equal(isRuntimeModelSelectionEnv("MODEL_AGENT_API_KEY"), true);
  assert.equal(isRuntimeModelSelectionEnv("MODEL_AGENT_API_KEY_ID"), true);
  assert.equal(isRuntimeModelSelectionEnv("MODEL_AGENT_API_KEY_NAME"), true);
  assert.equal(isRuntimeModelSelectionEnv("SAFE_SETTING"), false);
});

test("legacy capability fallbacks do not inherit the new-draft Ark default", () => {
  const fallbackOverrides = runtimeModelNameSource.match(/modelSource: undefined/g) ?? [];
  assert.equal(fallbackOverrides.length, 2);
});

test("the picker restores by ID or name and deploys the current selection", () => {
  assert.match(
    customCreateSource,
    /response\.keys\.find\(\(key\) => key\.id === apiKeyId\)\s*\?\?\s*response\.keys\.find\(\(key\) => key\.name === apiKeyName\)/,
  );
  assert.match(customCreateSource, /modelApiKeyId: key\.id/);
  assert.match(customCreateSource, /modelApiKeyName: key\.name/);
  assert.match(
    projectPreviewSource,
    /agentDraft\.deployment\?\.modelApiKeyId\?\.trim\(\)[\s\S]*?byKey\.set\("MODEL_AGENT_API_KEY_ID", apiKeyId\)/,
  );
  assert.match(
    projectPreviewSource,
    /agentDraft\.deployment\?\.modelApiKeyName\?\.trim\(\)[\s\S]*?byKey\.set\("MODEL_AGENT_API_KEY_NAME", apiKeyName\)/,
  );
});

test("legacy custom Runtime secrets move into transient UI state", () => {
  assert.match(
    customCreateSource,
    /customModelSecretValues = Object\.fromEntries\([\s\S]*?secretKeys\.has\(key\)/,
  );
  assert.match(
    customCreateSource,
    /envValues: Object\.fromEntries\([\s\S]*?!secretKeys\.has\(key\)/,
  );
  assert.match(
    customCreateSource,
    /useState<\s*Record<string, string>\s*>\(initialState\.customModelSecretValues\)/,
  );
});
