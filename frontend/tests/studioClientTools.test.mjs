import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/studioClientTools.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const {
  executeStudioClientTool,
  parseStudioClientToolCapabilities,
  parseStudioClientToolExecution,
  sanitizeDownloadFilename,
} = await import(moduleUrl);

const toolNames = [
  "ppt_generate",
  "image_generate",
  "image_edit",
  "video_generate",
  "video_task_query",
];

test("requires the complete Studio media capability set", () => {
  assert.equal(parseStudioClientToolCapabilities({ tools: toolNames }), true);
  assert.equal(parseStudioClientToolCapabilities({ tools: toolNames.slice(0, -1) }), false);
  assert.equal(parseStudioClientToolCapabilities({ tools: "ppt_generate" }), false);
});

test("validates Studio client tool execution responses", () => {
  assert.deepEqual(
    parseStudioClientToolExecution({ result: { ok: true }, downloads: [] }),
    { result: { ok: true }, downloads: [] },
  );
  assert.equal(parseStudioClientToolExecution({ downloads: [] }), null);
  assert.equal(
    parseStudioClientToolExecution({ result: {}, downloads: [{ filename: "x" }] }),
    null,
  );
});

test("sanitizes download filenames to a basename", () => {
  assert.equal(sanitizeDownloadFilename("../private/deck.pptx"), "deck.pptx");
  assert.equal(sanitizeDownloadFilename("C:\\private\\deck.pptx"), "deck.pptx");
  assert.equal(sanitizeDownloadFilename(""), "download");
});

test("executes through the unified endpoint, downloads files, and returns only result", async () => {
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  const calls = [];
  const anchors = [];
  const revoked = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({
      result: { filename: "deck.pptx" },
      downloads: [{
        filename: "../deck.pptx",
        mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        data: "ZGVjaw==",
      }],
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  globalThis.document = {
    body: { appendChild: (anchor) => anchors.push(anchor) },
    createElement: () => ({ click() { this.clicked = true; }, remove() { this.removed = true; } }),
  };
  URL.createObjectURL = () => "blob:deck";
  URL.revokeObjectURL = (url) => revoked.push(url);

  try {
    const result = await executeStudioClientTool("ppt_generate", { title: "Deck" });
    assert.deepEqual(result, { filename: "deck.pptx" });
    assert.equal(calls[0].url, "/web/client-tools/execute");
    assert.equal(calls[0].init.method, "POST");
    assert.deepEqual(JSON.parse(calls[0].init.body), {
      name: "ppt_generate",
      arguments: { title: "Deck" },
    });
    assert.equal(anchors[0].download, "deck.pptx");
    assert.equal(anchors[0].clicked, true);
    assert.equal(anchors[0].removed, true);
    assert.deepEqual(revoked, ["blob:deck"]);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.document = originalDocument;
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  }
});

test("allows media execution to run for twenty-one minutes", () => {
  assert.match(source, /const EXECUTION_TIMEOUT_MS = 21 \* 60 \* 1_000/);
  assert.match(source, /AbortSignal\.timeout\(EXECUTION_TIMEOUT_MS\)/);
});
