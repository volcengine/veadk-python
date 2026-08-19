import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const createSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const chatSource = readFileSync(
  new URL("../src/create/AgentBuilderChatPanel.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("intelligent Agent creation uses a persistent multi-turn SSE conversation", () => {
  assert.match(
    clientSource,
    /createGeneratedAgentConversation[\s\S]*?"\/web\/generated-agent-conversations"/,
  );
  assert.match(
    clientSource,
    /runGeneratedAgentConversationSSE[\s\S]*?generated-agent-conversations\/\$\{encodeURIComponent\(conversationId\)\}\/run_sse/,
  );
  assert.match(createSource, /runGeneratedAgentConversationSSE\(/);
  assert.match(createSource, /applyEvent\(acc, event\)/);
  assert.match(
    createSource,
    /agentBuilderMountedRef\.current = false;[\s\S]*?queueMicrotask\([\s\S]*?!agentBuilderMountedRef\.current[\s\S]*?agentBuilderAbortRef\.current\?\.abort\(\)/,
  );
});

test("the canvas changes only after the backend emits an agent_draft event", () => {
  const conversationHandler = createSource.slice(
    createSource.indexOf("const runAgentBuilderConversation"),
    createSource.indexOf("const addCanvasStep"),
  );
  assert.match(
    conversationHandler,
    /eventType === "agent_draft"[\s\S]*?applyGeneratedAgentDraft\([\s\S]*?\.draft/,
  );
  assert.match(createSource, /normalizeDraft\(generatedDraft\)/);
  assert.doesNotMatch(conversationHandler, /generateAgentDraftFromRequirement/);
});

test("the chat panel renders real message history instead of generated placeholders", () => {
  assert.match(chatSource, /messages\.map\(\(message\) =>/);
  assert.match(chatSource, /blocks=\{message\.blocks \?\? \[\]\}/);
  assert.doesNotMatch(chatSource, /智能体配置已更新。你可以继续/);
  assert.doesNotMatch(chatSource, /generated:\s*boolean/);
});

test("builder transcripts restore from user-and-draft-scoped browser storage", () => {
  assert.match(createSource, /loadAgentBuilderConversation\(localStorage/);
  assert.match(createSource, /writeAgentBuilderConversation\(localStorage/);
  assert.match(
    createSource,
    /window\.setTimeout\([\s\S]*?writeAgentBuilderConversation\([\s\S]*?AGENT_BUILDER_PERSIST_DEBOUNCE_MS/,
  );
  assert.match(createSource, /window\.clearTimeout\(timer\)/);
  assert.match(
    appSource,
    /agentBuilderStorageKey=\{[\s\S]*?workspaceDraftsKey\(userId\)[\s\S]*?encodeURIComponent\(editingDraftId\)/,
  );
});
