import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/create/agentBuilderConversationStorage.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const {
  loadAgentBuilderConversation,
  writeAgentBuilderConversation,
} = await import(moduleUrl);

function memoryStorage(initial = new Map()) {
  return {
    values: initial,
    getItem(key) {
      return this.values.get(key) ?? null;
    },
    setItem(key, value) {
      this.values.set(key, value);
    },
  };
}

test("persists the visible builder transcript and active conversation", () => {
  const storage = memoryStorage();
  writeAgentBuilderConversation(storage, "builder", {
    conversationId: "agent-builder-123",
    expiresAt: 200,
    messages: [
      { id: "u1", role: "user", text: "做一个客服助手" },
      {
        id: "a1",
        role: "assistant",
        blocks: [{ kind: "text", text: "请补充输入和输出。" }],
      },
    ],
  });

  assert.deepEqual(loadAgentBuilderConversation(storage, "builder", 100), {
    conversationId: "agent-builder-123",
    expiresAt: 200,
    messages: [
      {
        id: "u1",
        role: "user",
        text: "做一个客服助手",
        blocks: undefined,
        streaming: false,
        error: undefined,
      },
      {
        id: "a1",
        role: "assistant",
        text: undefined,
        blocks: [{ kind: "text", text: "请补充输入和输出。" }],
        streaming: false,
        error: undefined,
      },
    ],
  });
});

test("keeps restored messages but drops an expired backend conversation id", () => {
  const storage = memoryStorage();
  writeAgentBuilderConversation(storage, "builder", {
    conversationId: "agent-builder-expired",
    expiresAt: 50,
    messages: [{ id: "u1", role: "user", text: "继续" }],
  });

  const restored = loadAgentBuilderConversation(storage, "builder", 100);
  assert.equal(restored.conversationId, undefined);
  assert.equal(restored.messages[0].text, "继续");
});

test("redacts likely secrets and omits tool arguments from browser storage", () => {
  const storage = memoryStorage();
  writeAgentBuilderConversation(storage, "builder", {
    messages: [
      { id: "u1", role: "user", text: "api_key=sk-sensitive-value" },
      {
        id: "a1",
        role: "assistant",
        blocks: [
          {
            kind: "tool",
            name: "generate_agent",
            args: { apiKey: "sk-tool-secret" },
            response: { token: "hidden" },
            done: true,
          },
        ],
      },
    ],
  });

  const raw = storage.getItem("builder");
  assert.doesNotMatch(raw, /sk-sensitive-value|sk-tool-secret|hidden/);
  assert.match(raw, /api_key=\[已脱敏\]/);
  assert.match(raw, /generate_agent/);
});
