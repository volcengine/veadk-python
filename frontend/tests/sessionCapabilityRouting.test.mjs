import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/sessionCapabilities.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { requiresSessionCapabilityRunner } = await import(moduleUrl);

test("uses the base runner when capabilities are unavailable or base-only", () => {
  assert.equal(requiresSessionCapabilityRunner(null), false);
  assert.equal(
    requiresSessionCapabilityRunner({
      tools: [{ custom: false }],
      skills: [{ custom: false }],
    }),
    false,
  );
});

test("uses the harness runner for custom tools or skills", () => {
  assert.equal(
    requiresSessionCapabilityRunner({
      tools: [{ custom: true }],
      skills: [],
    }),
    true,
  );
  assert.equal(
    requiresSessionCapabilityRunner({
      tools: [],
      skills: [{ custom: true }],
    }),
    true,
  );
});
