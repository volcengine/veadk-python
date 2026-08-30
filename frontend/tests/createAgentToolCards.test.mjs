import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const cardSource = readFileSync(new URL(
  "../src/ui/builtin-tools/CreateAgentToolCards.tsx",
  import.meta.url,
), "utf8");
const cardStyles = readFileSync(new URL(
  "../src/ui/builtin-tools/create-agent-tool-cards.css",
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

test("uses native status indicators instead of text badges for active and completed states", () => {
  assert.match(
    cardSource,
    /import \{ LoadingIndicator \} from "@openai\/apps-sdk-ui\/components\/Indicator"/,
  );
  assert.match(
    cardSource,
    /import \{ Check \} from "@openai\/apps-sdk-ui\/components\/Icon"/,
  );
  assert.match(cardSource, /<LoadingIndicator[\s\S]*?aria-label="进行中"/);
  assert.match(cardSource, /<Check[\s\S]*?aria-label="已完成"/);
  assert.doesNotMatch(cardSource, /<Badge[^>]*>进行中<\/Badge>/);
  assert.doesNotMatch(cardSource, /<Badge[^>]*>已完成<\/Badge>/);
  assert.doesNotMatch(cardSource, /create-agent-card__summary/);
  assert.doesNotMatch(cardSource, /已完成资源收集/);
  assert.doesNotMatch(cardSource, /来源状态|sourceStatusIndicator/);
  assert.doesNotMatch(cardSource, /create-agent-card__resource-ref/);
  assert.doesNotMatch(cardSource, /<Badge[^>]*>[\s\S]{0,80}\{group\.label\}/);
  assert.match(cardSource, /<Badge[\s\S]*?className="create-agent-card__resource-version"[\s\S]*?>[\s\S]*?\{resource\.version\}/);
  assert.doesNotMatch(cardSource, /版本 \{resource\.version\}/);
  assert.match(cardStyles, /\.create-agent-card__resource-version\s*\{[\s\S]*?font-weight:\s*var\(--font-weight-normal, 400\);/);
  assert.match(cardStyles, /\.create-agent-card__resource-title\s*\{[\s\S]*?align-items:\s*center;/);
  assert.match(cardStyles, /border-bottom:\s*1px dashed hsl\(var\(--border\)/);
  assert.match(cardStyles, /\.create-agent-card__resource p,[\s\S]*?overflow-wrap:\s*anywhere;/);
});

test("bounds expanded resource details in a keyboard-scrollable region", () => {
  assert.match(
    cardSource,
    /className="create-agent-card__accordion-scroll"[\s\S]*?role="region"[\s\S]*?tabIndex=\{0\}/,
  );
  assert.match(
    cardStyles,
    /\.create-agent-card__accordion-scroll\s*\{[\s\S]*?max-height:\s*min\(360px, 52dvh\);[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    cardStyles,
    /\.create-agent-card__accordion-content\s*\{[\s\S]*?height:\s*var\(--accordion-panel-height\);[\s\S]*?transition:/,
  );
  assert.match(
    cardStyles,
    /\.create-agent-card__accordion-content\[data-starting-style\][\s\S]*?height:\s*0;/,
  );
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
