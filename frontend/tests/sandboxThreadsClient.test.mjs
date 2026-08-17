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

globalThis.window = Object.assign(new EventTarget(), {
  location: {
    search: "",
    pathname: "/",
    hash: "",
    origin: "http://localhost",
  },
  history: { replaceState() {} },
});
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();

const result = await build({
  stdin: {
    contents: `
      export { sandboxClient } from "./src/adk/sandbox.ts";
      export {
        AUTHENTICATION_REQUIRED_EVENT,
        authenticationRestored,
      } from "./src/adk/authSession.ts";
    `,
    resolveDir: fileURLToPath(new URL("..", import.meta.url)),
  },
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const {
  AUTHENTICATION_REQUIRED_EVENT,
  authenticationRestored,
  sandboxClient,
} = await import(moduleUrl);

test("retries a sandbox message after Studio authentication is restored", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    authenticationRestored();
  });
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, init });
    if (requests.length === 1) {
      const loginPage = new Response("<html>login</html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      });
      Object.defineProperties(loginPage, {
        redirected: { value: true },
        url: { value: "https://example.userpool.auth.example.com/oauth2/login" },
      });
      return loginPage;
    }
    return new Response(
      [
        'event: delta\ndata: {"text":"恢复成功"}',
        "event: done\ndata: {}",
        "",
      ].join("\n\n"),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
  };

  const authenticationRequired = new Promise((resolve) => {
    window.addEventListener(AUTHENTICATION_REQUIRED_EVENT, resolve, {
      once: true,
    });
  });
  const pending = sandboxClient.sendMessage({
    sessionId: "session-1",
    text: "你好",
  });
  await authenticationRequired;
  authenticationRestored();

  const result = await pending;

  assert.equal(result.text, "恢复成功");
  assert.equal(requests.length, 2);
  assert.equal(requests[0].url, "/web/sandbox/sessions/session-1/messages");
  assert.equal(requests[1].url, requests[0].url);
  assert.equal(requests[1].init.body, requests[0].init.body);
});

test("retries sandbox settings after a confirmed expired Studio session", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    authenticationRestored();
  });
  const settingsUrl = "/web/sandbox/sessions/session-1/settings";
  let settingsRequests = 0;
  globalThis.fetch = async (url) => {
    if (url === settingsUrl) {
      settingsRequests += 1;
      if (settingsRequests === 1) return new Response("", { status: 401 });
      return Response.json({
        threadId: "thread-1",
        cwd: "/workspace",
        workspaceLocked: false,
        busy: false,
      });
    }
    if (url === "/oauth2/userinfo") {
      return new Response("", { status: 401 });
    }
    if (url === "/web/auth-config") {
      return Response.json({
        providers: [
          { id: "oidc", label: "SSO", loginUrl: "/oauth2/login" },
        ],
      });
    }
    throw new Error(`unexpected request: ${url}`);
  };

  const authenticationRequired = new Promise((resolve) => {
    window.addEventListener(AUTHENTICATION_REQUIRED_EVENT, resolve, {
      once: true,
    });
  });
  const pending = sandboxClient.getSettings("session-1");
  await authenticationRequired;
  authenticationRestored();

  const settings = await pending;

  assert.equal(settings.threadId, "thread-1");
  assert.equal(settings.cwd, "/workspace");
  assert.equal(settingsRequests, 2);
});

test("reads a Codex thread without activating it", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, init };
    return new Response(
      JSON.stringify({
        thread: {
          id: "thread/old",
          preview: "continue work",
          cwd: "/workspace",
          updatedAt: 2,
        },
        threadId: "thread/old",
        messages: [
          {
            id: "message-1",
            role: "user",
            content: "continue work",
            timestamp: 2,
            images: [
              {
                mimeType: "image/png",
                data: "iVBORw0KGgppbWFnZQ==",
                name: "handoff.png",
                alt: "端云接力界面",
              },
            ],
          },
        ],
        cwd: "/workspace",
        workspaceLocked: true,
        permissions: {
          approvalPolicy: "never",
          approvalsReviewer: "user",
          sandboxMode: "workspace-write",
          networkAccess: true,
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };

  const snapshot = await sandboxClient.readThread("session/1", "thread/old");

  assert.equal(snapshot.threadId, "thread/old");
  assert.equal(snapshot.messages[0].content, "continue work");
  assert.deepEqual(snapshot.messages[0].images, [
    {
      mimeType: "image/png",
      data: "iVBORw0KGgppbWFnZQ==",
      name: "handoff.png",
      alt: "端云接力界面",
    },
  ]);
  assert.equal(
    request.url,
    "/web/sandbox/sessions/session%2F1/threads/thread%2Fold",
  );
  assert.equal(request.init.method, "GET");
});

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
  await assert.rejects(() =>
    sandboxClient.startAgentSession("deepseek-harness", {
      displayName: "DeepSeek Harness",
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
    {
      url: "/web/deepseek-harness/sessions",
      body: { displayName: "DeepSeek Harness", persistent: true },
    },
  ]);
});
