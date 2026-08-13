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

const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);

function draft(deployment) {
  return {
    name: "root-agent",
    description: "runtime name persistence",
    instruction: "echo",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
    deployment,
  };
}

test("treats an older explicit Runtime name as customized", () => {
  const imported = normalizeDraft(
    draft({ feishuEnabled: false, runtimeName: "legacy-runtime" }),
  );
  assert.equal(imported.deployment.runtimeName, "legacy-runtime");
  assert.equal(imported.deployment.runtimeNameCustomized, true);
});

test("exports the customized Runtime name marker through YAML", () => {
  assert.match(
    configYamlSource,
    /draft\.deployment\?\.runtimeNameCustomized/,
  );
  assert.match(
    configYamlSource,
    /deployment\.runtimeNameCustomized = true/,
  );
});

test("preserves an explicitly cleared Runtime name for inline validation", () => {
  const imported = normalizeDraft(draft({
    feishuEnabled: false,
    runtimeName: "",
    runtimeNameCustomized: true,
  }));
  assert.equal(imported.deployment.runtimeName, "");
  assert.equal(imported.deployment.runtimeNameCustomized, true);
});
