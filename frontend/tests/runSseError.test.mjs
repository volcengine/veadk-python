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

test("adds persistent-memory guidance to run_sse 404 variants", () => {
  for (const error of [
    "Error:run_sse failed:404",
    "Error: run_sse failed: 404",
    "RUN_SSE FAILED : 404",
  ]) {
    const formatted = formatRunSseError(error);
    assert.ok(formatted.startsWith(error));
    assert.match(formatted, /多实例部署/);
    assert.match(formatted, /in-memory/);
    assert.match(formatted, /SQLite/);
    assert.match(formatted, /基于数据库的持久化短期记忆/);
  }
});

test("leaves unrelated errors unchanged", () => {
  for (const error of ["run_sse failed: 500", "create_session failed: 404"]) {
    assert.equal(formatRunSseError(error), error);
  }
});

test("does not append the guidance twice", () => {
  const formatted = formatRunSseError("run_sse failed: 404");
  assert.equal(formatRunSseError(formatted), formatted);
});
