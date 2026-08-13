import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/create/runtimeName.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { normalizeRuntimeName, resolveRuntimeName, runtimeNameProblem } = await import(moduleUrl);

test("normalizes empty and mixed-language Agent names", () => {
  assert.equal(normalizeRuntimeName("   "), "agent-runtime");
  assert.equal(normalizeRuntimeName("  sales 中文 / agent  "), "sales-agent");
  assert.equal(normalizeRuntimeName("中文"), "agent-runtime");
});

test("follows the Root Agent until the Runtime name is explicitly edited", () => {
  assert.equal(resolveRuntimeName("root agent", "", false), "root-agent");
  assert.equal(resolveRuntimeName("renamed agent", "", false), "renamed-agent");
  assert.equal(resolveRuntimeName("renamed agent", "fixed-runtime", true), "fixed-runtime");
  assert.equal(resolveRuntimeName("renamed agent", "", true), "");
  assert.equal(resolveRuntimeName("renamed agent", "legacy-runtime"), "legacy-runtime");
});

test("keeps valid underscores and extends short defaults", () => {
  assert.equal(normalizeRuntimeName("valid_runtime_01"), "valid_runtime_01");
  assert.equal(normalizeRuntimeName("ai"), "ai-rt");
});

test("collapses invalid runs and truncates defaults to 64 characters", () => {
  assert.equal(normalizeRuntimeName("agent...---///runtime"), "agent-runtime");
  const boundary = "a".repeat(64);
  assert.equal(normalizeRuntimeName(boundary), boundary);
  assert.equal(normalizeRuntimeName(`${boundary}b`), boundary);
});

test("validates manual Runtime names without rewriting them", () => {
  assert.equal(runtimeNameProblem("runtime_name-01"), null);
  assert.equal(runtimeNameProblem("a".repeat(64)), null);

  assert.match(runtimeNameProblem(""), /必填/);
  assert.match(runtimeNameProblem("abc"), /4-64/);
  assert.match(runtimeNameProblem("a".repeat(65)), /4-64/);
  assert.match(runtimeNameProblem("中文 runtime"), /只能包含/);
  assert.match(runtimeNameProblem("runtime.name"), /只能包含/);
  assert.match(runtimeNameProblem(" runtime_name "), /只能包含/);
});
