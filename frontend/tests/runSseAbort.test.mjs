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
