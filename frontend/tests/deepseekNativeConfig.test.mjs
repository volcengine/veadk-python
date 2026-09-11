import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";
import { build } from "esbuild";
import { parse } from "yaml";

const temp = mkdtempSync(join(tmpdir(), "dsh-config-test-"));
after(() => rmSync(temp, { recursive: true, force: true }));
const compiledPath = join(temp, "native-config.cjs");
await build({
  entryPoints: [fileURLToPath(new URL("../src/create/deepseek/nativeConfig.ts", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", target: "node20", outfile: compiledPath,
});
const { createNativeDraft, validateNativeDraft, nativeConfigFiles, nativeProviderOptions, nativeModelOptions, resolveNativeField, updateNativeField, NATIVE_SECTIONS } = createRequire(import.meta.url)(compiledPath);

function settings(draft) {
  return parse(nativeConfigFiles(draft).find((file) => file.path === "settings.yaml").content);
}

test("container export includes its build inputs and a valid native startup script", () => {
  const files = Object.fromEntries(nativeConfigFiles(createNativeDraft()).map((file) => [file.path, file.content]));
  for (const path of ["Dockerfile", "start.sh", "container.patch.yml", "runtime.mjs", "agentkit.yaml", ".dockerignore", "settings.yaml", ".env.example", "README.md"]) {
    assert.ok(files[path], `Missing export file: ${path}`);
  }
  execFileSync("sh", ["-n"], { input: files["start.sh"] });
  assert.match(files.Dockerfile, /npm install --global @deepseek-ai\/dsh@\d+\.\d+\.\d+/);
  assert.match(files.Dockerfile, /USER node/);
  assert.match(files.Dockerfile, /COPY[^\n]*settings\.yaml container\.patch\.yml/);
  assert.match(files.Dockerfile, /ENTRYPOINT \["\/usr\/bin\/tini", "--", "\/opt\/agent\/start\.sh"\]/);
  assert.match(files.Dockerfile, /COPY[^\n]*start\.sh \/opt\/application\/run\.sh/);
  assert.match(files["start.sh"], /DSH_HOME="\$\{DSH_HOME:-\/home\/node\/\.dsh\}"/);
  assert.match(files["start.sh"], /exec dsh --profile web --patch \/opt\/agent\/container\.patch\.yml --no-open/);
  assert.match(files["start.sh"], /--port 3080/);
  assert.doesNotMatch(files["start.sh"], /--host 0\.0\.0\.0/);
  const patch = parse(files["container.patch.yml"], { customTags: [{ tag: "tag:yaml.org,2002:js", resolve: (value) => value }] });
  assert.equal(patch[0].id, "webserver");
  assert.equal(patch[0].config.host, "127.0.0.1");
  assert.equal(patch[1].insert[0].name, "/opt/agent/runtime.mjs");
  assert.deepEqual(files[".dockerignore"].trim().split("\n"), ["**", "!Dockerfile", "!settings.yaml", "!container.patch.yml", "!start.sh", "!runtime.mjs"]);
  assert.equal(parse(files["agentkit.yaml"]).common.entry_point, "runtime.mjs");
  execFileSync(process.execPath, ["--input-type=module", "--check"], { input: files["runtime.mjs"] });
  assert.equal(files[".env.example"].split("\n").filter((line) => line && !line.startsWith("#")).every((line) => /^[A-Z_][A-Z0-9_]*=$/.test(line)), true);
});

test("prefilled defaults export with native types and remain editable or clearable", () => {
  const draft = createNativeDraft();
  assert.deepEqual(validateNativeDraft(draft), {});
  assert.equal(draft.fields["agent-presets.default"], "standard");
  assert.equal(draft.fields["llm-deepseek.maxTokens"], "256000");
  assert.equal(draft.fields["subagent-model-selection.enabled"], "false");
  assert.deepEqual(settings(draft), {
    "agent-default-model": { provider: "deepseek-official", model: "deepseek-flash" },
    "agent-presets": { default: "standard" },
    permission: { defaultPreset: "workspace-write" },
    "llm-deepseek": {
      apiKeyEnv: "DEEPSEEK_API_KEY", reasoningEffort: "high", maxTokens: 256000,
      defaultContextWindow: 1000000, streamIdleTimeoutMs: 300000,
    },
    bash: { timeoutMs: 60000, maxTimeoutMs: 600000, maxOutputBytes: 64000 },
    "subagent-model-selection": { enabled: false },
    "web-search-deepseek": {
      apiKeyEnv: "DEEPSEEK_API_KEY", model: "deepseek-v4-flash", apiVersion: "2023-06-01",
      maxTokens: 4096, maxUses: 5,
    },
  });
  draft.fields["agent-presets.default"] = "minimal";
  draft.fields["llm-deepseek.maxTokens"] = "";
  assert.equal(settings(draft)["agent-presets"].default, "minimal");
  assert.equal(settings(draft)["llm-deepseek"].maxTokens, undefined);
  assert.equal(createNativeDraft().fields["llm-deepseek.maxTokens"], "256000");
});

test("cloud build defaults follow the active cloud without changing native model settings", () => {
  const draft = createNativeDraft();
  const files = Object.fromEntries(nativeConfigFiles(draft, "byteplus").map(file => [file.path, file.content]));
  assert.equal(parse(files["agentkit.yaml"]).launch_types.cloud.region, "ap-southeast-1");
  assert.match(files.Dockerfile, /DEBIAN_MIRROR=deb\.debian\.org/);
  assert.equal(parse(files["settings.yaml"])["agent-default-model"].provider, "deepseek-official");
});

test("individual overrides retain native inheritance and accept installed custom presets", () => {
  const draft = createNativeDraft();
  draft.fields = {
    "agent-default-model.model": "deepseek-v4-flash",
    "agent-presets.default": "my-installed-preset",
    "subagent-model-selection.enabled": "false",
  };
  assert.deepEqual(settings(draft), {
    "agent-default-model": { model: "deepseek-v4-flash" },
    "agent-presets": { default: "my-installed-preset" },
    "subagent-model-selection": { enabled: false },
  });
});

test("provider selection updates model choices and clears incompatible reasoning", () => {
  for (const provider of ["volcengine", "byteplus"]) {
    let draft = createNativeDraft();
    draft.providers = [{ key: "p", id: provider, displayName: "", baseURL: "https://gateway.example/v1", api: "openai-completions", apiKeyEnv: "KEY", models: [{ key: "m", id: "company-model", name: "", contextWindow: "", maxTokens: "" }] }];
    draft.fields["agent-default-model.reasoningEffort"] = "max";
    assert.deepEqual(nativeProviderOptions(draft), ["deepseek-official", provider]);
    draft = updateNativeField(draft, "agent-default-model.provider", provider);
    assert.equal(draft.fields["agent-default-model.model"], "company-model");
    assert.equal(draft.fields["agent-default-model.reasoningEffort"], "");
    assert.deepEqual(nativeModelOptions(draft, provider), ["company-model"]);
    const effort = NATIVE_SECTIONS[0].fields.find((field) => field.path.endsWith("reasoningEffort"));
    assert.deepEqual(resolveNativeField(draft, effort).options, []);
    assert.deepEqual(settings(draft)["agent-default-model"], { provider, model: "company-model" });
    draft.providers = [];
    assert.ok(validateNativeDraft(draft)["agent-default-model.provider"]);
    assert.equal(validateNativeDraft(draft)["agent-default-model.model"], "unknownProvider");
    draft = updateNativeField(draft, "agent-default-model.provider", "deepseek-official");
    assert.equal(draft.fields["agent-default-model.model"], "deepseek-flash");
    assert.deepEqual(resolveNativeField(draft, effort).options, ["off", "low", "high", "max"]);
  }
});

test("stream idle timers respect the native timer range", () => {
  const draft = createNativeDraft();
  draft.fields["llm-deepseek.streamIdleTimeoutMs"] = "2147483648";
  assert.equal(validateNativeDraft(draft)["llm-deepseek.streamIdleTimeoutMs"], "timer");
});

test("writes the native settings namespaces and scalar types", () => {
  const draft = createNativeDraft();
  draft.fields = {
    "agent-presets.default": "minimal",
    "permission.defaultPreset": "read-only",
    "agent-default-model.provider": "deepseek-official",
    "agent-default-model.model": "deepseek-v4-flash",
    "llm-deepseek.reasoningEffort": "off",
    "llm-deepseek.maxTokens": "8192",
    "bash.timeoutMs": "1500",
    "agent-loop.maxParallelToolCalls": "2",
  };
  assert.deepEqual(settings(draft), {
    "agent-default-model": { provider: "deepseek-official", model: "deepseek-v4-flash" },
    "agent-presets": { default: "minimal" },
    permission: { defaultPreset: "read-only" },
    "llm-deepseek": { reasoningEffort: "off", maxTokens: 8192 },
    bash: { timeoutMs: 1500 },
    "agent-loop": { maxParallelToolCalls: 2 },
  });
});

test("custom providers retain their own protocol and model capabilities", () => {
  for (const providerId of ["volcengine", "byteplus"]) {
    const draft = createNativeDraft();
    draft.providers = [{
      key: "ui-only", id: providerId, displayName: "My gateway",
      baseURL: "https://gateway.example/v1", api: "openai-completions", apiKeyEnv: "MODEL_API_KEY",
      models: [{ key: "model-row", id: "custom-model", name: "Model", contextWindow: "128000", maxTokens: "4096" }],
    }];
    draft.fields["agent-default-model.provider"] = providerId;
    draft.fields["agent-default-model.model"] = "custom-model";
    const native = settings(draft);
    assert.deepEqual(native["llm-pi-ai"].providers[providerId], {
      displayName: "My gateway", baseURL: "https://gateway.example/v1", api: "openai-completions",
      apiKeyEnv: "MODEL_API_KEY", models: [{ id: "custom-model", name: "Model", contextWindow: 128000, maxTokens: 4096 }],
    });
    assert.equal(JSON.stringify(native).includes("ui-only"), false);
    assert.equal(JSON.stringify(native).includes("VeADK"), false);
  }
});

test("invalid numeric edits and unsupported enums block export", () => {
  for (const value of ["0", "-1", "1.5", "Infinity", "9007199254740992", "abc"]) {
    const draft = createNativeDraft();
    draft.fields["agent-loop.maxParallelToolCalls"] = value;
    assert.ok(validateNativeDraft(draft)["agent-loop.maxParallelToolCalls"]);
    assert.throws(() => nativeConfigFiles(draft));
  }
  const draft = createNativeDraft();
  draft.fields["permission.defaultPreset"] = "custom";
  assert.ok(validateNativeDraft(draft)["permission.defaultPreset"]);
});

test("subagent model selection requires nonempty unique provider/model routes", () => {
  const draft = createNativeDraft();
  draft.fields["subagent-model-selection.enabled"] = "true";
  assert.ok(validateNativeDraft(draft)["subagent-model-selection.allowedModels"]);
  draft.allowedModels = [{ key: "a", provider: "deepseek-official", model: "deepseek-flash" }];
  assert.deepEqual(settings(draft)["subagent-model-selection"], {
    enabled: true, allowedModels: [{ provider: "deepseek-official", model: "deepseek-flash" }],
  });
  draft.allowedModels.push({ ...draft.allowedModels[0], key: "b" });
  assert.ok(validateNativeDraft(draft)["subagent-model-selection.allowedModels"]);
});

test("credential references export placeholders and never become literal keys", () => {
  const draft = createNativeDraft();
  draft.fields["llm-deepseek.apiKeyEnv"] = "COMPANY_DEEPSEEK_KEY";
  const files = nativeConfigFiles(draft);
  assert.match(files.find((file) => file.path === ".env.example").content, /COMPANY_DEEPSEEK_KEY=\n/);
  assert.equal(settings(draft)["llm-deepseek"].apiKeyEnv, "COMPANY_DEEPSEEK_KEY");
  draft.fields["llm-deepseek.apiKeyEnv"] = "sk-secret-value";
  assert.ok(validateNativeDraft(draft)["llm-deepseek.apiKeyEnv"]);
  draft.fields["llm-deepseek.baseURL"] = "https://user:password@example.com/v1";
  assert.ok(validateNativeDraft(draft)["llm-deepseek.baseURL"]);
});

test("rejects duplicate provider/model ids and unsafe provider dictionary keys", () => {
  const draft = createNativeDraft();
  const provider = { key: "one", id: "__proto__", displayName: "", baseURL: "https://example.com/v1", api: "openai-completions", apiKeyEnv: "KEY", models: [{ key: "m", id: "m", name: "", contextWindow: "", maxTokens: "" }] };
  draft.providers = [provider];
  assert.ok(validateNativeDraft(draft)["providers.one.id"]);
  provider.id = "company";
  draft.providers.push({ ...provider, key: "two" });
  assert.ok(validateNativeDraft(draft)["providers.two.id"]);
  draft.providers.pop();
  provider.models.push({ ...provider.models[0], key: "m2" });
  assert.equal(validateNativeDraft(draft)["providers.one.models.m2.id"], "duplicate");
});

test("custom model defaults and child selections cannot refer to removed or missing models", () => {
  const draft = createNativeDraft();
  draft.fields = { "agent-default-model.provider": "company", "agent-default-model.model": "missing-model" };
  draft.allowedModels = [{ key: "r", provider: "company", model: "missing-model" }];
  assert.equal(validateNativeDraft(draft)["agent-default-model.model"], "unknownProvider");
  draft.providers = [{ key: "p", id: "company", displayName: "", baseURL: "https://example.com/v1", api: "openai-completions", apiKeyEnv: "KEY", models: [{ key: "m", id: "present-model", name: "", contextWindow: "", maxTokens: "" }] }];
  assert.equal(validateNativeDraft(draft)["agent-default-model.model"], "unknownModel");
  assert.equal(validateNativeDraft(draft)["subagent-model-selection.allowedModels"], "unknownModel");
  draft.fields["agent-default-model.model"] = "present-model";
  draft.allowedModels[0].model = "present-model";
  assert.deepEqual(validateNativeDraft(draft), {});
});
