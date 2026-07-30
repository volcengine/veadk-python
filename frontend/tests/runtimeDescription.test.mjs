import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/runtimeDescription.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { normalizeRuntimeDescription, RUNTIME_DESCRIPTION_MAX_BYTES } =
  await import(moduleUrl);

test("runtime descriptions are normalized to a safe single line", () => {
  assert.equal(
    normalizeRuntimeDescription("  数据\n分析\u0000 Agent 🤖  "),
    "数据 分析 Agent",
  );
  assert.equal(normalizeRuntimeDescription("Ａｇｅｎｔ＿１"), "Agent_1");
});

test("runtime descriptions stay within the AgentKit byte limit", () => {
  const normalized = normalizeRuntimeDescription("数".repeat(100));
  assert.ok(Buffer.byteLength(normalized, "utf8") <= RUNTIME_DESCRIPTION_MAX_BYTES);
  assert.equal(normalized, "数".repeat(85));
});

test("every deployment caller uses the shared runtime description rule", () => {
  assert.match(
    clientSource,
    /description: normalizeRuntimeDescription\(opts\?\.description \?\? ""\)/,
  );
});
