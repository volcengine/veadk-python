// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
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
    name: "root-agent",
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

const { resolveMcpGatewayEnv } = await loadTypeScriptModule(
  "../src/create/mcpGatewayEnv.ts",
);

test("derives Sidecar MCP upstream URLs from the previously added HTTP tool", () => {
  const result = resolveMcpGatewayEnv(
    draft({
      mcpTools: [
        {
          name: "orders",
          transport: "http",
          url: " https://mcp.example.test/orders/mcp ",
          authTokenEnv: "MCP_ORDERS_TOKEN",
        },
      ],
    }),
  );

  assert.deepEqual(result, {
    ok: true,
    urls: ["https://mcp.example.test/orders/mcp"],
  });
});

test("collects nested and workflow HTTP tools once without inspecting credentials", () => {
  const sharedTool = {
    name: "inventory",
    transport: "http",
    url: "https://mcp.example.test/inventory/mcp",
    authTokenEnv: "MCP_SHARED_TOKEN",
  };
  const workflowAgent = draft({ name: "workflow-agent", mcpTools: [sharedTool] });
  const result = resolveMcpGatewayEnv(
    draft({
      mcpTools: [
        {
          name: "orders",
          transport: "http",
          url: "https://mcp.example.test/orders/mcp",
          authTokenEnv: "MCP_SHARED_TOKEN",
        },
        { name: "local", transport: "stdio", command: "example" },
      ],
      subAgents: [workflowAgent],
      workflow: {
        type: "sequential",
        nodes: [{ id: "inventory", agent: workflowAgent }],
        edges: [],
      },
    }),
  );

  assert.deepEqual(result, {
    ok: true,
    urls: [
      "https://mcp.example.test/orders/mcp",
      "https://mcp.example.test/inventory/mcp",
    ],
  });
});

test("preserves one gateway route per configured HTTP tool", () => {
  const result = resolveMcpGatewayEnv(
    draft({
      mcpTools: [
        {
          name: "orders-primary",
          transport: "http",
          url: "https://mcp.example.test/shared/mcp",
          authTokenEnv: "MCP_SHARED_TOKEN",
        },
        {
          name: "orders-secondary",
          transport: "http",
          url: "https://mcp.example.test/shared/mcp",
          authTokenEnv: "MCP_SHARED_TOKEN",
        },
      ],
    }),
  );

  assert.deepEqual(result, {
    ok: true,
    urls: [
      "https://mcp.example.test/shared/mcp",
      "https://mcp.example.test/shared/mcp",
    ],
  });
});

test("fails closed when no usable HTTP MCP tool is available", () => {
  assert.equal(
    resolveMcpGatewayEnv(
      draft({
        mcpTools: [{ name: "local", transport: "stdio", command: "example" }],
      }),
    ).reason,
    "missing_http_tool",
  );
  assert.equal(
    resolveMcpGatewayEnv(
      draft({ mcpTools: [{ name: "orders", transport: "http", url: "" }] }),
    ).reason,
    "missing_url",
  );
});

test("accepts optional and distinct per-tool credentials", () => {
  const result = resolveMcpGatewayEnv(
    draft({
      mcpTools: [
        {
          name: "orders",
          transport: "http",
          url: "https://mcp.example.test/orders/mcp",
        },
        {
          name: "inventory",
          transport: "http",
          url: "https://mcp.example.test/inventory/mcp",
          authTokenEnv: "MCP_INVENTORY_TOKEN",
        },
      ],
    }),
  );
  assert.deepEqual(result, {
    ok: true,
    urls: [
      "https://mcp.example.test/orders/mcp",
      "https://mcp.example.test/inventory/mcp",
    ],
  });
});
