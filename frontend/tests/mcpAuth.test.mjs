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

function draft(overrides = {}) {
  return {
    name: "sales-agent",
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

const {
  confirmMcpCredentialReuse,
  clearMcpConfiguredAuth,
  configuredMcpEnvKeys,
  deploymentMcpSecretValues,
  mcpCredentialActionRequired,
  mcpConfigurationConflict,
  mcpCredentialReuseValues,
  mcpAuthTokenInputValue,
  mcpUrlNeedsPathWarning,
  prepareMcpAuth,
  replaceMcpCredentialForChangedUrl,
  removedConfiguredMcpEnvKeys,
  removeMcpCredentialForChangedUrl,
  sourcePreservingMcpSecretValues,
  updateMcpAuthTokenInput,
  updateMcpUrlInput,
} = await loadTypeScriptModule("../src/create/mcpAuth.ts");
const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);

test("moves MCP tokens to deterministic collision-safe environment variables", () => {
  const source = draft({
    mcpTools: [
      { name: "orders", transport: "http", authToken: "first-secret" },
      { name: "orders", transport: "http", authToken: "second-secret" },
    ],
  });

  const prepared = prepareMcpAuth(source);

  assert.deepEqual(
    prepared.draft.mcpTools.map((tool) => tool.authTokenEnv),
    [
      "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
      "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN_2",
    ],
  );
  assert.deepEqual(prepared.envValues, {
    MCP_SALES_AGENT_ORDERS_AUTH_TOKEN: "first-secret",
    MCP_SALES_AGENT_ORDERS_AUTH_TOKEN_2: "second-secret",
  });
  assert.doesNotMatch(JSON.stringify(prepared.draft), /first-secret|second-secret/);
  assert.equal(source.mcpTools[0].authToken, "first-secret");
});

test("shows an environment reference and treats replacement input as transient", () => {
  const tool = {
    name: "orders",
    transport: "http",
    authTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
  };
  assert.equal(
    mcpAuthTokenInputValue(tool),
    "${MCP_SALES_AGENT_ORDERS_AUTH_TOKEN}",
  );

  const replaced = updateMcpAuthTokenInput(tool, "replacement-secret");
  assert.equal(replaced.authToken, "replacement-secret");
  assert.equal(replaced.authTokenEnv, "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN");
});

test("shows recovered MCP credentials and clears their binding with the input", () => {
  const tool = {
    name: "orders",
    transport: "http",
    authTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
    authToken: "recovered-secret",
    credentialConfigured: true,
  };

  assert.equal(mcpAuthTokenInputValue(tool), "recovered-secret");

  const removedByInput = updateMcpAuthTokenInput(tool, "");
  assert.equal(removedByInput.authTokenEnv, undefined);
  assert.equal(removedByInput.authToken, undefined);
  assert.equal(removedByInput.credentialConfigured, false);

  const replaced = updateMcpAuthTokenInput(tool, "replacement-secret");
  assert.equal(replaced.authToken, "replacement-secret");
  assert.equal(replaced.credentialConfigured, false);

  const removed = clearMcpConfiguredAuth({ ...tool, authToken: undefined });
  assert.equal(removed.authToken, undefined);
  assert.equal(removed.authTokenEnv, undefined);
  assert.equal(removed.credentialConfigured, false);

  const prepared = prepareMcpAuth(draft({ mcpTools: [tool] }));
  assert.equal(prepared.draft.mcpTools[0].authTokenEnv, tool.authTokenEnv);
  assert.equal(prepared.draft.mcpTools[0].credentialConfigured, undefined);
  assert.doesNotMatch(JSON.stringify(prepared.draft), /recovered-secret|configured.*true/i);
});

test("wires the MCP URL-change credential choices into the editor and deploy payload", () => {
  assert.match(
    customCreateSource,
    /onChange\(\s*tools\.map\([\s\S]*?updateMcpUrlInput\(tool, e\.target\.value\)/,
  );
  assert.match(
    customCreateSource,
    /aria-invalid=\{mcpCredentialActionRequired\(tool\)\}/,
  );
  assert.match(customCreateSource, /t\("traditional\.mcp\.reuseCredential"\)/);
  assert.match(customCreateSource, /t\("traditional\.mcp\.replaceCredential"\)/);
  assert.match(customCreateSource, /t\("traditional\.mcp\.noAuth"\)/);
  assert.match(
    customCreateSource,
    /mcpCredentialReuses:\s*deploymentTarget[\s\S]*?mcpCredentialReuseValues\(draft\)/,
  );
});

test("requires an explicit credential decision when a published MCP URL changes", () => {
  const published = {
    name: "orders",
    transport: "http",
    url: "https://mcp.example.com/orders/mcp",
    authTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
    authToken: "recovered-secret",
    credentialConfigured: true,
    credentialSourceUrl: "https://mcp.example.com/orders/mcp",
    credentialSourceAuthTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
  };

  const changed = updateMcpUrlInput(
    published,
    "https://new-mcp.example.com/orders/mcp",
  );
  assert.equal(changed.authToken, undefined);
  assert.equal(changed.credentialUpdate, "pending");
  assert.equal(mcpCredentialActionRequired(changed), true);
  assert.equal(mcpAuthTokenInputValue(changed), "");

  const reused = confirmMcpCredentialReuse(changed);
  assert.equal(reused.credentialUpdate, "reuse");
  assert.equal(mcpCredentialActionRequired(reused), false);
  assert.deepEqual(mcpCredentialReuseValues(draft({ mcpTools: [reused] })), [
    {
      agentName: "sales-agent",
      name: "orders",
      url: "https://new-mcp.example.com/orders/mcp",
      sourceAuthTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
    },
  ]);

  const restored = updateMcpUrlInput(
    reused,
    "https://mcp.example.com/orders/mcp/",
  );
  assert.equal(restored.credentialUpdate, undefined);
  assert.equal(restored.credentialConfigured, true);
  assert.equal(
    restored.authTokenEnv,
    "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
  );
});

test("supports replacing or explicitly removing auth after an MCP URL change", () => {
  const changed = updateMcpUrlInput(
    {
      name: "orders",
      transport: "http",
      url: "https://mcp.example.com/orders/mcp",
      authTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
      credentialConfigured: true,
    },
    "https://new-mcp.example.com/orders/mcp",
  );

  const replacing = replaceMcpCredentialForChangedUrl(changed);
  assert.equal(replacing.authTokenEnv, undefined);
  assert.equal(replacing.credentialUpdate, "replace");
  const replacement = updateMcpAuthTokenInput(
    replacing,
    "replacement-secret",
  );
  assert.equal(replacement.credentialUpdate, "replace");
  assert.deepEqual(
    deploymentMcpSecretValues(draft({ mcpTools: [replacement] })),
    [
      {
        agentName: "sales-agent",
        name: "orders",
        url: "https://new-mcp.example.com/orders/mcp",
        value: "replacement-secret",
      },
    ],
  );

  const removed = removeMcpCredentialForChangedUrl(changed);
  assert.equal(removed.credentialUpdate, "remove");
  assert.equal(removed.authTokenEnv, undefined);
  assert.equal(mcpCredentialActionRequired(removed), false);
  assert.deepEqual(mcpCredentialReuseValues(draft({ mcpTools: [removed] })), []);
});

test("finds duplicate MCP names and canonical endpoint URLs before deploy", () => {
  assert.equal(
    mcpConfigurationConflict(
      draft({
        mcpTools: [
          { name: "orders", transport: "http", url: "https://one.example.com/mcp" },
          { name: "orders", transport: "http", url: "https://two.example.com/mcp" },
        ],
      }),
    ),
    "duplicateName",
  );
  assert.equal(
    mcpConfigurationConflict(
      draft({
        mcpTools: [
          {
            name: "orders-a",
            transport: "http",
            url: "https://MCP.example.com:443/orders/mcp/",
          },
          {
            name: "orders-b",
            transport: "http",
            url: "https://mcp.example.com/orders/mcp",
          },
        ],
      }),
    ),
    "duplicateUrl",
  );
  assert.equal(
    mcpConfigurationConflict(
      draft({
        mcpTools: [
          {
            name: "orders-a",
            transport: "http",
            url: "https://mcp.example.com/orders/../mcp",
          },
          {
            name: "orders-b",
            transport: "http",
            url: "https://mcp.example.com/mcp",
          },
        ],
      }),
    ),
    null,
  );
});

test("keeps unchanged reference-only credentials eligible for server resolution", () => {
  const unchanged = draft({
    mcpTools: [
      {
        name: "orders",
        transport: "http",
        url: "https://mcp.example.com/orders/mcp",
        authTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
        credentialConfigured: true,
        credentialSourceUrl: "https://mcp.example.com/orders/mcp",
        credentialSourceAuthTokenEnv: "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
      },
    ],
  });

  assert.equal(mcpCredentialActionRequired(unchanged.mcpTools[0]), false);
  assert.deepEqual(deploymentMcpSecretValues(unchanged), []);
  assert.deepEqual(mcpCredentialReuseValues(unchanged), []);
  const prepared = prepareMcpAuth(unchanged).draft.mcpTools[0];
  assert.equal(
    prepared.authTokenEnv,
    "MCP_SALES_AGENT_ORDERS_AUTH_TOKEN",
  );
  assert.equal(prepared.credentialSourceUrl, undefined);
  assert.equal(prepared.credentialUpdate, undefined);
});

test("derives configured and removed MCP keys across nested agent graphs", () => {
  const configuredTool = (name, authTokenEnv) => ({
    name,
    transport: "http",
    url: `https://mcp.example.com/${name}/mcp`,
    authTokenEnv,
    credentialConfigured: true,
  });
  const published = draft({
    mcpTools: [configuredTool("root", "MCP_ROOT_TOKEN")],
    subAgents: [
      draft({
        name: "child",
        mcpTools: [configuredTool("child", "MCP_CHILD_TOKEN")],
      }),
    ],
    workflow: {
      type: "sequential",
      edges: [],
      nodes: [
        {
          id: "worker",
          agent: draft({
            name: "worker",
            mcpTools: [configuredTool("worker", "MCP_WORKFLOW_TOKEN")],
          }),
        },
      ],
    },
  });

  const publishedKeys = configuredMcpEnvKeys(published);
  assert.deepEqual(publishedKeys, [
    "MCP_ROOT_TOKEN",
    "MCP_CHILD_TOKEN",
    "MCP_WORKFLOW_TOKEN",
  ]);
  assert.deepEqual(removedConfiguredMcpEnvKeys(publishedKeys, published), []);

  const edited = {
    ...published,
    mcpTools: [
      {
        ...published.mcpTools[0],
        authToken: "replacement-secret",
        credentialConfigured: false,
      },
    ],
    subAgents: [{ ...published.subAgents[0], mcpTools: [] }],
    workflow: {
      ...published.workflow,
      nodes: published.workflow.nodes.map((node) => ({
        ...node,
        agent: {
          ...node.agent,
          mcpTools: node.agent.mcpTools.map(clearMcpConfiguredAuth),
        },
      })),
    },
  };

  assert.deepEqual(removedConfiguredMcpEnvKeys(publishedKeys, edited), [
    "MCP_CHILD_TOKEN",
    "MCP_WORKFLOW_TOKEN",
  ]);
  assert.equal(
    removedConfiguredMcpEnvKeys(publishedKeys, edited).includes("MCP_ROOT_TOKEN"),
    false,
  );
});

test("does not remove a published key while another MCP still references it", () => {
  const current = draft({
    mcpTools: [
      {
        name: "replacement",
        transport: "http",
        url: "https://mcp.example.com/replacement/mcp",
        authTokenEnv: "MCP_SHARED_TOKEN",
        authToken: "new-secret",
      },
    ],
  });

  assert.deepEqual(
    removedConfiguredMcpEnvKeys(["MCP_SHARED_TOKEN"], current),
    [],
  );
});

test("submits source-preserving MCP secrets by endpoint identity, not env name", () => {
  const source = draft({
    mcpTools: [
      {
        name: "orders",
        transport: "http",
        url: "https://mcp.example.com/orders/mcp",
        authToken: "replacement-secret",
        authTokenEnv: "BROWSER_CHOSEN_REFERENCE",
      },
      {
        name: "stdio",
        transport: "stdio",
        command: "npx",
        args: ["server"],
        authToken: "must-not-be-submitted",
      },
    ],
    subAgents: [
      draft({
        name: "worker",
        mcpTools: [
          {
            name: "inventory",
            transport: "http",
            url: "https://mcp.example.com/inventory/mcp",
            authToken: "worker-secret",
          },
        ],
      }),
    ],
  });

  assert.deepEqual(sourcePreservingMcpSecretValues(source), [
    {
      agentName: "sales-agent",
      name: "orders",
      url: "https://mcp.example.com/orders/mcp",
      value: "replacement-secret",
    },
    {
      agentName: "worker",
      name: "inventory",
      url: "https://mcp.example.com/inventory/mcp",
      value: "worker-secret",
    },
  ]);
});

test("resolves new Sidecar MCP credentials from prior tool inputs only", () => {
  const source = draft({
    deployment: {
      envValues: { IMPORTED_INVENTORY_TOKEN: "imported-inventory-secret" },
    },
    mcpTools: [
      {
        name: "public",
        transport: "http",
        url: "https://mcp.example.com/public/mcp",
      },
      {
        name: "orders",
        transport: "http",
        url: "https://mcp.example.com/orders/mcp",
        authToken: "new-orders-secret",
      },
      {
        name: "inventory",
        transport: "http",
        url: "https://mcp.example.com/inventory/mcp",
        authTokenEnv: "IMPORTED_INVENTORY_TOKEN",
      },
    ],
  });

  assert.deepEqual(deploymentMcpSecretValues(source), [
    {
      agentName: "sales-agent",
      name: "orders",
      url: "https://mcp.example.com/orders/mcp",
      value: "new-orders-secret",
    },
    {
      agentName: "sales-agent",
      name: "inventory",
      url: "https://mcp.example.com/inventory/mcp",
      value: "imported-inventory-secret",
    },
  ]);
  assert.doesNotMatch(
    JSON.stringify(prepareMcpAuth(source).draft.mcpTools),
    /new-orders-secret|imported-inventory-secret/,
  );
});

test("warns about non-standard MCP paths without rewriting them", () => {
  assert.equal(mcpUrlNeedsPathWarning("https://example.com/mcp"), false);
  assert.equal(
    mcpUrlNeedsPathWarning("https://example.com/gateway/mcp/?region=cn"),
    false,
  );
  assert.equal(mcpUrlNeedsPathWarning("https://example.com/custom-path"), true);
});

test("YAML export preserves MCP tokens as runtime environment values", () => {
  assert.match(configYamlSource, /const prepared = prepareMcpAuth\(draft\)/);
  assert.match(
    configYamlSource,
    /envValues = \{[\s\S]*?\.\.\.prepared\.envValues/,
  );
  assert.match(configYamlSource, /deployment\.envValues = \{/);
  assert.doesNotMatch(configYamlSource, /e\.authToken =/);

  const imported = normalizeDraft({
    name: "sales-agent",
    deployment: {
      envValues: { MCP_SALES_AGENT_ORDERS_AUTH_TOKEN: "yaml-secret" },
    },
  });
  assert.equal(
    imported.deployment.envValues.MCP_SALES_AGENT_ORDERS_AUTH_TOKEN,
    "yaml-secret",
  );
});
