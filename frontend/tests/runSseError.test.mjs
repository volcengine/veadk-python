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

const NETWORK_HINT = "提示：请检查共享公网出口等网络配置，然后重试。";

test("adds memory guidance only when the response says the session is missing", () => {
  const error = "run_sse failed: 404：Session not found: session-1";
  const formatted = formatRunSseError(error);
  assert.ok(formatted.startsWith(`原始响应：${error}`));
  assert.match(formatted, /in-memory/);
  assert.match(formatted, /进程重启/);
  assert.match(formatted, /基于数据库的持久化短期记忆/);
  assert.ok(formatted.endsWith(NETWORK_HINT));
});

test("identifies an unsupported harness route without blaming memory", () => {
  const formatted = formatRunSseError("run_sse failed: 404：Not Found");
  assert.match(formatted, /^原始响应：run_sse failed/);
  assert.match(formatted, /Runtime 未提供会话能力运行接口/);
  assert.doesNotMatch(formatted, /in-memory/);
});

test("does not guess at the cause of an unexplained 404", () => {
  const error = "run_sse failed: 404：upstream error";
  const formatted = formatRunSseError(error);
  assert.ok(formatted.startsWith(`原始响应：${error}`));
  assert.ok(formatted.endsWith(NETWORK_HINT));
  assert.doesNotMatch(formatted, /会话已不存在|Runtime 未提供/);
});

test("preserves unrelated errors before appending network guidance", () => {
  for (const error of ["run_sse failed: 500", "create_session failed: 404"]) {
    const formatted = formatRunSseError(error);
    assert.ok(formatted.startsWith(`原始响应：${error}`));
    assert.ok(formatted.endsWith(NETWORK_HINT));
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
  assert.ok(formatted.startsWith(`原始响应：${error}`));
  assert.match(formatted, /模型生成的工具参数格式不完整/);
  assert.ok(formatted.endsWith(NETWORK_HINT));
});

test("does not claim that a model error was caused by public egress", () => {
  const error = "ModelInvocationError: upstream model returned 503";
  const formatted = formatRunSseError(error);
  assert.ok(formatted.startsWith(`原始响应：${error}`));
  assert.ok(formatted.endsWith(NETWORK_HINT));
  assert.doesNotMatch(formatted, /Runtime 可能|无法访问模型服务|导致/);
});

test("does not duplicate an original-response label provided by HTTP handling", () => {
  const error = [
    "run_sse failed: 502：运行会话失败（HTTP 502）",
    "Bad Gateway",
    "原始响应：",
    '<html lang="en">Bad Gateway</html>',
  ].join("\n");
  const formatted = formatRunSseError(error);
  assert.equal(formatted.match(/原始响应：/g)?.length, 1);
  assert.ok(formatted.startsWith("run_sse failed: 502"));
  assert.ok(formatted.endsWith(NETWORK_HINT));
});
