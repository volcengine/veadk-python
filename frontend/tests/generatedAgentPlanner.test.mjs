import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const normalizeSource = readFileSync(
  new URL("../src/create/normalizeDraft.ts", import.meta.url),
  "utf8",
);
const createSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const createStyles = readFileSync(
  new URL("../src/create/CustomCreate.css", import.meta.url),
  "utf8",
);

test("removes hidden capabilities from every generated Agent", () => {
  const start = normalizeSource.indexOf(
    "export function sanitizeGeneratedDraftCapabilities",
  );
  const sanitizer = normalizeSource.slice(start);

  assert.match(sanitizer, /GENERATED_TOOL_IDS\.has\(toolId\)/);
  assert.match(sanitizer, /tracing: false/);
  assert.match(sanitizer, /tracingExporters: \[\]/);
  assert.match(sanitizer, /memory: \{ shortTerm: false, longTerm: false \}/);
  assert.match(sanitizer, /shortTermBackend: "local"/);
  assert.match(sanitizer, /longTermBackend: "local"/);
  assert.match(sanitizer, /autoSaveSession: false/);
  assert.match(sanitizer, /knowledgebase: false/);
  assert.match(sanitizer, /knowledgebaseBackend: DEFAULT_KB_BACKEND/);
  assert.match(sanitizer, /knowledgebaseIndex: ""/);
  assert.match(
    sanitizer,
    /subAgents: draft\.subAgents\.map\(sanitizeGeneratedDraftCapabilities\)/,
  );
  assert.match(
    createSource,
    /setDraft\(sanitizeGeneratedDraftCapabilities\(normalizeDraft\(result\.draft\)\)\)/,
  );
});

test("keeps OpenViking long-term memory when normalizing imported drafts", () => {
  assert.match(normalizeSource, /"openviking"/);
});

test("feeds supported generated tool ids into the checklist selection", () => {
  assert.match(createSource, /items=\{CREATE_BUILTIN_TOOLS\}/);
  assert.match(createSource, /selected=\{builtinTools\}/);
});

test("allows Agent generation to outlive the default request timeout", () => {
  assert.match(clientSource, /GENERATED_AGENT_DRAFT_TIMEOUT_MS = 190_000/);
  assert.match(
    clientSource,
    /apiFetch\([\s\S]*?"\/web\/generated-agent-drafts"[\s\S]*?GENERATED_AGENT_DRAFT_TIMEOUT_MS/,
  );
});

test("dims the input and shows a spinner while generation is active", () => {
  assert.match(
    createStyles,
    /\.cw-ai-compose\.is-generating \.cw-ai-compose-form\s*\{[\s\S]*?background: hsl\(var\(--muted\) \/ 0\.7\)/,
  );
  assert.match(createStyles, /\.cw-ai-orb\s*\{[\s\S]*?animation: cw-ai-orb-spin 720ms linear infinite/);
  assert.match(createStyles, /@keyframes cw-ai-orb-spin/);
});

test("names the planner model and preserves generation errors verbatim", () => {
  assert.match(
    createSource,
    /placeholder="描述目标，使用 doubao-seed-2-0-lite-260428 模型一键生成配置"/,
  );
  assert.match(
    createSource,
    /setAiErrorDialog\(\s*error instanceof Error \? error\.message : String\(error\),?\s*\)/,
  );
  assert.doesNotMatch(
    createSource,
    /error instanceof Error \? error\.message : "生成 Agent 配置失败"/,
  );
});

test("validates short generation requirements beside the input before requesting", () => {
  const handler = createSource.slice(
    createSource.indexOf("const handleGenerateDraft"),
    createSource.indexOf("const addCanvasStep"),
  );

  assert.match(createSource, /const GENERATED_AGENT_REQUIREMENT_MIN_LENGTH = 4/);
  assert.match(
    handler,
    /if \(requirement\.length < GENERATED_AGENT_REQUIREMENT_MIN_LENGTH\) return/,
  );
  assert.match(
    createSource,
    /const aiRequirementError =[\s\S]*?"请至少输入 4 个字符。"/,
  );
  assert.ok(
    handler.indexOf(
      "requirement.length < GENERATED_AGENT_REQUIREMENT_MIN_LENGTH",
    ) <
      handler.indexOf("generateAgentDraftFromRequirement(requirement)"),
  );
  assert.match(createSource, /aria-invalid=\{Boolean\(aiRequirementError\)\}/);
  assert.match(
    createSource,
    /aria-describedby=\{\s*aiRequirementError \? "ai-requirement-error" : undefined\s*\}/,
  );
  assert.match(
    createSource,
    /id="ai-requirement-error"[\s\S]*?role="alert"[\s\S]*?\{aiRequirementError\}/,
  );
  assert.match(createStyles, /\.cw-ai-requirement-error\s*\{/);
});
