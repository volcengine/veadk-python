import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const cardSource = readFileSync(new URL(
  "../src/ui/builtin-tools/CreateAgentToolCards.tsx",
  import.meta.url,
), "utf8");

async function loadCardData() {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(
      "../src/ui/builtin-tools/createAgentToolCardData.ts",
      import.meta.url,
    ))],
    bundle: true,
    format: "cjs",
    platform: "node",
    write: false,
  });
  const module = { exports: {} };
  Function("module", "exports", result.outputFiles[0].text)(module, module.exports);
  return module.exports;
}

test("normalizes collected resources and separates every resource source", async () => {
  const { filterCollectedResourcesByCategory, parseCollectedResources } = await loadCardData();
  const parsed = parseCollectedResources({
    result: {
      collection_id: "collection-1",
      capabilities: {
        google_adk_version: "2.1.0",
        agent_types: ["llm", "workflow"],
        max_orchestration_depth: 2,
      },
      sources: [
        { source: "skill_hub:sp-public", status: "ok", count: 1 },
        { source: "skill_space:private-space", status: "ok", count: 1 },
        { source: "agentkit_knowledge", status: "skipped", count: 0, message: "No STS" },
      ],
      resources: [
        {
          ref: "sp-public:research",
          kind: "skill",
          name: "Research",
          source: "skill_hub:sp-public",
          metadata: { source_type: "skillhub" },
        },
        {
          ref: "private-space:writer",
          kind: "skill",
          name: "Writer",
          source: "skill_space:private-space",
          metadata: { source_type: "skillspace" },
        },
        {
          ref: "knowledge:kb-1",
          kind: "knowledge_base",
          name: "Product docs",
          source: "agentkit_knowledge",
        },
      ],
    },
  });

  assert.equal(parsed.collectionId, "collection-1");
  assert.equal(parsed.capabilities.googleAdkVersion, "2.1.0");
  assert.deepEqual(parsed.counts, {
    all: 3,
    skill_hub: 1,
    skill_space: 1,
    knowledge_base: 1,
  });
  assert.deepEqual(
    parsed.resources.map((resource) => resource.category),
    ["skill_hub", "skill_space", "knowledge_base"],
  );
  assert.deepEqual(
    parsed.sources.map((source) => source.category),
    ["skill_hub", "skill_space", "knowledge_base"],
  );
  assert.equal(parsed.sources[2].status, "skipped");
  assert.deepEqual(
    filterCollectedResourcesByCategory(parsed, "skill_space"),
    {
      resources: [parsed.resources[1]],
      sources: [parsed.sources[1]],
    },
  );
});

test("uses a single-category accordion and keeps implementation hints private", () => {
  assert.match(cardSource, /import \{ Accordion \} from "@base-ui\/react\/accordion"/);
  assert.match(cardSource, /<Accordion\.Root[\s\S]*?defaultValue=\{\[defaultCategory\]\}/);
  assert.match(cardSource, /<Accordion\.Panel/);
  assert.match(cardSource, /filterCollectedResourcesByCategory\(data, item\.value\)/);
  assert.match(cardSource, /AgentKit 技能中心/);
  assert.doesNotMatch(cardSource, /<SegmentedControl/);
  assert.doesNotMatch(cardSource, /Google ADK \$\{data\.capabilities\.googleAdkVersion\}/);
  assert.doesNotMatch(cardSource, /最多嵌套/);
});

test("combines create_agents input blueprints with partial execution results", async () => {
  const { parseCreatedAgents } = await loadCardData();
  const parsed = parseCreatedAgents(
    {
      collection_id: "collection-1",
      agents: [
        {
          name: "research_team",
          task: "Research the market",
          root_node: "pipeline",
          nodes: [
            { id: "pipeline", type: "sequential", children: ["researcher"] },
            {
              id: "researcher",
              type: "llm",
              instruction: "Research",
              resources: ["sp-public:research"],
              python_tools: [{ name: "score", description: "Score", code: "def score(): pass" }],
            },
          ],
        },
        {
          name: "writer",
          task: "Write a brief",
          root_node: "writer",
          nodes: [{ id: "writer", type: "llm", instruction: "Write" }],
        },
      ],
    },
    JSON.stringify({
      collection_id: "collection-1",
      results: [
        { name: "research_team", root_type: "sequential", status: "completed", output: "Done" },
        { name: "writer", root_type: "llm", status: "failed", error: "Model unavailable" },
      ],
    }),
  );

  assert.equal(parsed.completedCount, 1);
  assert.equal(parsed.failedCount, 1);
  assert.deepEqual(parsed.agents[0], {
    name: "research_team",
    task: "Research the market",
    rootType: "sequential",
    nodeCount: 2,
    resourceCount: 1,
    pythonToolCount: 1,
    status: "completed",
    output: "Done",
    error: "",
  });
  assert.equal(parsed.agents[1].error, "Model unavailable");
});
