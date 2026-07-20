import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../src/adk/sse.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { parseSSE } = await import(moduleUrl);

function sseResponse(chunks, { hold = false, onCancel } = {}) {
  const encoder = new TextEncoder();
  let index = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index++]));
      } else if (!hold) {
        controller.close();
      }
    },
    cancel() {
      onCancel?.();
    },
  });
  return new Response(stream);
}

test("reassembles split chunks and parses LF frames", async () => {
  const response = sseResponse(['data: {"a"', ':1}\n\ndata: {"b":2}\n\n']);
  const events = [];
  for await (const event of parseSSE(response)) events.push(event);
  assert.deepEqual(events, [{ a: 1 }, { b: 2 }]);
  assert.equal(response.body.locked, false);
});

test("parses CRLF frames", async () => {
  const response = sseResponse(['data: {"ok":true}\r', "\n\r\n"]);
  const events = [];
  for await (const event of parseSSE(response)) events.push(event);
  assert.deepEqual(events, [{ ok: true }]);
});

test("logs malformed data but ignores known terminators", async () => {
  const messages = [];
  const originalDebug = console.debug;
  console.debug = (...args) => messages.push(args);
  try {
    const response = sseResponse([
      "data: [DONE]\n\ndata: ping\n\ndata: malformed\n\ndata: {\"ok\":true}\n\n",
    ]);
    const events = [];
    for await (const event of parseSSE(response)) events.push(event);
    assert.deepEqual(events, [{ ok: true }]);
    assert.equal(messages.length, 1);
    assert.match(String(messages[0][0]), /dropping unparseable frame/);
  } finally {
    console.debug = originalDebug;
  }
});

test("cancels and unlocks the stream when the consumer exits early", async () => {
  let cancelled = false;
  const response = sseResponse(['data: {"first":1}\n\n'], {
    hold: true,
    onCancel: () => {
      cancelled = true;
    },
  });
  for await (const event of parseSSE(response)) {
    assert.deepEqual(event, { first: 1 });
    break;
  }
  assert.equal(cancelled, true);
  assert.equal(response.body.locked, false);
});
