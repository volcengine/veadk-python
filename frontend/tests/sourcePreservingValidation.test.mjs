import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

// Exercise the actual editor validation without mounting unrelated workbenches.
const source = await readFile(new URL("../src/create/CustomCreate.tsx", import.meta.url), "utf8");
const implementation = source.slice(source.indexOf("function nodeProblem("), source.indexOf("function validationProblemMessage("));
const result = await build({
  stdin: {
    contents: `import { isA2aType, isOrchestratorType } from './agentTypeMeta';
      import { agentNameProblem } from './agentNameValidation';
      import { mcpConfigurationConflict } from './mcpAuth';
      const nodeAcceptsChildren = (n) => !isA2aType(n.agentType);
      ${implementation}
      export { treeProblems };`,
    resolveDir: fileURLToPath(new URL("../src/create/", import.meta.url)),
    loader: "ts",
  },
  bundle: true, format: "esm", platform: "node", write: false,
});
const { treeProblems } = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`);
const draft = (name = "application_agent") => ({ name, agentType: "llm", description: "Runtime-owned agent", instruction: "", subAgents: [], mcpTools: [] });

test("the editor passes its authorized edit mode to validation", () => {
  assert.match(source, /treeProblems\(draft, duplicateNames, \[\], deploymentTarget\?\.editMode\)/);
});

test("source-preserving updates accept runtime-owned dynamic prompts at root and child nodes", () => {
  const root = { ...draft(), subAgents: [draft("child_agent")] };
  assert.deepEqual(treeProblems(root, new Set(), [], "source-preserving"), []);
  assert.equal(root.instruction, "");
  assert.equal(root.subAgents[0].instruction, "");
});
test("ordinary creation and regeneration still require root and child prompts", () => {
  for (const mode of [undefined, "regenerate"]) {
    const problems = treeProblems({ ...draft(), subAgents: [draft("child_agent")] }, new Set(), [], mode);
    assert.deepEqual(problems.map(p => [p.path, p.problem]), [[[], "missingPrompt"], [[0], "missingPrompt"]]);
  }
});
test("source-preserving mode retains identity, description, topology and MCP conflicts", () => {
  const check = (root, duplicateNames = new Set()) => treeProblems(root, duplicateNames, [], "source-preserving").map(p => p.problem);
  assert.deepEqual(check({ ...draft(), name: "" }), ["name.required"]);
  assert.deepEqual(check(draft(), new Set(["application_agent"])), ["duplicateName"]);
  assert.deepEqual(check({ ...draft(), description: "" }), ["missingDescription"]);
  assert.deepEqual(check({ ...draft(), agentType: "sequential" }), ["missingSubagent"]);
  const mcp = { name: "metrics", transport: "http", url: "https://mcp.example.invalid/metrics" };
  assert.deepEqual(check({ ...draft(), mcpTools: [mcp, { ...mcp, url: "https://mcp.example.invalid/other" }] }), ["mcpDuplicateName"]);
  assert.deepEqual(check({ ...draft(), mcpTools: [mcp, { ...mcp, name: "other" }] }), ["mcpDuplicateUrl"]);
});
