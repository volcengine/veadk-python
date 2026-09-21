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
    fileURLToPath(new URL("../src/adk/client.ts", import.meta.url)),
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
const {
  clearRemoteApps,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  continueTurn,
  continueTurnSSE,
  registerRemoteApp,
  runSseFirstEventTimeoutError,
  runSSE,
  getAgentInfo,
} = await import(moduleUrl);

test("createSession uses the MPA instance id instead of the Runtime id", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    mpaInstanceId: "mi-agent-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (String(url).includes("/profile-status")) {
      return Response.json({
        operationId: "op-1",
        status: "applied",
        profileRevision: 12,
        runtimeRevision: "v1",
        etag: "12",
      });
    }
    return Response.json({ sessionId: "session-1" });
  };

  const sessionId = await createSession("mpa-agent", "user");

  assert.equal(sessionId, "session-1");
  assert.equal(captured.length, 2);
  assert.match(
    captured[0].url,
    /\/web\/runtime-proxy\/r-runtime-1\/api\/v1\/agents\/mi-agent-1\/profile-status/,
  );
  assert.deepEqual(captured[1].body, {
    mpaInstanceId: "mi-agent-1",
    profileRevision: 12,
  });
});

test("createSession hydrates the MPA instance id for cached Runtime connections", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (String(url).includes("/web/runtime-detail")) {
      return Response.json({
        runtimeId: "r-runtime-1",
        mpaInstanceId: "mi-agent-from-detail",
        name: "mi-agent-from-detail",
        description: "",
        status: "Ready",
        statusMessage: "",
        model: "",
        project: "default",
        region: "cn-beijing",
        createdAt: "",
        updatedAt: "",
        resources: {},
        envs: [],
        memoryId: "",
        toolId: "",
        knowledgeId: "",
        mcpToolsetId: "",
        artifactUrl: "",
        artifactType: "",
        networkTypes: [],
        endpoint: "",
        authType: "key_auth",
      });
    }
    if (String(url).includes("/profile-status")) {
      return Response.json({
        operationId: "op-1",
        status: "applied",
        profileRevision: 13,
        runtimeRevision: "v2",
        etag: "13",
      });
    }
    return Response.json({ id: "session-2" });
  };

  const sessionId = await createSession("mpa-agent", "user");

  assert.equal(sessionId, "session-2");
  assert.equal(captured.length, 3);
  assert.match(captured[0].url, /\/web\/runtime-detail\?/);
  assert.match(
    captured[1].url,
    /\/web\/runtime-proxy\/r-runtime-1\/api\/v1\/agents\/mi-agent-from-detail\/profile-status/,
  );
  assert.deepEqual(captured[2].body, {
    mpaInstanceId: "mi-agent-from-detail",
    profileRevision: 13,
  });
});

test("createSession continues with profile revision zero when MPA profile is absent", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    mpaInstanceId: "mi-agent-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (String(url).includes("/profile-status")) {
      return Response.json(
        { detail: { code: "profile_not_found", message: "profile_not_found" } },
        { status: 404 },
      );
    }
    return Response.json({ sessionId: "session-1" }, { status: 201 });
  };

  const sessionId = await createSession("mpa-agent", "user");

  assert.equal(sessionId, "session-1");
  assert.equal(captured.length, 2);
  assert.deepEqual(captured[1].body, {
    mpaInstanceId: "mi-agent-1",
    profileRevision: 0,
  });
});

test("listSessions uses the native MPA Runtime session API", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init = {}) => {
    captured.push({
      url: String(url),
      method: init.method ?? "GET",
    });
    return Response.json({
      sessions: [
        {
          id: "session-1",
          appName: "default",
          userId: "agentkit-key-auth",
          lastUpdateTime: 1789630185,
          title: "done",
          status: "idle",
        },
      ],
    });
  };

  const sessions = await listSessions("mpa-agent", "studio-user");

  assert.equal(sessions.length, 1);
  assert.equal(sessions[0].id, "session-1");
  assert.equal(captured.length, 1);
  assert.match(
    captured[0].url,
    /\/web\/runtime-proxy\/r-runtime-1\/api\/v1\/sessions\?_runtime_region=cn-beijing$/,
  );
  assert.equal(captured[0].method, "GET");
});

test("listSessions explains legacy MPA Runtime auth failures", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-legacy",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  globalThis.fetch = async () =>
    Response.json(
      { detail: "X-Jwt-Token header is required" },
      { status: 401 },
    );

  await assert.rejects(
    () => listSessions("mpa-agent", "studio-user"),
    /older authentication adapter[\s\S]*X-Jwt-Token header is required/,
  );
});

test("getAgentInfo falls back to A2A metadata when Runtime default agent-info is absent", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-a2a",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    const path = String(url);
    if (path.includes("/web/agent-info/default")) {
      return Response.json({ detail: "Not Found" }, { status: 404 });
    }
    if (path.includes("/web/agent-info/a2a-default")) {
      return Response.json({
        name: "default",
        description: "A2A metadata",
        type: "a2a",
        model: "model-a",
        tools: [],
        skills: [],
        subAgents: [],
      });
    }
    throw new Error(`unexpected URL: ${path}`);
  };

  const info = await getAgentInfo("mpa-agent");

  assert.equal(info.name, "default");
  assert.equal(info.type, "a2a");
  assert.equal(info.model, "model-a");
  assert.match(urls[0], /\/web\/agent-info\/default/);
  assert.match(urls[1], /\/web\/agent-info\/a2a-default/);
});

test("listSessions treats legacy MPA Runtime connections with mpaInstanceId as native MPA", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    mpaInstanceId: "mi-agent-1",
    region: "cn-beijing",
  });

  const captured = [];
  globalThis.fetch = async (url, init = {}) => {
    captured.push({
      url: String(url),
      method: init.method ?? "GET",
    });
    return Response.json({ sessions: [] });
  };

  await listSessions("mpa-agent", "studio-user");

  assert.equal(captured.length, 1);
  assert.match(captured[0].url, /\/api\/v1\/sessions\?_runtime_region=cn-beijing$/);
  assert.doesNotMatch(captured[0].url, /\/apps\/default\/users\/studio-user\/sessions/);
});

test("getSession hydrates MPA Runtime session events from the native events API", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init = {}) => {
    captured.push({
      url: String(url),
      method: init.method ?? "GET",
    });
    if (String(url).includes("/api/v1/sessions/session-1/events")) {
      return Response.json({
        events: [
          {
            id: "event-1",
            author: "default",
            partial: false,
            content: { parts: [{ text: "done" }] },
          },
        ],
      });
    }
    return Response.json({
      id: "session-1",
      appName: "default",
      userId: "agentkit-key-auth",
      lastUpdateTime: 1789630185,
      title: "done",
      status: "idle",
    });
  };

  const session = await getSession("mpa-agent", "studio-user", "session-1");

  assert.equal(session.id, "session-1");
  assert.equal(session.events.length, 1);
  assert.equal(session.events[0].id, "event-1");
  assert.equal(captured.length, 2);
  assert.match(
    captured[0].url,
    /\/web\/runtime-proxy\/r-runtime-1\/api\/v1\/sessions\/session-1\?_runtime_region=cn-beijing$/,
  );
  assert.match(
    captured[1].url,
    /\/web\/runtime-proxy\/r-runtime-1\/api\/v1\/sessions\/session-1\/events\?_runtime_region=cn-beijing$/,
  );
});

test("deleteSession uses the native MPA Runtime session API", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "r-runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init = {}) => {
    captured.push({
      url: String(url),
      method: init.method ?? "GET",
    });
    return Response.json({ sessionId: "session-1" });
  };

  await deleteSession("mpa-agent", "studio-user", "session-1");

  assert.equal(captured.length, 1);
  assert.match(
    captured[0].url,
    /\/web\/runtime-proxy\/r-runtime-1\/api\/v1\/sessions\/session-1\?_runtime_region=cn-beijing&_method=DELETE$/,
  );
  assert.equal(captured[0].method, "POST");
});

test("runSSE forwards cancellation after yielding partial output", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  let requestSignal;
  globalThis.fetch = async (_url, init) => {
    requestSignal = init.signal;
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(
            'data: {"partial":true,"content":{"parts":[{"text":"part"}]}}\n\n',
          ),
        );
        init.signal.addEventListener(
          "abort",
          () => {
            controller.error(
              init.signal.reason ?? new DOMException("Aborted", "AbortError"),
            );
          },
          { once: true },
        );
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  };

  const abortController = new AbortController();
  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
    signal: abortController.signal,
  });

  const first = await events.next();
  assert.equal(first.done, false);
  assert.equal(first.value.partial, true);
  assert.equal(first.value.content.parts[0].text, "part");
  assert.ok(requestSignal instanceof AbortSignal);
  assert.equal(requestSignal.aborted, false);

  const next = events.next();
  abortController.abort(new DOMException("Stopped by user", "AbortError"));

  await assert.rejects(next, (error) => {
    assert.equal(error.name, "AbortError");
    return true;
  });
});

test("runSSE forwards execution idempotency headers and metadata through the local BFF", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      headers: new Headers(init.headers),
      body: JSON.parse(String(init.body)),
    });
    if (String(url).includes("/api/v1/sessions/session/run")) {
      return Response.json({
        sessionId: "session",
        invocationId: "e-accepted",
        turnId: "turn-accepted",
        operationId: "op-accepted",
        executionConfigRevision: 7,
      });
    }
    return new Response(
      'data: {"partial":true,"content":{"parts":[{"text":"accepted"}]}}\n\n',
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
    idempotencyKey: "turn-key-1",
    executionConfigVersion: 7,
    lastEventId: "event-before-refresh",
  });

  const first = await events.next();
  assert.equal(first.done, false);
  assert.equal(captured.length, 1);
  assert.equal(captured[0].url, "/run_sse");
  assert.equal(captured[0].headers.get("Idempotency-Key"), "turn-key-1");
  assert.equal(captured[0].body.executionConfigVersion, 7);
  assert.equal(captured[0].body.lastEventId, "event-before-refresh");
  assert.deepEqual(captured[0].body.custom_metadata.veadkExecution, {
    executionConfigVersion: 7,
    idempotencyKey: "turn-key-1",
  });
  await events.return();
});

test("runSSE resumes an MPA runtime stream from the last event id", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      headers: new Headers(init.headers),
      body: JSON.parse(String(init.body)),
    });
    if (String(url).includes("/api/v1/sessions/session/run")) {
      return Response.json({
        sessionId: "session",
        invocationId: "e-accepted",
        turnId: "turn-accepted",
        operationId: "op-accepted",
        executionConfigRevision: 7,
      });
    }
    return new Response(
      'data: {"partial":false,"id":"event-after-refresh","content":{"parts":[{"text":"accepted"}]}}\n\n',
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  const events = runSSE({
    appName: "mpa-agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
    idempotencyKey: "turn-key-1",
    executionConfigVersion: 7,
    lastEventId: "event-before-refresh",
  });

  const first = await events.next();
  assert.equal(first.done, false);
  assert.equal(first.value.id, "event-after-refresh");
  assert.equal(captured.length, 2);
  assert.match(captured[0].url, /\/web\/runtime-proxy\/runtime-1\/api\/v1\/sessions\/session\/run/);
  assert.equal(captured[0].headers.get("Idempotency-Key"), "turn-key-1");
  assert.deepEqual(captured[0].body, {
    content: "hello",
    executionConfigVersion: 7,
  });
  assert.match(captured[1].url, /\/web\/runtime-proxy\/runtime-1\/api\/v1\/sessions\/session\/sse/);
  assert.deepEqual(captured[1].body, {
    invocationId: "e-accepted",
    lastEventId: "event-before-refresh",
  });
  await events.return();
});

test("runSSE stops an MPA runtime stream on named done before heartbeat", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  globalThis.fetch = async (url, _init) => {
    if (String(url).includes("/api/v1/sessions/session/run")) {
      return Response.json({
        sessionId: "session",
        invocationId: "e-accepted",
        turnId: "turn-accepted",
        operationId: "op-accepted",
        executionConfigRevision: 1,
      });
    }
    return new Response(
      [
        'event: message\ndata: {"partial":true,"content":{"parts":[{"text":"hello"}]}}\n\n',
        'event: done\ndata: {"sessionId":"session","invocationId":"e-accepted"}\n\n',
        'event: heartbeat\ndata: {"message":"ping"}\n\n',
      ].join(""),
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  const events = runSSE({
    appName: "mpa-agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
    idempotencyKey: "turn-key-1",
    executionConfigVersion: 1,
  });

  const first = await events.next();
  const second = await events.next();
  assert.equal(first.done, false);
  assert.equal(first.value.content.parts[0].text, "hello");
  assert.equal(second.done, true);
});

test("runSSE forwards zero execution config revisions for initial MPA sessions", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (String(url).includes("/api/v1/sessions/session/run")) {
      return Response.json({
        sessionId: "session",
        invocationId: "e-accepted",
      });
    }
    return new Response(
      [
        'event: message\ndata: {"partial":false,"id":"event-1","content":{"parts":[{"text":"ok"}]}}\n\n',
        'event: done\ndata: {"sessionId":"session","invocationId":"e-accepted"}\n\n',
      ].join(""),
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  const events = runSSE({
    appName: "mpa-agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
    idempotencyKey: "turn-key-1",
    executionConfigVersion: 0,
  });

  await events.next();

  assert.deepEqual(captured[0].body, {
    content: "hello",
    executionConfigVersion: 0,
  });
});

test("continueTurn calls the MPA runtime continuation endpoint", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      headers: new Headers(init.headers),
      body: JSON.parse(String(init.body)),
    });
    return Response.json({
      taskId: "task-1",
      sessionId: "session",
      invocationId: "e-continued",
      turnId: "turn-continued",
      operationId: "op-continued",
      executionConfigRevision: 7,
      continuationOf: "turn-old",
      idempotentReplay: false,
    });
  };

  const result = await continueTurn(
    "mpa-agent",
    "session",
    "task-1",
    2,
    "continue-key-1",
  );

  assert.equal(result.invocationId, "e-continued");
  assert.equal(result.continuationOf, "turn-old");
  assert.equal(captured.length, 1);
  assert.match(captured[0].url, /\/web\/runtime-proxy\/runtime-1\/api\/v1\/a2a\/tasks\/task-1\/continue/);
  assert.equal(captured[0].headers.get("Idempotency-Key"), "continue-key-1");
  assert.deepEqual(captured[0].body, { expectedGeneration: 2 });
});

test("continueTurnSSE streams a runtime continuation without starting a normal run", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
    clearRemoteApps();
  });

  registerRemoteApp("mpa-agent", {
    app: "default",
    runtimeId: "runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });

  const captured = [];
  globalThis.fetch = async (url, init) => {
    captured.push({
      url: String(url),
      headers: new Headers(init.headers),
      body: JSON.parse(String(init.body)),
    });
    if (String(url).includes("/api/v1/a2a/tasks/task-1/continue")) {
      return Response.json({
        taskId: "task-1",
        sessionId: "session",
        invocationId: "e-continued",
        turnId: "turn-continued",
        operationId: "op-continued",
        executionConfigRevision: 7,
        continuationOf: "turn-old",
        idempotentReplay: false,
      });
    }
    return new Response(
      'data: {"partial":false,"id":"event-after-continue","content":{"parts":[{"text":"continued"}]}}\n\n',
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  const events = continueTurnSSE({
    appName: "mpa-agent",
    sessionId: "session",
    taskId: "task-1",
    expectedGeneration: 2,
    idempotencyKey: "continue-key-1",
    lastEventId: "event-before-continue",
  });

  const first = await events.next();
  assert.equal(first.done, false);
  assert.equal(first.value.id, "event-after-continue");
  assert.equal(captured.length, 2);
  assert.match(captured[0].url, /\/api\/v1\/a2a\/tasks\/task-1\/continue/);
  assert.doesNotMatch(captured[0].url, /\/api\/v1\/sessions\/session\/run/);
  assert.equal(captured[0].headers.get("Idempotency-Key"), "continue-key-1");
  assert.deepEqual(captured[0].body, { expectedGeneration: 2 });
  assert.match(captured[1].url, /\/api\/v1\/sessions\/session\/sse/);
  assert.deepEqual(captured[1].body, {
    invocationId: "e-continued",
    lastEventId: "event-before-continue",
  });
  await events.return();
});

test("runSSE aborts when no first event arrives before the deadline", async (t) => {
  const previousFetch = globalThis.fetch;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  t.after(() => {
    globalThis.fetch = previousFetch;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  });

  let timeoutCallback;
  let timeoutMs;
  globalThis.setTimeout = (callback, ms, ...args) => {
    timeoutMs = ms;
    timeoutCallback = () => callback(...args);
    return 1;
  };
  globalThis.clearTimeout = () => {};
  globalThis.fetch = async (_url, init) => {
    return new Promise((_resolve, reject) => {
      init.signal.addEventListener(
        "abort",
        () => reject(init.signal.reason ?? new DOMException("Aborted", "AbortError")),
        { once: true },
      );
    });
  };

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  const next = events.next();
  assert.equal(timeoutMs, 30_000);
  timeoutCallback();

  await assert.rejects(next, (error) => {
    assert.equal(error.message, runSseFirstEventTimeoutError());
    assert.match(error.message, /No SSE event was received within 30 seconds/);
    assert.match(error.message, /Check network settings such as the shared public egress, then try again/);
    return true;
  });
});

test("runSSE clears the first-event deadline after yielding the first event", async (t) => {
  const previousFetch = globalThis.fetch;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  t.after(() => {
    globalThis.fetch = previousFetch;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  });

  let requestSignal;
  let timeoutCallback;
  let clearedTimer;
  globalThis.setTimeout = (callback, ms, ...args) => {
    assert.equal(ms, 30_000);
    timeoutCallback = () => callback(...args);
    return 7;
  };
  globalThis.clearTimeout = (timer) => {
    clearedTimer = timer;
  };
  globalThis.fetch = async (_url, init) => {
    requestSignal = init.signal;
    return new Response(
      'data: {"partial":true,"content":{"parts":[{"text":"part"}]}}\n\n',
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  const first = await events.next();
  assert.equal(first.done, false);
  assert.equal(first.value.content.parts[0].text, "part");
  assert.equal(clearedTimer, 7);
  timeoutCallback();
  assert.equal(requestSignal.aborted, false);

  await events.return();
});

test("runSSE formats a fetch rejection before any response arrives", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  globalThis.fetch = async () => {
    throw new TypeError("fetch failed: upstream unavailable");
  };

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  await assert.rejects(events.next(), (error) => {
    assert.match(error.message, /^Raw response: TypeError: fetch failed: upstream unavailable/);
    assert.match(error.message, /Check network settings such as the shared public egress, then try again/);
    return true;
  });
});

test("runSSE preserves an AbortError rejected by fetch", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  const abortError = new DOMException("Stopped by user", "AbortError");
  globalThis.fetch = async () => {
    throw abortError;
  };

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  await assert.rejects(events.next(), (error) => {
    assert.equal(error, abortError);
    assert.equal(error.name, "AbortError");
    assert.doesNotMatch(error.message, /Raw response|shared public egress/);
    return true;
  });
});

test("runSSE rejects an HTTP 200 response that contains no valid events", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  globalThis.fetch = async () => new Response("", {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  await assert.rejects(
    events.next(),
    /Raw response: HTTP 200 with an empty SSE response body\.[\s\S]*Check network settings such as the shared public egress, then try again/,
  );
});

test("runSSE formats malformed SSE JSON without losing the original data", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  globalThis.fetch = async () => new Response("data: malformed-json\n\n", {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  await assert.rejects(events.next(), (error) => {
    assert.match(error.message, /^Raw response: Error: Failed to parse the SSE event JSON/);
    assert.match(error.message, /Raw data: malformed-json/);
    assert.match(error.message, /Check network settings such as the shared public egress, then try again/);
    return true;
  });
});

test("runSSE preserves a partial event and reports an unexpected stream failure", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  globalThis.fetch = async () => {
    let pullCount = 0;
    const stream = new ReadableStream({
      pull(controller) {
        pullCount += 1;
        if (pullCount > 1) {
          controller.error(new TypeError("terminated"));
          return;
        }
        controller.enqueue(
          new TextEncoder().encode(
            'data: {"partial":true,"content":{"parts":[{"text":"part"}]}}\n\n',
          ),
        );
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  };

  const events = runSSE({
    appName: "agent",
    userId: "user",
    sessionId: "session",
    text: "hello",
  });

  const first = await events.next();
  assert.equal(first.done, false);
  assert.equal(first.value.content.parts[0].text, "part");
  await assert.rejects(events.next(), (error) => {
    assert.match(error.message, /^Raw response: TypeError: terminated/);
    assert.match(error.message, /Check network settings such as the shared public egress, then try again/);
    assert.doesNotMatch(error.message, /Runtime may|Unable to access the model service/);
    return true;
  });
});

test("A2A connecting status keeps a delayed response open beyond 30 seconds", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let streamController;
  let requestSignal;
  globalThis.fetch = async (_url, init) => {
    requestSignal = init.signal;
    return new Response(new ReadableStream({start(controller) {
      streamController = controller;
      controller.enqueue(new TextEncoder().encode('data: {"partial":true,"customMetadata":{"a2aStatus":"connecting"},"content":{"parts":[]}}\n\n'));
    }}), {headers: {"Content-Type": "text/event-stream"}});
  };
  const events = runSSE({appName: "a2a-default", userId: "user", sessionId: "session", text: "hello"});
  assert.equal((await events.next()).value.customMetadata.a2aStatus, "connecting");
  const next = events.next();
  t.mock.timers.tick(120_000);
  assert.equal(requestSignal.aborted, false);
  streamController.enqueue(new TextEncoder().encode('data: {"partial":false,"content":{"parts":[{"text":"done"}]}}\n\n'));
  streamController.close();
  assert.equal((await next).value.content.parts[0].text, "done");
  assert.equal((await events.next()).done, true);
});
