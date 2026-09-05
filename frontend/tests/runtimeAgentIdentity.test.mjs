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
  stripManagedRuntimeInstructions,
} = await loadTypeScriptModule("../src/create/runtimeModelName.ts");
const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
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

test("published draft instructions are not replaced by managed Runtime rules", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "quick_agent",
      name: "quick_agent",
      draft: {
        ...cachedRuntimeDraft("quick_agent"),
        instruction: "User-authored instruction.",
        dynamicAgentDelegation: true,
      },
      graph: {
        name: "quick_agent",
        type: "llm",
        instruction:
          "User-authored instruction.\n\nManaged dynamic delegation rules.",
        children: [],
      },
    },
    "volcengine",
  );

  assert.equal(restored.instruction, "User-authored instruction.");
});

const managedRuntimeRules = ({
  escaped = false,
  heading = "动态子智能体协作规则：",
} = {}) => {
  const collectResources = escaped ? "collect\\_resources" : "collect_resources";
  const createAgents = escaped ? "create\\_agents" : "create_agents";
  const handoffTo = escaped ? "handoff\\_to" : "handoff_to";
  return [
    heading,
    `- 先调用 ${collectResources} 获取资源。`,
    `- 再调用 ${createAgents} 创建子智能体。`,
    `- 最后通过 ${handoffTo} 移交任务。`,
  ].join("\n");
};

test("quick draft recovery strips an unescaped managed Runtime rule block", () => {
  const instruction = "Keep this user prompt exactly.\n\n" + managedRuntimeRules();
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("quick_agent"),
    instruction,
    dynamicAgentDelegation: true,
  });

  assert.equal(restored.instruction, "Keep this user prompt exactly.");
});

test("quick draft recovery strips Markdown-escaped managed Runtime rules", () => {
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("quick_agent"),
    instruction: `Escaped user prompt.\n\n${managedRuntimeRules({ escaped: true })}`,
    dynamicAgentDelegation: true,
  });

  assert.equal(restored.instruction, "Escaped user prompt.");
});

test("quick draft recovery strips localized English managed Runtime rules", () => {
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("quick_agent"),
    instruction: `English user prompt.\n\n${managedRuntimeRules({
      heading: "Dynamic sub-agent collaboration rules:",
    })}`,
    dynamicAgentDelegation: true,
  });

  assert.equal(restored.instruction, "English user prompt.");
});

test("quick draft recovery truncates repeated managed rules at the first valid block", () => {
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("quick_agent"),
    instruction: [
      "Original prompt",
      managedRuntimeRules(),
      managedRuntimeRules({ escaped: true }),
    ].join("\n\n"),
    dynamicAgentDelegation: true,
  });

  assert.equal(restored.instruction, "Original prompt");
});

test("a user-authored managed-rule heading without stable signatures is preserved", () => {
  const instruction =
    "请解释下面这个标题：\n动态子智能体协作规则：\n这只是用户输入。";
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("quick_agent"),
    instruction,
    dynamicAgentDelegation: true,
  });

  assert.equal(restored.instruction, instruction);
});

test("managed Runtime rules are stripped recursively from quick draft agents", () => {
  const withManagedRules = (name, instruction) => ({
    ...cachedRuntimeDraft(name),
    instruction: `${instruction}\n\n${managedRuntimeRules({ escaped: true })}`,
    dynamicAgentDelegation: true,
  });
  const restored = stripManagedRuntimeInstructions({
    ...withManagedRules("root", "Root prompt"),
    dynamicAgentDelegation: true,
    subAgents: [withManagedRules("child", "Child prompt")],
    workflow: {
      nodes: [
        {
          id: "workflow-node",
          agent: withManagedRules("workflow_agent", "Workflow prompt"),
        },
      ],
    },
  });

  assert.equal(restored.instruction, "Root prompt");
  assert.equal(restored.subAgents[0].instruction, "Child prompt");
  assert.equal(restored.workflow.nodes[0].agent.instruction, "Workflow prompt");
});

test("traditional cloud drafts retain text resembling managed Runtime rules", () => {
  const instruction = `Traditional prompt.\n\n${managedRuntimeRules()}`;
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("traditional_agent"),
    instruction,
    dynamicAgentDelegation: false,
  });

  assert.equal(restored.instruction, instruction);
});

test("mixed drafts strip managed rules only from delegation-enabled nodes", () => {
  const childInstruction = `Traditional child prompt.\n\n${managedRuntimeRules()}`;
  const restored = stripManagedRuntimeInstructions({
    ...cachedRuntimeDraft("quick_agent"),
    instruction: `Quick prompt.\n\n${managedRuntimeRules()}`,
    dynamicAgentDelegation: true,
    subAgents: [
      {
        ...cachedRuntimeDraft("traditional_child"),
        instruction: childInstruction,
        dynamicAgentDelegation: false,
      },
    ],
  });

  assert.equal(restored.instruction, "Quick prompt.");
  assert.equal(restored.subAgents[0].instruction, childInstruction);
});

test("quick Runtime recovery restores every field shown by the three-step editor", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "research_assistant",
      name: "research_assistant",
      draft: {
        ...cachedRuntimeDraft("research_assistant"),
        description: "Researches complex topics and produces cited reports",
        instruction: "Plan, delegate independent research, and synthesize the result.",
        dynamicAgentDelegation: true,
        cloudProvider: "byteplus",
        modelSource: "custom",
        modelName: "deepseek-v3-2",
        modelProvider: "openai",
        modelApiBase: "https://ark.ap-southeast-1.bytepluses.com/api/v3",
        selectedSkills: [
          {
            source: "runtime",
            folder: "market-research",
            name: "market-research",
            description: "Research public markets",
          },
        ],
        cloudEnvironment: {
          environmentId: "env-1",
          environmentVersionId: "env-version-2",
          cliTools: ["lark-cli", "github-cli"],
          dockerfile: "RUN echo ready",
        },
        memory: { shortTerm: true, longTerm: true },
        shortTermBackend: "sqlite",
        longTermBackend: "viking",
        longTermMemoryIndex: "memory-index-1",
        autoSaveSession: true,
        deployment: {
          feishuEnabled: true,
          runtimeName: "research-assistant-runtime",
          runtimeNameCustomized: true,
          network: {
            mode: "both",
            vpcId: "vpc-1",
            subnetIds: "subnet-1,subnet-2",
            enableSharedInternetAccess: true,
          },
          modelApiKeyId: "api-key-1",
          modelApiKeyName: "Production Ark key",
          envValues: {
            REPORT_FORMAT: "markdown",
            FEISHU_APP_ID: "cli_test",
            FEISHU_APP_SECRET: "feishu-secret",
          },
        },
      },
    },
    "byteplus",
  );

  assert.deepEqual(
    {
      name: restored.name,
      description: restored.description,
      instruction: restored.instruction,
      dynamicAgentDelegation: restored.dynamicAgentDelegation,
      cloudProvider: restored.cloudProvider,
      modelSource: restored.modelSource,
      modelName: restored.modelName,
      modelProvider: restored.modelProvider,
      modelApiBase: restored.modelApiBase,
      selectedSkills: restored.selectedSkills,
      cloudEnvironment: restored.cloudEnvironment,
      memory: restored.memory,
      shortTermBackend: restored.shortTermBackend,
      longTermBackend: restored.longTermBackend,
      longTermMemoryIndex: restored.longTermMemoryIndex,
      autoSaveSession: restored.autoSaveSession,
      deployment: restored.deployment,
    },
    {
      name: "research_assistant",
      description: "Researches complex topics and produces cited reports",
      instruction: "Plan, delegate independent research, and synthesize the result.",
      dynamicAgentDelegation: true,
      cloudProvider: "byteplus",
      modelSource: "custom",
      modelName: "deepseek-v3-2",
      modelProvider: "openai",
      modelApiBase: "https://ark.ap-southeast-1.bytepluses.com/api/v3",
      selectedSkills: [
        {
          source: "runtime",
          folder: "market-research",
          name: "market-research",
          description: "Research public markets",
        },
      ],
      cloudEnvironment: {
        environmentId: "env-1",
        environmentVersionId: "env-version-2",
        cliTools: ["lark-cli", "github-cli"],
        dockerfile: "RUN echo ready",
      },
      memory: { shortTerm: true, longTerm: true },
      shortTermBackend: "sqlite",
      longTermBackend: "viking",
      longTermMemoryIndex: "memory-index-1",
      autoSaveSession: true,
      deployment: {
        feishuEnabled: true,
        runtimeName: "research-assistant-runtime",
        runtimeNameCustomized: true,
        network: {
          mode: "both",
          vpcId: "vpc-1",
          subnetIds: "subnet-1,subnet-2",
          enableSharedInternetAccess: true,
        },
        modelApiKeyId: "api-key-1",
        modelApiKeyName: "Production Ark key",
        envValues: {
          REPORT_FORMAT: "markdown",
          FEISHU_APP_ID: "cli_test",
          FEISHU_APP_SECRET: "feishu-secret",
        },
      },
    },
  );
});

test("legacy partial ops metadata is restored as the complete ops preset", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "legacy_ops_app",
      name: "legacy_ops_agent",
      draft: {
        ...cachedRuntimeDraft("legacy_ops_agent"),
        harnessSidecar: {
          enabled: true,
          profile: "ops",
          componentOverrides: {
            context_engine: false,
            compressor: false,
            verifier: false,
            long_run_control: false,
            mcp_resilience: true,
          },
        },
      },
    },
    "volcengine",
  );

  assert.deepEqual(restored.harnessSidecar.componentOverrides, {
    context_engine: true,
    compressor: false,
    verifier: true,
    long_run_control: true,
    mcp_resilience: true,
  });
});

test("runtime-preserved skills survive update draft normalization without fake files", () => {
  const normalized = normalizeDraft({
    ...cachedRuntimeDraft("legacy_agent"),
    selectedSkills: [
      {
        source: "runtime",
        folder: "serial-inspector",
        name: "serial-inspector",
        description: "Running version",
      },
    ],
  });

  assert.deepEqual(normalized.selectedSkills, [
    {
      source: "runtime",
      folder: "serial-inspector",
      name: "serial-inspector",
      description: "Running version",
    },
  ]);
});

test("recovered MCP authentication populates the editable credential value", () => {
  const restored = runtimeAgentDraftFromCloud(
    {
      appName: "cloud_app",
      name: "cloud_agent",
      draft: {
        ...cachedRuntimeDraft("cloud_agent"),
        mcpTools: [
          {
            name: "orders",
            transport: "http",
            url: "https://mcp.example.com/mcp",
            authToken: "recovered-editor-token",
            authTokenEnv: "MCP_ORDERS_TOKEN",
          },
          {
            name: "public",
            transport: "http",
            url: "https://mcp.example.com/public/mcp",
          },
        ],
      },
    },
    "volcengine",
    ["MCP_ORDERS_TOKEN"],
  );

  assert.equal(restored.mcpTools[0].credentialConfigured, true);
  assert.equal(restored.mcpTools[0].authToken, "recovered-editor-token");
  assert.equal(restored.mcpTools[1].credentialConfigured, false);
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
