import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
  const directory = mkdtempSync(join(tmpdir(), "veadk-sidecar-test-"));
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
  harnessSidecarProviderNotice,
  harnessProfileDefaultOptimizations,
  releaseDraftFromDebugVariant,
  selectedHarnessModelProxyOptimizations,
} = await loadTypeScriptModule("../src/create/harnessSidecarOptions.ts");
const { draftToYaml, yamlToDraft } = await loadCommonJsTypeScriptModule(
  "../src/create/configYaml.ts",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const harnessOptionsSource = readFileSync(
  new URL("../src/create/harnessSidecarOptions.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);

test("normalizes the five-option intent and derives enabled", () => {
  const draft = normalizeDraft({
    name: "agent",
    harnessSidecar: {
      enabled: false,
      profile: "default",
      componentOverrides: {
        context_engine: true,
        sql_readonly: true,
      },
    },
  });

  assert.equal(draft.harnessSidecar.enabled, true);
  assert.deepEqual(draft.harnessSidecar.componentOverrides, {
    context_engine: true,
    compressor: false,
    verifier: false,
    long_run_control: false,
    mcp_resilience: false,
  });
  assert.equal("sql_readonly" in draft.harnessSidecar.componentOverrides, false);
});

test("normalizes and round-trips the ops profile", () => {
  const draft = normalizeDraft({
    name: "ops-agent",
    harnessSidecar: {
      profile: "ops",
      componentOverrides: {
        context_engine: false,
        compressor: true,
        verifier: false,
        long_run_control: false,
        mcp_resilience: true,
      },
    },
  });

  assert.equal(draft.harnessSidecar.profile, "ops");
  assert.deepEqual(draft.harnessSidecar.componentOverrides, {
    context_engine: true,
    compressor: false,
    verifier: true,
    long_run_control: true,
    mcp_resilience: true,
  });
  const restored = yamlToDraft(draftToYaml(draft));
  assert.equal(restored.harnessSidecar.profile, "ops");
  assert.deepEqual(
    restored.harnessSidecar.componentOverrides,
    draft.harnessSidecar.componentOverrides,
  );
});

test("round-trips selected options in YAML and omits the unselected default", () => {
  const plainYaml = draftToYaml(normalizeDraft({ name: "plain" }));
  assert.doesNotMatch(plainYaml, /harnessSidecar|harness_sidecar/);

  const selected = normalizeDraft({
    name: "selected",
    harnessSidecar: {
      componentOverrides: {
        verifier: true,
        mcp_resilience: true,
      },
    },
  });
  const yaml = draftToYaml(selected);
  const restored = yamlToDraft(yaml);

  assert.equal(restored.harnessSidecar.enabled, true);
  assert.deepEqual(restored.harnessSidecar.componentOverrides, {
    context_engine: false,
    compressor: false,
    verifier: true,
    long_run_control: false,
    mcp_resilience: true,
  });
  assert.doesNotMatch(yaml, /sql_readonly|bytedance-agentkit-harness-sidecar/);
});

test("supports localized YAML header comments", () => {
  const yaml = draftToYaml(normalizeDraft({ name: "localized" }), {
    heading: "VeADK agent structure configuration",
    importHint: "Reload this file from Import YAML on the Create Agent page.",
  });

  assert.match(yaml, /^# VeADK agent structure configuration$/m);
  assert.match(yaml, /^# Reload this file from Import YAML on the Create Agent page\.$/m);
  assert.doesNotMatch(yaml, /[\u3400-\u9fff]/u);
});

test("uses this Studio release's integrated optimization metadata", () => {
  assert.match(harnessOptionsSource, /HARNESS_SIDECAR_OPTIONS/);
  assert.match(harnessOptionsSource, /HARNESS_SIDECAR_OPTION_GROUPS/);
  assert.match(harnessOptionsSource, /HARNESS_SIDECAR_PROFILES/);
  assert.match(harnessOptionsSource, /traditional\.optimization\.profiles\.default\.label/);
  assert.match(harnessOptionsSource, /traditional\.optimization\.profiles\.ops\.label/);
  assert.match(harnessOptionsSource, /traditional\.optimization\.options\.\$\{id\}\.label/);
  assert.match(harnessOptionsSource, /traditional\.optimization\.options\.\$\{id\}\.description/);
  assert.doesNotMatch(customCreateSource, /getHarnessSidecarCatalog/);
  assert.doesNotMatch(customCreateSource, /resolveHarnessSidecarSelection/);
  assert.doesNotMatch(harnessOptionsSource, /sql_readonly\s*:/);
  assert.match(customCreateSource, /function HarnessOptimizationWorkspace/);
  assert.match(customCreateSource, /traditional\.optimization\.scenario/);
  assert.doesNotMatch(customCreateSource, /不启用|value="none"/);
  assert.match(customCreateSource, /traditional\.optimization\.options\.\$\{item\.id\}\.label/);
  assert.match(customCreateSource, /onProfileChange/);
  assert.match(customCreateSource, /harnessProfileDefaultOptimizations/);
});

test("fails fast with a clear BytePlus Sidecar notice without blocking ordinary agents", () => {
  assert.equal(harnessSidecarProviderNotice("volcengine"), null);
  assert.match(
    harnessSidecarProviderNotice("byteplus"),
    /not available/,
  );
  assert.match(
    customCreateSource,
    /providerDraft\.harnessSidecar\?\.enabled && harnessProviderNotice/,
  );
  assert.match(
    customCreateSource,
    /selected && harnessProviderNotice[\s\S]*?setBuildErr\(harnessProviderNotice\)/,
  );
  assert.match(
    customCreateSource,
    /unavailableMessage=\{harnessProviderNotice\}/,
  );
});

test("derives Model Proxy dependencies from the selected optimization catalog", () => {
  const draft = normalizeDraft({
    name: "dependency-agent",
    harnessSidecar: {
      componentOverrides: {
        context_engine: true,
        compressor: false,
        verifier: true,
        long_run_control: false,
        mcp_resilience: true,
      },
    },
  });

  assert.deepEqual(selectedHarnessModelProxyOptimizations(draft), [
    "context_engine",
    "verifier",
  ]);
});

test("places the Harness optimization page immediately before environment setup", () => {
  assert.match(
    customCreateSource,
    /type WorkspaceMode =[\s\S]*?\| "validate"[\s\S]*?\| "optimize"[\s\S]*?\| "environment"[\s\S]*?\| "publish";/,
  );
  assert.match(
    customCreateSource,
    /\{ id: "build", label: "traditional\.workspace\.modes\.build" \},\s*\{ id: "validate", label: "traditional\.workspace\.modes\.validate" \},\s*\{ id: "optimize", label: "traditional\.workspace\.modes\.optimize" \},\s*\{ id: "environment", label: "traditional\.workspace\.modes\.environment" \},\s*\{ id: "publish", label: "traditional\.workspace\.modes\.publish" \}/,
  );
  assert.match(customCreateSource, /optimize:\s*"traditional\.workspace\.titles\.optimize"/);
  assert.doesNotMatch(customCreateSource, /为您的智能体选择一些优化项/);
  assert.ok(
    customCreateSource.indexOf('{workspaceMode === "validate"') <
      customCreateSource.indexOf('{workspaceMode === "optimize"'),
  );
  assert.ok(
    customCreateSource.indexOf('{workspaceMode === "optimize"') <
      customCreateSource.indexOf('{workspaceMode === "environment"'),
  );
  assert.match(
    customCreateSource,
    /const handleWorkspaceChange = async[\s\S]*?nextMode === "optimize"[\s\S]*?openOptimization\(\)/,
  );
});

test("materializes an ordinary project snapshot into one ops release draft", () => {
  const ordinaryDraft = normalizeDraft({
    name: "ordinary-agent",
    description: "ordinary description",
    instruction: "ordinary instruction",
    harnessSidecar: {
      profile: "ops",
      componentOverrides: Object.fromEntries(
        harnessProfileDefaultOptimizations("ops").map((id) => [id, true]),
      ),
    },
  });
  const selectedVariant = {
    modelName: "doubao-seed-1-6-250615",
    description: "ops description",
    instruction: "ops instruction",
  };

  const releaseDraft = releaseDraftFromDebugVariant(
    ordinaryDraft,
    selectedVariant,
  );

  assert.equal(releaseDraft.description, selectedVariant.description);
  assert.equal(releaseDraft.instruction, selectedVariant.instruction);
  assert.equal(releaseDraft.harnessSidecar.profile, "ops");
  assert.deepEqual(releaseDraft.harnessSidecar.componentOverrides, {
    context_engine: true,
    compressor: false,
    verifier: true,
    long_run_control: true,
    mcp_resilience: true,
  });
  assert.match(
    customCreateSource,
    /const materializePublishRelease = async[\s\S]*?releaseDraftFromDebugVariant\(providerDraft, releaseVariant\)[\s\S]*?generateAgentProject\(codegenDraft\(releaseDraft\)\)[\s\S]*?setDraft\(releaseDraft\)[\s\S]*?setProject\(generated\)/,
  );
  assert.match(
    customCreateSource,
    /const openOptimization = async[\s\S]*?setWorkspaceMode\("optimize"\)/,
  );
  assert.match(
    customCreateSource,
    /const handleWorkspaceChange = async[\s\S]*?nextMode === "publish"[\s\S]*?materializePublishRelease\(\)/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /if \(project\) setWorkspaceMode\("publish"\)/,
  );
  assert.match(
    customCreateSource,
    /description: draft\.description,[\s\S]*?harnessSidecar: draft\.harnessSidecar/,
  );
});

test("preserves the ordinary zero-component release draft", () => {
  const ordinaryDraft = normalizeDraft({
    name: "ordinary-agent",
    description: "ordinary description",
    instruction: "ordinary instruction",
  });
  const releaseDraft = releaseDraftFromDebugVariant(ordinaryDraft, {
    modelName: ordinaryDraft.modelName,
    description: ordinaryDraft.description,
    instruction: ordinaryDraft.instruction,
  });

  assert.equal(releaseDraft.harnessSidecar, undefined);
});

test("carries the selected variant into debug generation and deployment", () => {
  assert.match(
    customCreateSource,
    /const updateHarnessOptimization = \([\s\S]*?harnessSidecar: harnessIntentFromOptimizations\(/,
  );
  assert.doesNotMatch(customCreateSource, /harnessSidecar: undefined/);
  assert.match(clientSource, /body: JSON\.stringify\(\{\s*draft,/);
  assert.match(clientSource, /harnessSidecar: opts\?\.harnessSidecar/);
  assert.match(
    customCreateSource,
    /description: draft\.description,[\s\S]*?harnessSidecar: draft\.harnessSidecar/,
  );
  assert.match(configYamlSource, /harnessSidecar/);
});

test("marks a running variant stale when the draft optimization selection changes", () => {
  assert.match(
    customCreateSource,
    /const currentDebugSnapshot = useMemo\([\s\S]*?debugSnapshotKey\(providerDraft/,
  );
  assert.match(
    customCreateSource,
    /const stale = Boolean\([\s\S]*?runtimeSnapshot !==[\s\S]*?debugVariantSnapshot\(draftSnapshot, variant\)/,
  );
  assert.match(customCreateSource, /traditional\.debug\.configurationChanged/);
});

test("applies scenario defaults while allowing an empty custom selection", () => {
  assert.match(
    customCreateSource,
    /const updateHarnessOptimizationProfile = \([\s\S]*?harnessProfileDefaultOptimizations\(profile\)/,
  );
  assert.doesNotMatch(customCreateSource, /!harnessOptimizationProfile/);
  assert.match(harnessOptionsSource, /traditional\.optimization\.profiles\.default\.description/);
  assert.match(customCreateSource, /traditional\.optimization\.releaseScenario/);
  assert.match(
    customCreateSource,
    /harnessOptimizations\.map\(\(id\) =>\s*t\(`traditional\.optimization\.options\.\$\{id\}\.label`\)/,
  );
  assert.match(
    customCreateSource,
    /harnessOptimizationProfile === "ops"\s*\? "default"\s*: harnessOptimizationProfile/,
  );
});

test("treats checkbox changes as metadata and defers checks to runtime actions", () => {
  assert.match(
    customCreateSource,
    /const updateHarnessOptimization = \([\s\S]*?setDraft\(\(current\) =>/,
  );
  assert.doesNotMatch(customCreateSource, /resolveHarnessOptimizationPlan/);
  assert.doesNotMatch(customCreateSource, /harnessCatalogLoading/);
  assert.match(
    customCreateSource,
    /createdRun = await createGeneratedAgentTestRun\(/,
  );
  assert.match(
    clientSource,
    /harnessSidecar: opts\?\.harnessSidecar/,
  );
});
