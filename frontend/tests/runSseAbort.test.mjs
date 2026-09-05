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
const { runSseFirstEventTimeoutError, runSSE } = await import(moduleUrl);

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
