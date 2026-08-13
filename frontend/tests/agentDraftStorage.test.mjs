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

test("persists runtime credentials while converting MCP tokens to environment values", () => {
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
  assert.equal(sanitized.mcpTools[0].authTokenEnv, "MCP_DRAFT_AGENT_ROOT_AUTH_TOKEN");
  assert.deepEqual(sanitized.deployment.envValues, {
    FEISHU_APP_SECRET: "secret",
    MCP_DRAFT_AGENT_ROOT_AUTH_TOKEN: "root-secret",
    MCP_CHILD_CHILD_AUTH_TOKEN: "child-secret",
    MCP_WORKFLOW_AGENT_WORKFLOW_AUTH_TOKEN: "workflow-secret",
  });
  assert.equal(sanitized.subAgents[0].mcpTools[0].authToken, undefined);
  assert.equal(
    sanitized.subAgents[0].mcpTools[0].authTokenEnv,
    "MCP_CHILD_CHILD_AUTH_TOKEN",
  );
  assert.deepEqual(sanitized.subAgents[0].deployment.envValues, {
    API_KEY: "child-key",
  });
  assert.equal(sanitized.workflow.nodes[0].agent.mcpTools[0].authToken, undefined);
  assert.equal(sourceDraft.mcpTools[0].authToken, "root-secret");
});

test("writes a versioned user-scoped payload with runtime environment values", () => {
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
  assert.equal(
    payload.drafts[0].draft.mcpTools[0].authTokenEnv,
    "MCP_DRAFT_AGENT_SERVER_AUTH_TOKEN",
  );
  assert.deepEqual(payload.drafts[0].draft.deployment.envValues, {
    MCP_DRAFT_AGENT_SERVER_AUTH_TOKEN: "secret",
  });
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
    /无法读取本机草稿/,
  );
  assert.throws(
    () =>
      loadWorkspaceDrafts(
        memoryStorage({ [key]: JSON.stringify({ version: 2, drafts: [] }) }),
        "alice",
      ),
    /版本暂不受支持/,
  );
});

test("reports browser storage write failures with a recovery action", () => {
  const storage = memoryStorage();
  storage.setItem = () => {
    throw new DOMException("quota", "QuotaExceededError");
  };

  assert.throws(
    () => writeWorkspaceDrafts(storage, "alice", []),
    /删除不需要的草稿或清理此站点的浏览器存储后重试/,
  );
});
