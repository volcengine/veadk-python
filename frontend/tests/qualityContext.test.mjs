import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/adk/quality.ts", import.meta.url))],
  bundle: true, platform: "node", format: "cjs", write: false,
  plugins: [{ name: "quality-client", setup(builder) {
    builder.onResolve({ filter: /^\.\/client$/ }, () => ({ path: "client", namespace: "mock" }));
    builder.onResolve({ filter: /\/create\/skills\/skillspace$/ }, () => ({ path: "skillspace", namespace: "mock" }));
    builder.onResolve({ filter: /\/create\/veadkCatalog$/ }, () => ({ path: "catalog", namespace: "mock" }));
    builder.onLoad({ filter: /.*/, namespace: "mock" }, ({ path }) => ({ contents: path === "catalog" ? 'export const BUILTIN_TOOLS = [];' : path === "skillspace" ? 'export const getSkillDetail = (...args) => globalThis.qualitySkillDetail(...args);' : `
      export const getRuntimeAgentInfo = (...args) => globalThis.qualityRuntimeInfo(...args);
      export const getAgentInfo = (...args) => globalThis.qualityLocalInfo(...args);
      export const getEnvironmentManifest = (...args) => globalThis.qualityEnvironmentManifest(...args);
      export const studioFetch = (...args) => globalThis.qualityFetch(...args);
    ` }));
  } }],
});
const module = { exports: {} };
Function("require", "module", "exports", result.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const { loadQualityAgentContext } = module.exports;

test("suggestions send full Agent context without requiring user-written preferences", async (t) => {
  const body = { agent: { name: "orders", instruction: "Verify order IDs", subAgentDetails: [{ name: "shipping", instruction: "Check the carrier ETA" }] }, runtimeId: "runtime", region: "cn-beijing", language: "zh-CN", field: "goal" };
  const signal = new AbortController().signal;
  globalThis.qualityFetch = async (url, options) => {
    assert.equal(url, "/web/quality/preference-suggestions");
    assert.deepEqual(JSON.parse(options.body), body);
    assert.equal(options.signal, signal);
    return { ok: true, json: async () => ({ suggestions: [{ label: "Verify orders", text: "Check the correct order" }] }) };
  };
  t.after(() => delete globalThis.qualityFetch);
  await module.exports.suggestQualityPreferences(body, signal);
});

test("quality preference generation and reviewed values use the existing generation endpoints", async (t) => {
  const calls = [];
  globalThis.qualityFetch = async (url, options, timeout) => {
    calls.push({ url, body: JSON.parse(options.body), signal: options.signal, timeout });
    return { ok: true, json: async () => ({}) };
  };
  t.after(() => delete globalThis.qualityFetch);
  const signal = new AbortController().signal;
  const common = { agent: { name: "orders" }, runtimeId: "runtime", region: "ap-southeast-1", language: "en-US" };
  const overallPreferences = { name: "Order review", goal: "Verify ETA", scenarios: "Missing IDs", successCriteria: "Use verified information", unacceptableErrors: "Invented dates", preference: "balanced" };
  const componentPreferences = {
    dataset: { preference: "outcome", scenario: "User edited scenario", requirements: "Ask for ID", count: 300 },
    evaluators: { overallFocus: "Task completion", toolsFocus: "Order lookup", skillsFocus: "Not applicable", criteria: "User edited criteria", strictness: "strict" },
  };
  await module.exports.generateQualityPreferences({ ...common, overallPreferences }, signal);
  const reviewed = { ...common, overallPreferences, componentPreferences };
  await module.exports.generateQualityDataset({ ...reviewed, ...componentPreferences.dataset }, signal);
  await module.exports.generateQualityEvaluators(reviewed, signal);
  assert.deepEqual(calls.map(call => call.url), ["/web/quality/preferences", "/web/quality/generate", "/web/quality/evaluators"]);
  assert.deepEqual(calls[0].body, { ...common, overallPreferences });
  assert.deepEqual(calls[1].body, { ...reviewed, ...componentPreferences.dataset });
  assert.deepEqual(calls[2].body, reviewed);
  assert.ok(calls.every(call => call.signal === signal));
  assert.equal(calls[1].timeout, 760000);
  assert.equal(calls[2].timeout, 190000);
});

const draft = () => ({
  name: "orders", description: "Track customer orders", instruction: "Verify order IDs before giving an ETA",
  tools: ["lookup_order"], skills: [], subAgents: [],
  customTools: [{ name: "lookup_order", description: "Return order status and carrier ETA" }],
  selectedSkills: [{ name: "order_report", folder: "order_report", description: "Present status, ETA and uncertainties", localFiles: [{ path: ".env", content: "private-skill-file" }] }],
  deployment: { envValues: { API_KEY: "private-env-value" } },
  mcpTools: [{ name: "order-service", transport: "http", url: "https://private.example", authToken: "private-token" }],
});

test("quality context retains capability descriptions and child responsibilities without configuration secrets", async () => {
  const input = draft();
  input.subAgents = [{ ...draft(), name: "shipping", instruction: "Verify carrier estimates", subAgents: [] }];
  const context = await loadQualityAgentContext({ info: null, draft: input }, new AbortController().signal);
  assert.equal(context.toolDetails[0].description, input.customTools[0].description);
  assert.deepEqual(context.skills, ["order_report"]);
  assert.equal(context.skillDetails[0].description, input.selectedSkills[0].description);
  assert.equal(context.subAgentDetails[0].instruction, "Verify carrier estimates");
  assert.deepEqual(context.subAgentDetails[0].path, ["orders", "shipping"]);
  assert.doesNotMatch(JSON.stringify(context), /private-/);
});

test("deployed context joins the normal metadata request and does not restore removed capabilities from the editor draft", async (t) => {
  const fresh = { name: "live", description: "Live role", tools: [], skills: [{ name: "live_skill", description: "Live requirements" }], skillsPreviewSupported: true, subAgents: [], draft: draft() };
  globalThis.qualityRuntimeInfo = async (...args) => {
    assert.deepEqual(args, ["runtime-1", "ap-southeast-1", "live-app"]);
    return fresh;
  };
  t.after(() => delete globalThis.qualityRuntimeInfo);
  const context = await loadQualityAgentContext({ runtimeId: "runtime-1", region: "ap-southeast-1", appName: "live-app", info: null, draft: draft() }, new AbortController().signal);
  assert.deepEqual(context.tools, []);
  assert.deepEqual(context.toolDetails, []);
  assert.equal(context.skillDetails[0].description, "Live requirements");
  assert.equal(context.skillDetails[0].source, "runtime");
  assert.deepEqual(context.subAgentDetails, []);
});

test("loaded runtime details are reused with their full prompt and mounted capabilities", async (t) => {
  globalThis.qualityRuntimeInfo = async () => { throw Error("Unexpected repeated metadata request"); };
  t.after(() => delete globalThis.qualityRuntimeInfo);
  const info = { name: "live", appName: "actual-app", tools: ["lookup_order"], skills: [], subAgents: [], draft: draft() };
  for (const region of ["cn-beijing", "ap-southeast-1"]) {
    const context = await loadQualityAgentContext({ runtimeId: "runtime-1", region, info, draft: { ...draft(), instruction: "Unpublished editor changes" } }, new AbortController().signal);
    assert.equal(context.instruction, info.draft.instruction);
    assert.deepEqual(context.tools, ["lookup_order"]);
    assert.equal(context.toolDetails[0].description, "Return order status and carrier ETA");
  }
});

test("quality context preserves nested runtime ownership and bounds long descriptions", async () => {
  const child = { name: "shipping", description: "x".repeat(8000), instruction: "Check delivery windows", type: "llm", tools: ["carrier"], skills: [], children: [] };
  const root = { name: "orders", type: "sequential", children: [{ ...child, name: "dispatch", children: [child] }] };
  const context = await loadQualityAgentContext({ info: { name: "orders", tools: [], skills: [], subAgents: ["dispatch"], graph: root }, draft: draft() }, new AbortController().signal);
  assert.equal(context.type, "sequential");
  assert.deepEqual(context.subAgentDetails[1].path, ["orders", "dispatch", "shipping"]);
  assert.equal(context.subAgentDetails[1].description.length, 8000);
  assert.equal(context.subAgentDetails[1].instruction, "Check delivery windows");
  assert.deepEqual(context.subAgentDetails[1].tools, ["carrier"]);
});

test("all topology nodes retain ordered ownership, knowledge bases, memory and prompts beyond twenty children", async () => {
  const graph = {
    name: "orders", type: "sequential", tools: [], skills: [], components: [],
    children: Array.from({ length: 25 }, (_, index) => ({ name: `worker_${index}`, type: "llm", instruction: `Only use policy ${index}`, model: "test-model", tools: ["lookup_order"], skills: [],
      components: [{ kind: "knowledgebase", name: `policy_${index}`, description: `Policy for region ${index}`, backend: "viking", source: "knowledgebase", secret: "private-component-secret" }], children: [] })),
  };
  const context = await loadQualityAgentContext({ info: { name: "orders", graph, components: [], tools: [], skills: [], subAgents: graph.children.map(child => child.name) }, draft: draft() }, new AbortController().signal);
  assert.equal(context.subAgentDetails.length, 25);
  assert.equal(context.children[24], "root/24");
  assert.equal(context.subAgentDetails[24].parentId, "root");
  assert.equal(context.subAgentDetails[24].instruction, "Only use policy 24");
  assert.equal(context.subAgentDetails[24].components[0].name, "policy_24");
  assert.equal(context.subAgentDetails[24].components[0].provenance, "runtime");
  assert.deepEqual(context.components, []);
  assert.doesNotMatch(JSON.stringify(context), /private-component-secret/);
});

test("workflow-only drafts retain edges and resource settings without secrets", async () => {
  const input = { ...draft(), agentType: "parallel", knowledgebase: true, knowledgebaseBackend: "viking", knowledgebaseIndex: "refund-policy", memory: { shortTerm: true, longTerm: false },
    workflow: { type: "custom", nodes: [{ id: "lookup", agent: { ...draft(), name: "lookup" } }, { id: "review", agent: { ...draft(), name: "review" } }], edges: [{ from: "lookup", to: "review" }] },
  };
  const context = await loadQualityAgentContext({ info: null, draft: input }, new AbortController().signal);
  assert.deepEqual(context.configuredWorkflow.edges, [{ from: "root/0", to: "root/1" }]);
  assert.equal(context.components[0].name, "refund-policy");
  assert.equal(context.components[0].provenance, "draft");
  assert.equal(context.configuration.find(item => item.name === "memory.longTerm").value, "false");
  assert.deepEqual(context.mcpServers, [{ name: "order-service", transport: "http" }]);
  assert.doesNotMatch(JSON.stringify(context), /private-/);
});

test("reads only the bound environment and exact Skill version with cancellation support", async (t) => {
  const controller = new AbortController();
  const input = { ...draft(), cloudEnvironment: { environmentId: "env-1", environmentVersionId: "version-2" }, selectedSkills: [{ name: "order_report", folder: "order_report", source: "skillspace", skillSpaceId: "space-1", skillId: "skill-1", version: "v2", skillSpaceRegion: "ap-southeast-1" }] };
  globalThis.qualityEnvironmentManifest = async (...args) => {
    assert.deepEqual(args, ["env-1", "version-2", controller.signal]);
    return { metadata: { name: "Order environment", description: "Prepare reports" }, spec: { capabilities: ["document-processing"], skills: [{ name: "pdf-report", version: "v1" }], image: "private-image" } };
  };
  globalThis.qualitySkillDetail = async (...args) => {
    assert.deepEqual(args, ["space-1", "skill-1", "v2", "ap-southeast-1", undefined, undefined, undefined, controller.signal]);
    return { skillMd: "# Report\nCite order IDs", description: "Order reporting" };
  };
  t.after(() => { delete globalThis.qualityEnvironmentManifest; delete globalThis.qualitySkillDetail; });
  const context = await loadQualityAgentContext({ info: null, draft: input }, controller.signal);
  assert.equal(context.skillDetails[0].instructions, "# Report\nCite order IDs");
  assert.equal(context.environments[0].skills[0].name, "pdf-report");
  assert.doesNotMatch(JSON.stringify(context), /private-image/);
});

test("generation errors preserve the complete diagnostic text returned by the server", async (t) => {
  const diagnostics = "request-id: test-request\n" + "provider detail\n".repeat(10000) + "LAST CLOUD LOG LINE";
  globalThis.qualityFetch = async () => Response.json({ detail: { code: "quality_generation_failed", diagnostics } }, { status: 502 });
  t.after(() => delete globalThis.qualityFetch);
  await assert.rejects(module.exports.generateQualityEvaluators({ agent: {} }, new AbortController().signal), error => error.code === "failed" && error.diagnostics === diagnostics);
});
