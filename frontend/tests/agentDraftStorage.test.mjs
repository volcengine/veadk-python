import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/create/agentDraftStorage.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
const {
  loadWorkspaceDrafts,
  sanitizeAgentDraftForStorage,
  workspaceAgentCreationMode,
  workspaceDraftsKey,
  writeWorkspaceDrafts,
} = await import(moduleUrl);

function draft(overrides = {}) {
  return {
    name: "draft_agent",
    description: "draft",
    instruction: "help",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
    ...overrides,
  };
}

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
    value(key) {
      return values.get(key);
    },
  };
}

test("keeps MCP credentials ephemeral while preserving deployment values", () => {
  const sourceDraft = draft({
    mcpTools: [{ name: "root", transport: "http", authToken: "root-secret" }],
    deployment: { feishuEnabled: true, envValues: { FEISHU_APP_SECRET: "secret" } },
    subAgents: [
      draft({
        name: "child",
        mcpTools: [{ name: "child", transport: "http", authToken: "child-secret" }],
        deployment: { feishuEnabled: false, envValues: { API_KEY: "child-key" } },
      }),
    ],
    workflow: {
      type: "sequential",
      edges: [],
      nodes: [
        {
          id: "workflow-node",
          agent: draft({
            name: "workflow_agent",
            mcpTools: [
              { name: "workflow", transport: "http", authToken: "workflow-secret" },
            ],
          }),
        },
      ],
    },
  });

  const sanitized = sanitizeAgentDraftForStorage(sourceDraft);

  assert.equal(sanitized.mcpTools[0].authToken, undefined);
  assert.equal(sanitized.mcpTools[0].authTokenEnv, undefined);
  assert.deepEqual(sanitized.deployment.envValues, {
    FEISHU_APP_SECRET: "secret",
  });
  assert.equal(sanitized.subAgents[0].mcpTools[0].authToken, undefined);
  assert.equal(sanitized.subAgents[0].mcpTools[0].authTokenEnv, undefined);
  assert.deepEqual(sanitized.subAgents[0].deployment.envValues, {
    API_KEY: "child-key",
  });
  assert.equal(sanitized.workflow.nodes[0].agent.mcpTools[0].authToken, undefined);
  assert.equal(
    sanitized.workflow.nodes[0].agent.mcpTools[0].authTokenEnv,
    undefined,
  );
  assert.equal(sourceDraft.mcpTools[0].authToken, "root-secret");
  assert.doesNotMatch(
    JSON.stringify(sanitized),
    /root-secret|child-secret|workflow-secret/,
  );
});

test("persists every editable draft property including Feishu credentials", () => {
  const storage = memoryStorage();
  const completeDraft = draft({
    description: "complete description",
    instruction: "complete instruction",
    dynamicAgentDelegation: true,
    agentType: "llm",
    cloudProvider: "byteplus",
    maxIterations: 7,
    a2aUrl: "https://agent.example.com",
    model: "legacy-model",
    modelSource: "custom",
    modelName: "custom-model",
    modelProvider: "openai",
    modelApiBase: "https://model.example.com/v1",
    tools: ["legacy-tool"],
    skills: ["legacy-skill"],
    memory: { shortTerm: true, longTerm: true },
    knowledgebase: true,
    tracing: true,
    builtinTools: ["web_search"],
    customTools: [{ name: "lookup", description: "lookup records" }],
    mcpTools: [
      {
        name: "orders",
        transport: "http",
        url: "https://mcp.example.com/mcp",
        authTokenEnv: "MCP_ORDERS_TOKEN",
        credentialConfigured: true,
        credentialSourceUrl: "https://mcp.example.com/mcp",
        credentialSourceAuthTokenEnv: "MCP_ORDERS_TOKEN",
      },
    ],
    a2aRegistry: {
      enabled: true,
      registrySpaceId: "space-1",
      registryTopK: "5",
      registryRegion: "ap-southeast-1",
      registryEndpoint: "https://registry.example.com",
    },
    shortTermBackend: "redis",
    longTermBackend: "viking",
    longTermMemoryIndex: "memory-index",
    autoSaveSession: true,
    knowledgebaseBackend: "viking",
    knowledgebaseIndex: "knowledge-index",
    tracingExporters: ["tls"],
    selectedSkills: [
      {
        source: "runtime",
        folder: "ops",
        name: "ops",
        description: "operations",
      },
    ],
    cloudEnvironment: {
      environmentId: "environment-1",
      environmentVersionId: "version-2",
      cliTools: ["lark-cli"],
      dockerfile: "RUN echo ready",
    },
    harnessSidecar: {
      enabled: true,
      profile: "default",
      componentOverrides: {
        context_engine: true,
        compressor: false,
        verifier: true,
        long_run_control: false,
        mcp_resilience: true,
      },
      catalogVersion: "catalog-1",
      planHash: "sha256:plan",
    },
    deployment: {
      feishuEnabled: true,
      runtimeName: "runtime-name",
      runtimeNameCustomized: true,
      network: {
        mode: "both",
        vpcId: "vpc-1",
        subnetIds: "subnet-1,subnet-2",
        enableSharedInternetAccess: true,
      },
      modelApiKeyId: "key-id",
      modelApiKeyName: "key-name",
      envValues: {
        FEISHU_APP_ID: "cli_test",
        FEISHU_APP_SECRET: "persisted-feishu-secret",
        CUSTOM_SETTING: "custom-value",
      },
    },
  });

  writeWorkspaceDrafts(storage, "complete-builder", [
    {
      id: "complete-draft",
      updatedAt: 123,
      creationMode: "quick",
      deploymentTarget: {
        runtimeId: "runtime-1",
        name: "runtime-name",
        region: "ap-southeast-1",
        appName: "complete_app",
        currentVersion: 3,
        etag: "etag-1",
        editMode: "source-preserving",
        configuredMcpEnvKeys: ["MCP_ORDERS_TOKEN"],
        configuredRuntimeEnvKeys: ["OPAQUE_RUNTIME_SECRET"],
      },
      draft: completeDraft,
    },
  ]);

  const [loaded] = loadWorkspaceDrafts(storage, "complete-builder");
  assert.equal(loaded.creationMode, "quick");
  assert.deepEqual(loaded.deploymentTarget, {
    runtimeId: "runtime-1",
    name: "runtime-name",
    region: "ap-southeast-1",
    appName: "complete_app",
    currentVersion: 3,
    etag: "etag-1",
    editMode: "source-preserving",
    configuredMcpEnvKeys: ["MCP_ORDERS_TOKEN"],
    configuredRuntimeEnvKeys: ["OPAQUE_RUNTIME_SECRET"],
  });
  const expectedDraft = structuredClone(completeDraft);
  delete expectedDraft.mcpTools[0].credentialSourceUrl;
  delete expectedDraft.mcpTools[0].credentialSourceAuthTokenEnv;
  assert.deepEqual(loaded.draft, expectedDraft);
});

test("writes a versioned user-scoped payload without transient MCP values", () => {
  const storage = memoryStorage();
  writeWorkspaceDrafts(storage, "alice@example.com", [
    {
      id: "draft-1",
      updatedAt: 123,
      draft: draft({
        mcpTools: [{ name: "server", transport: "http", authToken: "secret" }],
      }),
    },
  ]);

  const payload = JSON.parse(storage.value(workspaceDraftsKey("alice@example.com")));
  assert.equal(payload.version, 1);
  assert.equal(payload.drafts[0].id, "draft-1");
  assert.equal(payload.drafts[0].draft.mcpTools[0].authToken, undefined);
  assert.equal(payload.drafts[0].draft.mcpTools[0].authTokenEnv, undefined);
  assert.equal(payload.drafts[0].draft.deployment, undefined);
  assert.equal(
    storage.value(workspaceDraftsKey("alice@example.com")).includes("secret"),
    false,
  );
});

test("persists recovered configured state without inventing an old MCP value", () => {
  const storage = memoryStorage();
  const configuredDraft = draft({
    mcpTools: [
      {
        name: "server",
        transport: "http",
        authTokenEnv: "MCP_SERVER_TOKEN",
        credentialConfigured: true,
      },
    ],
  });

  writeWorkspaceDrafts(storage, "alice", [
    { id: "configured", updatedAt: 123, draft: configuredDraft },
  ]);

  const serialized = storage.value(workspaceDraftsKey("alice"));
  const persisted = JSON.parse(serialized).drafts[0].draft;
  assert.equal(persisted.mcpTools[0].credentialConfigured, true);
  assert.equal(persisted.mcpTools[0].authTokenEnv, "MCP_SERVER_TOKEN");
  assert.equal(persisted.mcpTools[0].authToken, undefined);
  assert.equal(persisted.deployment?.envValues?.MCP_SERVER_TOKEN, undefined);
  assert.equal(serialized.includes("old-secret"), false);

  const loaded = loadWorkspaceDrafts(storage, "alice");
  assert.equal(loaded[0].draft.mcpTools[0].credentialConfigured, true);
});

test("keeps an explicit MCP environment reference but never its browser value", () => {
  const storage = memoryStorage();
  const referencedDraft = draft({
    mcpTools: [
      {
        name: "server",
        transport: "http",
        authToken: "${MCP_SERVER_TOKEN}",
      },
    ],
    deployment: {
      feishuEnabled: false,
      envValues: { MCP_SERVER_TOKEN: "must-stay-ephemeral" },
    },
  });

  writeWorkspaceDrafts(storage, "alice", [
    { id: "referenced", updatedAt: 123, draft: referencedDraft },
  ]);

  const serialized = storage.value(workspaceDraftsKey("alice"));
  const persisted = JSON.parse(serialized).drafts[0].draft;
  assert.equal(persisted.mcpTools[0].authTokenEnv, "MCP_SERVER_TOKEN");
  assert.equal(persisted.mcpTools[0].authToken, undefined);
  assert.equal(persisted.deployment.envValues.MCP_SERVER_TOKEN, undefined);
  assert.equal(serialized.includes("must-stay-ephemeral"), false);
});

test("preserves cloud environment selections in local drafts", () => {
  const storage = memoryStorage();
  const cloudEnvironment = {
    environmentId: "environment-123",
    environmentVersionId: "version-456",
  };
  writeWorkspaceDrafts(storage, "cloud-builder", [
    {
      id: "cloud-draft",
      updatedAt: 456,
      draft: draft({ cloudEnvironment }),
    },
  ]);

  const loaded = loadWorkspaceDrafts(storage, "cloud-builder");
  assert.deepEqual(loaded[0].draft.cloudEnvironment, cloudEnvironment);
});

test("persists the creation mode used to resume a workspace draft", () => {
  const storage = memoryStorage();
  writeWorkspaceDrafts(storage, "quick-builder", [
    {
      id: "quick-draft",
      updatedAt: 456,
      creationMode: "quick",
      draft: draft({ dynamicAgentDelegation: true }),
    },
    {
      id: "traditional-draft",
      updatedAt: 123,
      creationMode: "traditional",
      draft: draft(),
    },
  ]);

  const loaded = loadWorkspaceDrafts(storage, "quick-builder");
  assert.equal(loaded[0].creationMode, "quick");
  assert.equal(loaded[1].creationMode, "traditional");
  assert.equal(workspaceAgentCreationMode(loaded[0]), "quick");
  assert.equal(workspaceAgentCreationMode(loaded[1]), "traditional");
});

test("recovers legacy quick drafts from dynamic delegation", () => {
  assert.equal(
    workspaceAgentCreationMode({
      id: "legacy-quick",
      updatedAt: 1,
      draft: draft({ dynamicAgentDelegation: true }),
    }),
    "quick",
  );
  assert.equal(
    workspaceAgentCreationMode({
      id: "legacy-traditional",
      updatedAt: 2,
      draft: draft({ dynamicAgentDelegation: false }),
    }),
    "traditional",
  );
});

test("persists the published MCP key baseline with a Runtime update target", () => {
  const storage = memoryStorage();
  const deploymentTarget = {
    runtimeId: "runtime-1",
    name: "published-agent",
    region: "cn-beijing",
    appName: "published-agent",
    currentVersion: 7,
    etag: "opaque-etag",
    editMode: "source-preserving",
    configuredMcpEnvKeys: ["MCP_ROOT_TOKEN", "MCP_CHILD_TOKEN"],
  };

  writeWorkspaceDrafts(storage, "alice", [
    {
      id: "runtime-runtime-1",
      updatedAt: 456,
      draft: draft(),
      deploymentTarget,
    },
  ]);

  const loaded = loadWorkspaceDrafts(storage, "alice");
  assert.deepEqual(loaded[0].deploymentTarget, deploymentTarget);
});

test("round-trips every quick-create page field with its Runtime update identity", () => {
  const storage = memoryStorage();
  const quickDraft = draft({
    name: "research_assistant",
    description: "Researches complex topics and produces cited reports",
    instruction: "Plan the work, delegate independent research, then synthesize it.",
    dynamicAgentDelegation: true,
    cloudProvider: "byteplus",
    modelSource: "custom",
    modelName: "deepseek-v3-2",
    modelProvider: "openai",
    modelApiBase: "https://ark.ap-southeast-1.bytepluses.com/api/v3",
    selectedSkills: [
      {
        source: "skillspace",
        folder: "market-research",
        name: "Market research",
        description: "Research public markets",
        skillSpaceId: "space-1",
        skillSpaceName: "Production skills",
        skillId: "skill-1",
        version: "3",
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
      feishuEnabled: false,
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
      envValues: { REPORT_FORMAT: "markdown" },
    },
  });
  const deploymentTarget = {
    runtimeId: "runtime-quick-1",
    name: "research-assistant-runtime",
    region: "ap-southeast-1",
    appName: "research_assistant",
    currentVersion: 12,
    etag: "etag-v12",
    editMode: "regenerate",
    configuredMcpEnvKeys: ["MCP_RESEARCH_TOKEN"],
  };

  writeWorkspaceDrafts(storage, "quick-editor", [
    {
      id: "runtime-runtime-quick-1",
      updatedAt: 789,
      creationMode: "quick",
      draft: quickDraft,
      deploymentTarget,
    },
  ]);

  const [loaded] = loadWorkspaceDrafts(storage, "quick-editor");
  assert.equal(workspaceAgentCreationMode(loaded), "quick");
  assert.deepEqual(
    {
      name: loaded.draft.name,
      description: loaded.draft.description,
      instruction: loaded.draft.instruction,
      dynamicAgentDelegation: loaded.draft.dynamicAgentDelegation,
      cloudProvider: loaded.draft.cloudProvider,
      modelSource: loaded.draft.modelSource,
      modelName: loaded.draft.modelName,
      modelProvider: loaded.draft.modelProvider,
      modelApiBase: loaded.draft.modelApiBase,
      selectedSkills: loaded.draft.selectedSkills,
      cloudEnvironment: loaded.draft.cloudEnvironment,
      memory: loaded.draft.memory,
      shortTermBackend: loaded.draft.shortTermBackend,
      longTermBackend: loaded.draft.longTermBackend,
      longTermMemoryIndex: loaded.draft.longTermMemoryIndex,
      autoSaveSession: loaded.draft.autoSaveSession,
      deployment: loaded.draft.deployment,
    },
    {
      name: quickDraft.name,
      description: quickDraft.description,
      instruction: quickDraft.instruction,
      dynamicAgentDelegation: quickDraft.dynamicAgentDelegation,
      cloudProvider: quickDraft.cloudProvider,
      modelSource: quickDraft.modelSource,
      modelName: quickDraft.modelName,
      modelProvider: quickDraft.modelProvider,
      modelApiBase: quickDraft.modelApiBase,
      selectedSkills: quickDraft.selectedSkills,
      cloudEnvironment: quickDraft.cloudEnvironment,
      memory: quickDraft.memory,
      shortTermBackend: quickDraft.shortTermBackend,
      longTermBackend: quickDraft.longTermBackend,
      longTermMemoryIndex: quickDraft.longTermMemoryIndex,
      autoSaveSession: quickDraft.autoSaveSession,
      deployment: quickDraft.deployment,
    },
  );
  assert.deepEqual(loaded.deploymentTarget, deploymentTarget);
});

test("never persists server-managed Ark API key values while retaining selection metadata", () => {
  const leakedValue = "raw-ark-secret-must-not-enter-local-storage";
  const storage = memoryStorage();
  const draftWithLegacySecrets = draft({
    deployment: {
      feishuEnabled: false,
      modelApiKeyId: "ark-key-id",
      modelApiKeyName: "production-key",
      envValues: {
        MODEL_AGENT_API_KEY: leakedValue,
        SAFE_SETTING: "kept",
      },
    },
    subAgents: [
      draft({
        name: "child",
        deployment: {
          feishuEnabled: false,
          envValues: { MODEL_AGENT_API_KEY: leakedValue },
        },
      }),
    ],
    workflow: {
      type: "sequential",
      edges: [],
      nodes: [
        {
          id: "workflow-node",
          agent: draft({
            name: "workflow_agent",
            deployment: {
              feishuEnabled: false,
              envValues: { MODEL_AGENT_API_KEY: leakedValue },
            },
          }),
        },
      ],
    },
  });

  writeWorkspaceDrafts(storage, "alice", [
    {
      id: "draft-with-legacy-secret",
      updatedAt: 123,
      draft: draftWithLegacySecrets,
    },
  ]);

  const serialized = storage.value(workspaceDraftsKey("alice"));
  assert.equal(serialized.includes(leakedValue), false);
  const persisted = JSON.parse(serialized).drafts[0].draft;
  assert.equal(persisted.deployment.modelApiKeyId, "ark-key-id");
  assert.equal(persisted.deployment.modelApiKeyName, "production-key");
  assert.deepEqual(persisted.deployment.envValues, { SAFE_SETTING: "kept" });
  assert.deepEqual(persisted.subAgents[0].deployment.envValues, {});
  assert.deepEqual(
    persisted.workflow.nodes[0].agent.deployment.envValues,
    {},
  );
});

test("loads both legacy arrays and the current versioned payload", () => {
  const key = workspaceDraftsKey("alice");
  const legacyDraft = { id: "legacy", updatedAt: 1, draft: draft() };
  const legacyStorage = memoryStorage({ [key]: JSON.stringify([legacyDraft]) });
  assert.deepEqual(loadWorkspaceDrafts(legacyStorage, "alice"), [legacyDraft]);

  const currentStorage = memoryStorage({
    [key]: JSON.stringify({ version: 1, drafts: [legacyDraft] }),
  });
  assert.deepEqual(loadWorkspaceDrafts(currentStorage, "alice"), [legacyDraft]);
});

test("rejects unsupported or malformed persisted payloads", () => {
  const key = workspaceDraftsKey("alice");
  assert.throws(
    () => loadWorkspaceDrafts(memoryStorage({ [key]: "not-json" }), "alice"),
    /Could not read local drafts/,
  );
  assert.throws(
    () =>
      loadWorkspaceDrafts(
        memoryStorage({ [key]: JSON.stringify({ version: 2, drafts: [] }) }),
        "alice",
      ),
    /not supported/,
  );
});

test("reports browser storage write failures with a recovery action", () => {
  const storage = memoryStorage();
  storage.setItem = () => {
    throw new DOMException("quota", "QuotaExceededError");
  };

  assert.throws(
    () => writeWorkspaceDrafts(storage, "alice", []),
    /Delete unused drafts or clear this site's storage/,
  );
});
