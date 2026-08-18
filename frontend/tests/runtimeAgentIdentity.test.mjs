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

const { applyRuntimeAgentIntrospection } = await loadTypeScriptModule(
  "../src/create/runtimeModelName.ts",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const workspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
  "utf8",
);

function cachedRuntimeDraft(name) {
  return {
    name,
    agentType: "llm",
    modelName: "saved-model",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
  };
}

test("deployed Agent identity overrides a cached Runtime resource name", () => {
  const restored = applyRuntimeAgentIntrospection(
    cachedRuntimeDraft("customer-agent-a1b2c3"),
    undefined,
    { name: "customer_agent" },
  );

  assert.equal(restored.name, "customer_agent");
});

test("Runtime update entry always passes the live-hydrated draft through the update handler", () => {
  const clickStart = workspaceSource.indexOf("onClick={() =>\n                      selectedDraft");
  const clickEnd = workspaceSource.indexOf("                    }\n                  >", clickStart);
  assert.ok(clickStart >= 0 && clickEnd > clickStart);
  const clickHandler = workspaceSource.slice(clickStart, clickEnd);

  assert.match(clickHandler, /onUpdateAgent\(draft, selectedUpdateCapability\)/);
  assert.doesNotMatch(clickHandler, /selectedAgentUpdateDraft[\s\S]*?onEditDraft/);
});

test("Runtime update hydration applies deployed introspection before opening the builder", () => {
  const handlerStart = appSource.indexOf(
    "onUpdateAgent={async (nextDraft, capability) =>",
  );
  const handlerEnd = appSource.indexOf("onEditDraft=", handlerStart);
  assert.ok(handlerStart >= 0 && handlerEnd > handlerStart);
  const handler = appSource.slice(handlerStart, handlerEnd);

  assert.match(
    handler,
    /applyRuntimeAgentIntrospection\([\s\S]*?nextDraft,[\s\S]*?capability\.agent\?\.graph/,
  );
  assert.match(handler, /setImportedDraft\(classifiedDraft\)/);
});
