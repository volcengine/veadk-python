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
  applyRuntimeAgentIntrospection,
  hydrateA2aRegistryFromRuntime,
  runtimeAgentDraftFromCloud,
} = await loadTypeScriptModule("../src/create/runtimeModelName.ts");
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

test("deployed Runtime configuration is rebuilt only from cloud data", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "cloud_app",
      name: "cloud_agent",
      model: "openai/cloud-model",
      draft: {
        ...cachedRuntimeDraft("cloud_draft_name"),
        description: "cloud description",
        instruction: "cloud instruction",
        builtinTools: ["web_search"],
        mcpTools: [
          {
            name: "cloud-mcp",
            transport: "http",
            url: "https://mcp.example.com",
          },
        ],
        memory: { shortTerm: true, longTerm: true },
        shortTermBackend: "redis",
        longTermBackend: "viking",
        knowledgebase: true,
        knowledgebaseBackend: "viking",
        knowledgebaseIndex: "cloud-index",
        tracing: true,
        tracingExporters: ["tls"],
      },
    },
    "volcengine",
  );

  assert.equal(restored.name, "cloud_agent");
  assert.equal(restored.description, "cloud description");
  assert.equal(restored.instruction, "cloud instruction");
  assert.equal(restored.modelName, "cloud-model");
  assert.equal(restored.modelProvider, "openai");
  assert.deepEqual(restored.builtinTools, ["web_search"]);
  assert.equal(restored.mcpTools[0].name, "cloud-mcp");
  assert.deepEqual(restored.memory, { shortTerm: true, longTerm: true });
  assert.equal(restored.shortTermBackend, "redis");
  assert.equal(restored.longTermBackend, "viking");
  assert.equal(restored.knowledgebase, true);
  assert.equal(restored.knowledgebaseIndex, "cloud-index");
  assert.equal(restored.tracing, true);
  assert.deepEqual(restored.tracingExporters, ["tls"]);
});

test("Agent name uses only cloud graph, metadata, then app name", () => {
  const fromGraph = runtimeAgentDraftFromCloud(
    {
      appName: "cloud_app",
      name: "cloud_metadata_name",
      graph: { name: "cloud_graph_name", children: [] },
      draft: cachedRuntimeDraft("cloud_snapshot_name"),
    },
    "volcengine",
  );
  const fromMetadata = runtimeAgentDraftFromCloud(
    { appName: "cloud_app", name: "cloud_metadata_name" },
    "volcengine",
  );
  const fromAppName = runtimeAgentDraftFromCloud(
    { appName: "cloud_app" },
    "volcengine",
  );

  assert.equal(fromGraph.name, "cloud_graph_name");
  assert.equal(fromMetadata.name, "cloud_metadata_name");
  assert.equal(fromAppName.name, "cloud_app");
});

test("nullable fields from older cloud snapshots are normalized at the boundary", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "legacy_app",
      draft: {
        ...cachedRuntimeDraft("legacy_agent"),
        description: "legacy description",
        instruction: "legacy instruction",
        memory: { shortTerm: null, longTerm: null },
        a2aUrl: null,
        modelSource: null,
        cloudEnvironment: { cliTools: ["lark-cli"], dockerfile: null },
        deployment: {
          feishuEnabled: false,
          runtimeName: null,
          modelApiKeyId: null,
          modelApiKeyName: null,
        },
      },
    },
    "volcengine",
  );

  assert.deepEqual(restored.memory, { shortTerm: false, longTerm: false });
  assert.equal(restored.a2aUrl, "");
  assert.equal(restored.modelSource, undefined);
  assert.deepEqual(restored.cloudEnvironment.cliTools, ["lark-cli"]);
  assert.equal(restored.cloudEnvironment.dockerfile, undefined);
  assert.equal(restored.deployment.runtimeName, undefined);
  assert.equal(restored.deployment.modelApiKeyId, "");
  assert.equal(restored.deployment.modelApiKeyName, "");
});

test("legacy Runtime graph uses cloud values and defaults for unavailable fields", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "legacy_app",
      graph: {
        name: "legacy_agent",
        description: "legacy description",
        instruction: "legacy instruction",
        type: "llm",
        model: "openrouter/meta/llama",
        tools: [],
        skills: [],
        children: [],
      },
    },
    "volcengine",
  );

  assert.equal(restored.name, "legacy_agent");
  assert.equal(restored.modelName, "meta/llama");
  assert.equal(restored.modelProvider, "openrouter");
  assert.deepEqual(restored.memory, { shortTerm: false, longTerm: false });
  assert.equal(restored.knowledgebase, false);
  assert.equal(restored.tracing, false);
});

test("Runtime update preserves and hydrates a registry-backed remote child Agent", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "registry_parent",
      graph: {
        name: "registry_parent",
        type: "llm",
        children: [{ name: "remote_child", type: "llm", children: [] }],
      },
      draft: {
        ...cachedRuntimeDraft("registry_parent"),
        cloudProvider: "byteplus",
        subAgents: [
          {
            ...cachedRuntimeDraft("remote_child"),
            cloudProvider: "byteplus",
            agentType: "a2a",
            a2aRegistry: {
              enabled: true,
              registrySpaceId: "stale-space",
              registryTopK: "2",
              registryRegion: "stale-region",
              registryEndpoint: "https://stale.example.com/",
            },
          },
        ],
      },
    },
    "byteplus",
  );
  const hydrated = hydrateA2aRegistryFromRuntime(restored, [
    { key: "REGISTRY_SPACE_ID", value: "bp-space" },
    { key: "REGISTRY_TOP_K", value: "6" },
    { key: "REGISTRY_REGION", value: "ap-southeast-1" },
    {
      key: "REGISTRY_ENDPOINT",
      value: "https://agentkit.ap-southeast-1.byteplusapi.com/",
    },
  ]);

  assert.equal(hydrated.subAgents[0].agentType, "a2a");
  assert.deepEqual(hydrated.subAgents[0].a2aRegistry, {
    enabled: true,
    registrySpaceId: "bp-space",
    registryTopK: "6",
    registryRegion: "ap-southeast-1",
    registryEndpoint: "https://agentkit.ap-southeast-1.byteplusapi.com/",
  });
});

test("Runtime update entry passes only cloud capability to the update handler", () => {
  const clickStart = workspaceSource.indexOf("onClick={() =>\n                      selectedDraft");
  const clickEnd = workspaceSource.indexOf("                    }\n                  >", clickStart);
  assert.ok(clickStart >= 0 && clickEnd > clickStart);
  const clickHandler = workspaceSource.slice(clickStart, clickEnd);

  assert.match(clickHandler, /onUpdateAgent\(selectedUpdateCapability\)/);
  assert.doesNotMatch(clickHandler, /onUpdateAgent\(draft,/);
  assert.doesNotMatch(clickHandler, /selectedAgentUpdateDraft[\s\S]*?onEditDraft/);
});

test("Runtime update hydration starts from cloud configuration without local draft values", () => {
  const handlerStart = appSource.indexOf(
    "onUpdateAgent={async (capability) =>",
  );
  const handlerEnd = appSource.indexOf("onEditDraft=", handlerStart);
  assert.ok(handlerStart >= 0 && handlerEnd > handlerStart);
  const handler = appSource.slice(handlerStart, handlerEnd);

  assert.match(handler, /runtimeAgentDraftFromCloud\([\s\S]*?capability\.agent/);
  assert.match(
    handler,
    /hydrateA2aRegistryFromRuntime\([\s\S]*?capability\.runtime\.envs/,
  );
  assert.doesNotMatch(handler, /\bnextDraft\b|draftEnvValues/);
  assert.match(handler, /setImportedDraft\(classifiedDraft\)/);
});
