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
  mcpAuthTokenInputValue,
  mcpUrlNeedsPathWarning,
  prepareMcpAuth,
  updateMcpAuthTokenInput,
} = await loadTypeScriptModule("../src/create/mcpAuth.ts");
const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
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
