import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

async function loadTypeScriptModule(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  });
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
}

const streams = await loadTypeScriptModule(
  "../src/create/comparison/debugStreamRegistry.ts",
);

test("starting a replacement stream aborts and obsoletes the previous stream", () => {
  const registry = new streams.DebugStreamRegistry();
  const first = registry.begin("baseline");
  const second = registry.begin("baseline");

  assert.equal(first.signal.aborted, true);
  assert.equal(registry.isCurrent("baseline", first.token), false);
  assert.equal(registry.isCurrent("baseline", second.token), true);
  assert.equal(second.signal.aborted, false);
});

test("abort and finish only mutate the matching live stream", () => {
  const registry = new streams.DebugStreamRegistry();
  const baseline = registry.begin("baseline");
  const candidate = registry.begin("candidate");

  assert.equal(registry.finish("baseline", candidate.token), false);
  assert.equal(registry.isCurrent("baseline", baseline.token), true);
  assert.equal(registry.finish("baseline", baseline.token), true);
  assert.equal(registry.isCurrent("baseline", baseline.token), false);

  registry.abortAll();
  assert.equal(candidate.signal.aborted, true);
  assert.equal(registry.isCurrent("candidate", candidate.token), false);
});
