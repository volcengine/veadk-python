import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/create/agentNameValidation.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
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
  assert.match(agentNameProblem("user"), /保留名称/);
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
