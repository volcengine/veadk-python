import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

globalThis.window = {
  location: {
    search: "",
    pathname: "/",
    hash: "",
    origin: "http://localhost",
  },
  history: { replaceState() {} },
};
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/sandbox.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const { sandboxClient } = await import(moduleUrl);

test("deletes a Codex thread through the standard delete endpoint", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, init };
    return new Response(JSON.stringify({ deleted: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const deleted = await sandboxClient.deleteThread("session/1", "thread-old");

  assert.deepEqual(deleted, { deleted: true });
  assert.equal(
    request.url,
    "/web/sandbox/sessions/session%2F1/threads/delete",
  );
  assert.equal(request.init.method, "POST");
  assert.deepEqual(JSON.parse(request.init.body), { threadId: "thread-old" });
});

test("parses the replacement snapshot after deleting the active thread", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        deleted: true,
        thread: {
          id: "thread-replacement",
          preview: "",
          cwd: "/workspace",
          updatedAt: 2,
        },
        threadId: "thread-replacement",
        messages: [],
        cwd: "/workspace",
        workspaceLocked: false,
        permissions: {
          approvalPolicy: "on-request",
          approvalsReviewer: "user",
          sandboxMode: "workspace-write",
          networkAccess: true,
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );

  const deleted = await sandboxClient.deleteThread("session-1", "thread-active");

  assert.equal(deleted.deleted, true);
  assert.equal(deleted.snapshot.threadId, "thread-replacement");
  assert.equal(deleted.snapshot.thread.id, "thread-replacement");
  assert.equal(deleted.snapshot.cwd, "/workspace");
});

test("sends persistence explicitly for default and temporary agents", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, body: JSON.parse(init.body) });
    return new Response("unavailable", { status: 503 });
  };

  await assert.rejects(() => sandboxClient.startSession({ displayName: "Codex" }));
  await assert.rejects(() =>
    sandboxClient.startAgentSession("openclaw", {
      displayName: "OpenClaw",
      persistent: false,
    }),
  );

  assert.deepEqual(requests, [
    {
      url: "/web/sandbox/sessions",
      body: { displayName: "Codex", persistent: true },
    },
    {
      url: "/web/openclaw/sessions",
      body: { displayName: "OpenClaw", persistent: false },
    },
  ]);
});
