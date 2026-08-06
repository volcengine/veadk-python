import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/janusBrowserContext.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { parseJanusStatus, parseJanusToolError, parseJanusToolResult } = await import(moduleUrl);

test("detects Janus from its extension status reply", () => {
  assert.equal(parseJanusStatus({ available: true }), true);
  assert.equal(parseJanusStatus({ available: false }), false);
});

test("accepts a client-executed Janus tool result", () => {
  assert.equal(
    parseJanusToolResult({ result: "[0] Example — https://example.com" }),
    "[0] Example — https://example.com",
  );
});

test("rejects malformed Janus tool replies", () => {
  assert.equal(parseJanusToolResult({}), null);
  assert.equal(parseJanusToolResult({ result: 3 }), null);
});

test("surfaces Janus extension errors", () => {
  assert.equal(parseJanusToolError({ error: "missing permission" }), "missing permission");
  assert.equal(parseJanusToolError({ error: "" }), null);
  assert.equal(parseJanusToolError({}), null);
});
