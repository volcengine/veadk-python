import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/create/runtimeName.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
const {
  generateRuntimeName,
  normalizeRuntimeName,
  resolveRuntimeName,
  runtimeNameProblem,
  runtimeNameWithSuffix,
} = await import(moduleUrl);

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

test("adds one bounded suffix to generated Runtime names", () => {
  assert.equal(runtimeNameWithSuffix("sales 中文 agent", "a1b2c3"), "sales-agent-a1b2c3");
  assert.equal(runtimeNameWithSuffix("a".repeat(64), "z9y8x7").length, 64);
  assert.equal(runtimeNameWithSuffix("a".repeat(64), "z9y8x7").endsWith("-z9y8x7"), true);
  assert.equal(generateRuntimeName("sales agent", () => 0), "sales-agent-000000");
});

test("validates manual Runtime names without rewriting them", () => {
  assert.equal(runtimeNameProblem("runtime_name-01"), null);
  assert.equal(runtimeNameProblem("a".repeat(64)), null);

  assert.match(runtimeNameProblem(""), /required/);
  assert.match(runtimeNameProblem("abc"), /4[–-]64/);
  assert.match(runtimeNameProblem("a".repeat(65)), /4[–-]64/);
  assert.match(runtimeNameProblem("中文 runtime"), /only/);
  assert.match(runtimeNameProblem("runtime.name"), /only/);
  assert.match(runtimeNameProblem(" runtime_name "), /only/);
});
