import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
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

async function loadCommonJsTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "cjs",
    platform: "node",
    target: "node20",
    write: false,
  });
  const directory = mkdtempSync(join(tmpdir(), "veadk-model-fallback-test-"));
  const bundle = join(directory, "module.cjs");
  try {
    writeFileSync(bundle, result.outputFiles[0].contents);
    return createRequire(import.meta.url)(bundle);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
);
const {
  modelFallbackApiKeyEnv,
  nextModelFallbackApiKeyEnv,
  normalizeModelFallbacks,
} = await loadTypeScriptModule(
  "../src/create/modelFallbacks.ts",
);
const { isValidModelApiBaseUrl } = await loadTypeScriptModule(
  "../src/create/modelApiBase.ts",
);
const { draftToYaml, yamlToDraft } = await loadCommonJsTypeScriptModule(
  "../src/create/configYaml.ts",
);

test("normalizes same-provider model fallback order", () => {
  assert.deepEqual(
    normalizeModelFallbacks("primary-model", [
      " fallback-a ",
      "",
      "primary-model",
      "fallback-b",
      "fallback-a",
    ]),
    ["fallback-a", "fallback-b"],
  );
});

test("validates custom model API base URLs", () => {
  assert.equal(isValidModelApiBaseUrl(""), true);
  assert.equal(isValidModelApiBaseUrl("https://api.example.com/v1"), true);
  assert.equal(isValidModelApiBaseUrl("http://localhost:11434/v1"), true);
  assert.equal(isValidModelApiBaseUrl("api.example.com/v1"), false);
  assert.equal(isValidModelApiBaseUrl("ftp://api.example.com/v1"), false);
  assert.equal(isValidModelApiBaseUrl("https://user:pass@example.com/v1"), false);
});

test("normalizes cross-provider model fallback endpoints", () => {
  assert.deepEqual(
    normalizeModelFallbacks("primary-model", [
      "fallback-a",
      {
        model: " gpt-4o-mini ",
        provider: " openai ",
        api_base: " https://api.openai.com/v1 ",
        api_key_env: " OPENAI_BACKUP_API_KEY ",
      },
      {
        modelName: "gpt-4o-mini",
        modelProvider: "openai",
        modelApiBase: "https://api.openai.com/v1",
        modelApiKeyEnv: "OPENAI_BACKUP_API_KEY",
      },
    ]),
    [
      "fallback-a",
      {
        modelName: "gpt-4o-mini",
        modelProvider: "openai",
        modelApiBase: "https://api.openai.com/v1",
        modelApiKeyEnv: "OPENAI_BACKUP_API_KEY",
      },
    ],
  );
});

test("allocates stable cross-provider fallback API key env names", () => {
  const fallbacks = [
    "same-provider-backup",
    {
      modelName: "gpt-4o-mini",
      modelProvider: "openai",
      modelApiKeyEnv: "OPENAI_BACKUP_API_KEY",
    },
  ];

  assert.equal(
    nextModelFallbackApiKeyEnv("Agent", 2, fallbacks),
    "FALLBACK_MODEL_AGENT_3_API_KEY",
  );
  assert.equal(
    modelFallbackApiKeyEnv("Agent", 1, fallbacks, fallbacks[1]),
    "OPENAI_BACKUP_API_KEY",
  );
  assert.equal(
    modelFallbackApiKeyEnv("Agent", 1, fallbacks, {
      modelName: "claude-3-haiku",
      modelProvider: "anthropic",
      modelApiKeyEnv: "bad key",
    }),
    "FALLBACK_MODEL_AGENT_2_API_KEY",
  );
});

test("imports modelName arrays as primary plus fallback models", () => {
  const draft = normalizeDraft({
    name: "fallback-agent",
    modelName: ["primary-model", "fallback-a", "fallback-b"],
    modelFallbacks: ["fallback-c"],
  });

  assert.equal(draft.modelName, "primary-model");
  assert.deepEqual(draft.modelFallbacks, [
    "fallback-a",
    "fallback-b",
    "fallback-c",
  ]);
});

test("round-trips modelFallbacks through YAML", () => {
  const draft = normalizeDraft({
    name: "fallback-agent",
    modelName: "primary-model",
    modelFallbacks: [" fallback-a ", "primary-model", "fallback-b"],
  });
  const yaml = draftToYaml(draft);
  const restored = yamlToDraft(yaml);

  assert.match(yaml, /modelFallbacks:/);
  assert.match(yaml, /- fallback-a/);
  assert.deepEqual(restored.modelFallbacks, ["fallback-a", "fallback-b"]);
});

test("round-trips cross-provider fallback endpoints through YAML without secrets", () => {
  const draft = normalizeDraft({
    name: "fallback-agent",
    modelName: "primary-model",
    modelFallbacks: [
      "fallback-a",
      {
        modelName: "gpt-4o-mini",
        modelProvider: "openai",
        modelApiBase: "https://api.openai.com/v1",
        modelApiKeyEnv: "OPENAI_BACKUP_API_KEY",
      },
    ],
  });
  const yaml = draftToYaml(draft);
  const restored = yamlToDraft(yaml);

  assert.match(yaml, /modelProvider: openai/);
  assert.match(yaml, /modelApiKeyEnv: OPENAI_BACKUP_API_KEY/);
  assert.doesNotMatch(yaml, /modelApiKey:/);
  assert.deepEqual(restored.modelFallbacks, [
    "fallback-a",
    {
      modelName: "gpt-4o-mini",
      modelProvider: "openai",
      modelApiBase: "https://api.openai.com/v1",
      modelApiKeyEnv: "OPENAI_BACKUP_API_KEY",
    },
  ]);
});
