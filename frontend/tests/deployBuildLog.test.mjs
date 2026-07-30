import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

async function loadTypeScriptModule(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  return import(moduleUrl);
}

const { mergeDeployBuildLog } = await loadTypeScriptModule("../src/ui/deployBuildLog.ts");

function snapshot(text, fields = {}) {
  return {
    source: "code-pipeline",
    status: "running",
    text,
    lineCount: text ? text.split("\n").length : 0,
    truncated: false,
    updatedAt: 1,
    ...fields,
  };
}

test("deployment build logs append non-overlapping snapshots", () => {
  const merged = mergeDeployBuildLog(
    snapshot("line 1\nline 2"),
    snapshot("line 3\nline 4"),
  );

  assert.equal(merged.text, "line 1\nline 2\nline 3\nline 4");
  assert.equal(merged.lineCount, 4);
  assert.equal(merged.omittedEarly, false);
});

test("deployment build logs de-duplicate overlapping tail snapshots", () => {
  const first = snapshot("line 1\nline 2\nline 3");
  const second = snapshot("line 2\nline 3\nline 4");
  const merged = mergeDeployBuildLog(first, second);

  assert.equal(merged.text, "line 1\nline 2\nline 3\nline 4");
  assert.equal(merged.lineCount, 4);
});

test("deployment build logs keep a bounded tail and mark omitted early logs", () => {
  const merged = mergeDeployBuildLog(
    snapshot("alpha\nbeta\ngamma"),
    snapshot("delta\nepsilon"),
    18,
  );

  assert.equal(merged.text, "delta\nepsilon");
  assert.equal(merged.omittedEarly, true);
  assert.equal(merged.truncated, true);
});

test("deployment build logs preserve backend snapshot truncation state", () => {
  const merged = mergeDeployBuildLog(
    snapshot("line 1"),
    snapshot("line 1\nline 2", { truncated: true }),
  );

  assert.equal(merged.snapshotTruncated, true);
  assert.equal(merged.truncated, true);
});
