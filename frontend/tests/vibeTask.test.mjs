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
const workspaceSource = readFileSync(
  new URL("../src/ui/vibe/VibeTaskWorkspace.tsx", import.meta.url),
  "utf8",
);

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
  assert.match(appSource, /<VibeTaskWorkspace/);
  assert.match(appSource, /vibeClient\.list\(controller\.signal\)/);
  assert.match(workspaceSource, /StudioConfirmDialog/);
  assert.match(workspaceSource, /Session Token（可选）/);
  assert.match(tabsSource, /End"\) nextIndex = visibleModes\.length - 1/);
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
  await vibeClient.create("build", "12345678-1234-5678-9234-567812345678");
  assert.deepEqual(JSON.parse(requests[0].init.body), {
    goal: "build",
    requestId: "12345678-1234-5678-9234-567812345678",
  });
  await vibeClient.credentials(
    "vt-1",
    "ak-value",
    "sk-value",
    "token-value",
    "12345678-1234-5678-9234-567812345678",
  );
  assert.equal(requests[1].url, "/web/vibe/tasks/vt-1/credentials");
  assert.equal("localStorage" in requests[1].init, false);
  assert.deepEqual(JSON.parse(requests[1].init.body), {
    commandId: "12345678-1234-5678-9234-567812345678",
    accessKeyId: "ak-value",
    secretAccessKey: "sk-value",
    sessionToken: "token-value",
  });

  const events = parseVibeSse(
    'id: 2\nevent: task.completed\ndata: {"sequence":2,"eventType":"task.completed","stage":"done","timestamp":"now","payload":{}}\n\n',
  );
  assert.equal(events.length, 1);
  assert.equal(events[0].sequence, 2);
  assert.equal(events[0].eventType, "task.completed");
});

test("Vibe SSE buffers split frames and resumes with Last-Event-ID", async (t) => {
  const requests = [];
  const encoder = new TextEncoder();
  globalThis.__apiFetch = async (url, init = {}) => {
    requests.push({ url, init });
    if (url.endsWith("/events")) {
      return new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('id: 5\nevent: task.running\ndata: {"sequence":5,"eventType":"task.'));
          controller.enqueue(encoder.encode('running","stage":"building","timestamp":"now","payload":{}}\n\n'));
          controller.close();
        },
      }), { headers: { "content-type": "text/event-stream" } });
    }
    return new Response(JSON.stringify({ taskId: "vt-1", state: "completed" }), {
      headers: { "content-type": "application/json" },
    });
  };
  t.after(() => delete globalThis.__apiFetch);
  const { streamVibeEvents } = await loadVibe();
  const controller = new AbortController();
  const events = [];
  for await (const event of streamVibeEvents("vt-1", { after: 4, signal: controller.signal })) {
    events.push(event);
  }
  assert.equal(events.length, 1);
  assert.equal(events[0].sequence, 5);
  assert.equal(new Headers(requests[0].init.headers).get("Last-Event-ID"), "4");
});
