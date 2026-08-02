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
