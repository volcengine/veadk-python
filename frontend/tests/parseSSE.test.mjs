import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/adk/sse.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
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

test("parses a final data frame when EOF arrives without a blank separator", async () => {
  const response = sseResponse(['data: {"ok":true}']);
  const events = [];
  for await (const event of parseSSE(response)) events.push(event);
  assert.deepEqual(events, [{ ok: true }]);
});

test("rejects a truncated final data frame instead of silently dropping it", async () => {
  const response = sseResponse(['data: {"content":']);
  await assert.rejects(async () => {
    for await (const _event of parseSSE(response)) {
      // Consume the stream so its EOF handling runs.
    }
  }, (error) => {
    assert.match(error.message, /incomplete SSE event/i);
    assert.match(error.message, /Raw data: \{"content":/);
    return true;
  });
});

test("rejects malformed JSON frames and includes their original data", async () => {
  const response = sseResponse(["data: malformed\n\n"]);
  await assert.rejects(async () => {
    for await (const _event of parseSSE(response)) {
      // Consume the stream so frame parsing runs.
    }
  }, (error) => {
    assert.match(error.message, /Failed to parse (?:the )?SSE event JSON/);
    assert.match(error.message, /Raw data: malformed/);
    return true;
  });
});

test("ignores known terminators", async () => {
  const response = sseResponse([
    "data: [DONE]\n\ndata: ping\n\ndata: {\"ok\":true}\n\n",
  ]);
  const events = [];
  for await (const event of parseSSE(response)) events.push(event);
  assert.deepEqual(events, [{ ok: true }]);
});

test("bounds malformed frame details while preserving the original prefix", async () => {
  const malformed = "x".repeat(700);
  const response = sseResponse([`data: ${malformed}\n\n`]);
  await assert.rejects(async () => {
    for await (const _event of parseSSE(response)) {
      // Consume the stream so frame parsing runs.
    }
  }, (error) => {
    assert.match(error.message, new RegExp(`Raw data: ${"x".repeat(40)}`));
    assert.match(error.message, /truncated, 700 characters total/);
    assert.ok(error.message.length < 650);
    return true;
  });
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
