import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const typesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/types.ts", import.meta.url),
  "utf8",
);
const tabsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatWorkspaceTabs.tsx", import.meta.url),
  "utf8",
);
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const vibeSource = readFileSync(new URL("../src/adk/vibe.ts", import.meta.url), "utf8");

async function loadVibe() {
  const js = ts.transpileModule(vibeSource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
    .replace('import { withAuth } from "./auth";', "const withAuth = (value) => value;")
    .replace(
      'import { withLocalUser } from "./identity";',
      "const withLocalUser = (value) => value;",
    )
    .replace("return fetch(withAuth(path),", "return globalThis.__apiFetch(withAuth(path),");
  return import(`data:text/javascript;base64,${Buffer.from(js).toString("base64")}`);
}

test("Vibe reuses new-chat workspace and Composer", () => {
  assert.match(typesSource, /"agent" \| "vibe" \| "skill" \| "video"/);
  assert.match(tabsSource, /value: "vibe", label: "Vibe 创建"/);
  assert.match(composerSource, /构建并完成云端验证的 VeADK Agent/);
  assert.match(appSource, /newChatWorkspaceMode === "vibe"/);
  assert.match(appSource, /vibeClient\.create/);
});

test("Vibe client never persists credentials and parses replay events", async (t) => {
  const requests = [];
  globalThis.__apiFetch = async (url, init = {}) => {
    requests.push({ url, init });
    return new Response(JSON.stringify({ taskId: "vt-1", goal: "g", state: "ready" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  t.after(() => delete globalThis.__apiFetch);
  const { vibeClient, parseVibeSse } = await loadVibe();
  await vibeClient.credentials("vt-1", "ak-value", "sk-value");
  assert.equal(requests[0].url, "/web/vibe/tasks/vt-1/credentials");
  assert.equal("localStorage" in requests[0].init, false);
  assert.match(requests[0].init.body, /accessKeyId/);

  const events = parseVibeSse(
    'id: 2\nevent: task.completed\ndata: {"sequence":2,"eventType":"task.completed","stage":"done","timestamp":"now","payload":{}}\n\n',
  );
  assert.equal(events.length, 1);
  assert.equal(events[0].sequence, 2);
  assert.equal(events[0].eventType, "task.completed");
});
