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
const { runSSE } = await import(moduleUrl);

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
  assert.equal(requestSignal, abortController.signal);

  const next = events.next();
  abortController.abort(new DOMException("Stopped by user", "AbortError"));

  await assert.rejects(next, (error) => {
    assert.equal(error.name, "AbortError");
    return true;
  });
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
    assert.match(error.message, /^原始响应：TypeError: fetch failed: upstream unavailable/);
    assert.match(error.message, /请检查共享公网出口等网络配置，然后重试/);
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
    assert.doesNotMatch(error.message, /原始响应|共享公网出口/);
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
    /原始响应：HTTP 200，SSE 响应体为空。[\s\S]*请检查共享公网出口等网络配置，然后重试/,
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
    assert.match(error.message, /^原始响应：Error: Failed to parse SSE event JSON/);
    assert.match(error.message, /原始 data：malformed-json/);
    assert.match(error.message, /请检查共享公网出口等网络配置，然后重试/);
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
    assert.match(error.message, /^原始响应：TypeError: terminated/);
    assert.match(error.message, /请检查共享公网出口等网络配置，然后重试/);
    assert.doesNotMatch(error.message, /Runtime 可能|无法访问模型服务/);
    return true;
  });
});
