import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/create/agentNameValidation.ts", import.meta.url),
    ),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
const { agentNameProblem, duplicateAgentNames } = await import(moduleUrl);

test("accepts Google ADK-compatible agent names", () => {
  for (const name of ["agent", "agent_1", "_router", "AgentRouter"]) {
    assert.equal(agentNameProblem(name), null);
  }
});

test("rejects invalid and reserved Google ADK agent names", () => {
  for (const name of ["", "1agent", "agent-name", "agent name", "客服智能体"]) {
    assert.notEqual(agentNameProblem(name), null);
  }
  assert.match(agentNameProblem("user"), /reserved/);
});

test("finds duplicate names across nested agent types", () => {
  const duplicates = duplicateAgentNames({
    name: "root_agent",
    subAgents: [
      { name: "researcher", subAgents: [] },
      {
        name: "parallel_group",
        subAgents: [{ name: "researcher", subAgents: [] }],
      },
    ],
  });

  assert.deepEqual([...duplicates], ["researcher"]);
});
