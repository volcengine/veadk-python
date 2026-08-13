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
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  return import(moduleUrl);
}

const state = await loadTypeScriptModule(
  "../src/create/comparison/comparisonSessionState.ts",
);

test("locks the active revision only after a successful start", () => {
  const initial = state.createComparisonSessionState();
  assert.equal(state.comparisonSessionStatus(initial), "not_started");

  const edited = state.markComparisonConfigurationChanged(initial, true);
  const starting = state.beginComparisonSession(edited);
  assert.equal(state.comparisonSessionStatus(starting), "starting");

  const ready = state.completeComparisonSession(
    starting,
    starting.pendingSessionRevision,
  );
  assert.equal(state.comparisonSessionStatus(ready), "ready");
  assert.equal(ready.activeSessionRevision, ready.configurationRevision);
});

test("latches a real configuration edit even when later values are restored", () => {
  const ready = state.completeComparisonSession(
    state.beginComparisonSession(state.createComparisonSessionState()),
    0,
  );
  const unchanged = state.markComparisonConfigurationChanged(ready, false);
  assert.equal(unchanged, ready);

  const edited = state.markComparisonConfigurationChanged(ready, true);
  const restored = state.markComparisonConfigurationChanged(edited, true);
  assert.equal(restored.configurationRevision, 2);
  assert.equal(state.comparisonSessionStatus(restored), "stale");
});

test("topology or cloud invalidation makes a ready Session stale", () => {
  const ready = state.completeComparisonSession(
    state.beginComparisonSession(state.createComparisonSessionState()),
    0,
  );

  const invalidated = state.markComparisonConfigurationChanged(ready, true);

  assert.equal(invalidated.activeSessionRevision, 0);
  assert.equal(invalidated.configurationRevision, 1);
  assert.equal(state.comparisonSessionStatus(invalidated), "stale");
});

test("a semantic edit during startup clears the matching attempt and remains recoverable", () => {
  const firstStarting = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const firstEdited = state.markComparisonConfigurationChanged(
    firstStarting,
    true,
  );
  assert.equal(firstEdited.pendingSessionRevision, null);
  assert.equal(state.comparisonSessionStatus(firstEdited), "not_started");

  const ready = state.completeComparisonSession(
    state.beginComparisonSession(state.createComparisonSessionState()),
    0,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const replacementStarting = state.beginComparisonSession(stale);
  const replacementEdited = state.markComparisonConfigurationChanged(
    replacementStarting,
    true,
  );
  assert.equal(replacementEdited.pendingSessionRevision, null);
  assert.equal(replacementEdited.activeSessionRevision, 0);
  assert.equal(state.comparisonSessionStatus(replacementEdited), "stale");
});

test("a failed replacement keeps the previous active revision", () => {
  const ready = state.completeComparisonSession(
    state.beginComparisonSession(state.createComparisonSessionState()),
    0,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const starting = state.beginComparisonSession(stale);
  const failed = state.failComparisonSession(
    starting,
    starting.pendingSessionRevision,
    {
      variantId: "variant-1",
      variantName: "对照组 1",
      stage: "session",
      message: "创建调试会话失败",
    },
  );
  assert.equal(failed.activeSessionRevision, 0);
  assert.equal(state.comparisonSessionStatus(failed), "failed");
  assert.equal(failed.failure?.variantName, "对照组 1");
});

test("ignores completion from an obsolete attempt", () => {
  const starting = state.beginComparisonSession(state.createComparisonSessionState());
  assert.equal(state.completeComparisonSession(starting, 99), starting);
  assert.equal(
    state.failComparisonSession(starting, 99, {
      variantId: "baseline",
      variantName: "基准组",
      stage: "run",
      message: "obsolete",
    }),
    starting,
  );
});
