import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/create/modelApiKeyPresentation.ts", import.meta.url))],
  bundle: true, format: "esm", platform: "node", write: false,
});
const { modelApiKeyDescription, modelApiKeyMatches, modelOptionsWithPermissions } = await import(
  `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`
);

test("granted video and shut-down models appear as disabled model menu options", () => {
  const code = { id: "code-v1", name: "code", displayName: "Code", vendorName: "", available: true, apiKeyAllowed: true, lifecycleStatus: "Retiring", activationState: "Available" };
  const denied = { ...code, id: "other-v1", name: "other", available: false, apiKeyAllowed: false };
  const models = [code, denied];
  const result = modelOptionsWithPermissions(models, [
    { name: "video", modelId: "video-v1", state: "VideoGeneration" },
    { name: "lite", modelId: "lite-v1", state: "Shutdown" },
    { name: "code", modelId: "code-v1", state: "Available" },
    { name: "video-v1", modelId: "video-v1", state: "VideoGeneration" },
  ]);
  assert.deepEqual(result.map((model) => model.id), ["code-v1", "video-v1", "lite-v1", "other-v1"]);
  assert.equal(result[1].unavailableReason, "VideoGeneration");
  assert.equal(result[2].unavailableReason, "Shutdown");
  assert.ok(result.slice(1, 3).every((model) => !model.available && model.apiKeyAllowed));
  assert.deepEqual(models, [code, denied]);
});

test("hundreds of granted non-chat models remain model menu data with stable unique IDs", () => {
  const permissions = Array.from({ length: 300 }, (_, index) => ({ name: `model-${index}`, modelId: `version-${index}`, state: "Shutdown" }));
  const result = modelOptionsWithPermissions([], permissions);
  assert.equal(result.length, 300);
  assert.equal(new Set(result.map((model) => model.id)).size, 300);
  assert.ok(result.every((model) => !model.available && model.unavailableReason === "Shutdown"));
});

for (const locale of ["zh-CN", "en-US"]) {
  const messages = JSON.parse(readFileSync(new URL(`../src/i18n/resources/${locale}/create.json`, import.meta.url), "utf8")).modelApiKey;
  const translate = (key) => messages[key.split(".")[1]];
  test(`${locale}: status and permission subtitles cover every combination`, () => {
    for (const status of ["Active", "Restricted"]) {
      for (const allowAll of [true, false]) {
        const key = { id: "private-id", name: "Production", status, allowAll };
        assert.equal(modelApiKeyDescription(key, translate), `${status === "Active" ? messages.enabled : messages.disabled} · ${allowAll ? messages.allPermissions : messages.customPermissions}`);
      }
    }
    assert.equal(modelApiKeyDescription({ id: "id", name: "Legacy" }, translate), `${messages.unknownStatus} · ${messages.unknownPermissions}`);
  });

  test(`${locale}: search retains matching disabled and custom-permission keys`, () => {
    const keys = [
      { id: "1", name: "Production East", status: "Active", allowAll: true },
      { id: "2", name: "Production West", status: "Active", allowAll: false },
      { id: "3", name: "Production East", status: "Restricted", allowAll: false },
    ];
    const search = (query) => keys.filter((key) => modelApiKeyMatches(query, key.name, modelApiKeyDescription(key, translate))).map((key) => key.id);
    assert.deepEqual(search(""), ["1", "2", "3"]);
    assert.deepEqual(search("  PRODUCTION  "), ["1", "2", "3"]);
    assert.deepEqual(search("ＰＲＯＤＵＣＴＩＯＮ"), ["1", "2", "3"]);
    assert.deepEqual(search(`production ${messages.disabled}`), ["3"]);
    assert.deepEqual(search(messages.customPermissions), ["2", "3"]);
    assert.deepEqual(search("not-present"), []);
  });
}
