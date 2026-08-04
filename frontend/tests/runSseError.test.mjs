import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/runSseError.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { formatRunSseError } = await import(moduleUrl);

test("adds memory guidance only when the response says the session is missing", () => {
  const error = "run_sse failed: 404：Session not found: session-1";
  const formatted = formatRunSseError(error);
  assert.ok(formatted.startsWith(error));
  assert.match(formatted, /in-memory/);
  assert.match(formatted, /进程重启/);
  assert.match(formatted, /基于数据库的持久化短期记忆/);
});

test("identifies an unsupported harness route without blaming memory", () => {
  const formatted = formatRunSseError("run_sse failed: 404：Not Found");
  assert.match(formatted, /Runtime 未提供会话能力运行接口/);
  assert.doesNotMatch(formatted, /in-memory/);
});

test("does not guess at the cause of an unexplained 404", () => {
  assert.equal(
    formatRunSseError("run_sse failed: 404：upstream error"),
    "run_sse failed: 404：upstream error",
  );
});

test("leaves unrelated errors unchanged", () => {
  for (const error of ["run_sse failed: 500", "create_session failed: 404"]) {
    assert.equal(formatRunSseError(error), error);
  }
});

test("does not append the guidance twice", () => {
  const formatted = formatRunSseError(
    "run_sse failed: 404：Session not found: session-1",
  );
  assert.equal(formatRunSseError(formatted), formatted);
});

test("preserves malformed tool argument details and adds an actionable message", () => {
  const error = "Expecting ',' delimiter: line 1 column 169 (char 168)";
  const formatted = formatRunSseError(error);
  assert.ok(formatted.startsWith(error));
  assert.match(formatted, /模型生成的工具参数格式不完整/);
});
