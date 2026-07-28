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

test("preserves generated capabilities on every nested Agent", () => {
  const start = normalizeSource.indexOf("function parseSubAgents");
  const end = normalizeSource.indexOf("function parseSelectedSkills");
  const parser = normalizeSource.slice(start, end);

  for (const field of [
    "modelName",
    "builtinTools",
    "memory",
    "shortTermBackend",
    "longTermBackend",
    "autoSaveSession",
    "knowledgebase",
    "knowledgebaseBackend",
    "tracing",
    "tracingExporters",
    "subAgents",
  ]) {
    assert.match(parser, new RegExp(`\\b${field}:`));
  }
  assert.match(parser, /subAgents: parseSubAgents\(so\.subAgents\)/);
});

test("feeds normalized generated tool ids into the checklist selection", () => {
  assert.match(createSource, /setDraft\(normalizeDraft\(result\.draft\)\)/);
  assert.match(createSource, /items=\{BUILTIN_TOOLS\}/);
  assert.match(createSource, /selected=\{builtinTools\}/);
});

test("allows Agent generation to outlive the default request timeout", () => {
  assert.match(clientSource, /GENERATED_AGENT_DRAFT_TIMEOUT_MS = 190_000/);
  assert.match(
    clientSource,
    /apiFetch\([\s\S]*?"\/web\/generated-agent-drafts"[\s\S]*?GENERATED_AGENT_DRAFT_TIMEOUT_MS/,
  );
});

test("dims the input and animates the smoke while generation is active", () => {
  assert.match(
    createStyles,
    /\.cw-ai-compose\.is-generating \.cw-ai-compose-form\s*\{[\s\S]*?background: rgba\(235, 235, 240, 0\.9\)/,
  );
  assert.match(createStyles, /\.cw-ai-compose\.is-generating::before/);
  assert.match(createStyles, /animation: cw-ai-banner-smoke-a 7s/);
  assert.match(createStyles, /animation: cw-ai-banner-smoke-b 8\.5s/);
});
