import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

function transpileTypeScriptModule(source) {
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  });
  return `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
}

async function loadModules() {
  const stateSource = readFileSync(
    new URL("../src/create/comparison/comparisonSessionState.ts", import.meta.url),
    "utf8",
  );
  const stateUrl = transpileTypeScriptModule(stateSource);
  const state = await import(stateUrl);

  const viewModelSource = readFileSync(
    new URL(
      "../src/create/comparison/comparisonSessionViewModel.ts",
      import.meta.url,
    ),
    "utf8",
  ).replace(
    /from\s+["']\.\/comparisonSessionState["']/,
    `from ${JSON.stringify(stateUrl)}`,
  );
  const viewModel = await import(transpileTypeScriptModule(viewModelSource));
  return { state, viewModel };
}

const { state, viewModel } = await loadModules();
const READY_PLACEHOLDER = "输入测试消息，将发送到所有已启动测试组...";

function present(sessionState, overrides = {}) {
  return viewModel.comparisonSessionViewModel(sessionState, {
    problem: "",
    canSendReadySession: false,
    readyComposerPlaceholder: READY_PLACEHOLDER,
    ...overrides,
  });
}

test("initial Session offers one direct start without stale evidence", () => {
  const presentation = present(state.createComparisonSessionState());

  assert.equal(presentation.showWarning, false);
  assert.equal(presentation.showAlert, false);
  assert.equal(presentation.actionLabel, "开启 Session");
  assert.equal(presentation.requireConfirmation, false);
  assert.equal(presentation.cardStatusLabel, null);
  assert.equal(presentation.sessionReady, false);
  assert.equal(presentation.sessionStarting, false);
  assert.equal(presentation.verdictEditable, false);
});

test("ready Session can send and requires confirmation before replacement", () => {
  const starting = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const ready = state.completeComparisonSession(
    starting,
    starting.pendingSessionRevision,
  );
  const presentation = present(ready, { canSendReadySession: true });

  assert.equal(presentation.actionLabel, "重新开启 Session");
  assert.equal(presentation.requireConfirmation, true);
  assert.equal(presentation.composerDisabled, false);
  assert.equal(presentation.composerPlaceholder, READY_PLACEHOLDER);
  assert.equal(presentation.sessionReady, true);
  assert.equal(presentation.sessionStarting, false);
  assert.equal(presentation.verdictEditable, true);
});

test("stale Session keeps the previous transcript read-only and directs recovery", () => {
  const starting = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const ready = state.completeComparisonSession(
    starting,
    starting.pendingSessionRevision,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const presentation = present(stale, { canSendReadySession: true });

  assert.equal(presentation.showWarning, true);
  assert.equal(presentation.showAlert, true);
  assert.equal(
    presentation.warningTitle,
    "对照配置已变化，请开启新 Session",
  );
  assert.equal(presentation.actionLabel, "开启新 Session");
  assert.equal(presentation.cardStatusLabel, "上一 Session · 只读");
  assert.equal(presentation.transcriptReadOnly, true);
  assert.equal(presentation.composerDisabled, true);
  assert.equal(
    presentation.composerPlaceholder,
    "配置已变化，请先开启新 Session",
  );
  assert.equal(presentation.requireConfirmation, true);
  assert.equal(presentation.sessionReady, false);
  assert.equal(presentation.sessionStarting, false);
  assert.equal(presentation.verdictEditable, false);
});

test("stale Session exposes the exact validation problem that blocks recovery", () => {
  const starting = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const ready = state.completeComparisonSession(
    starting,
    starting.pendingSessionRevision,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const problem = "请先完成「对照组 2」的 API Base 与临时凭据配置";
  const presentation = present(stale, { problem });

  assert.equal(presentation.actionDisabled, true);
  assert.equal(presentation.actionProblem, problem);
});

test("replacement start blocks duplicates while preserving old evidence", () => {
  const firstStart = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const ready = state.completeComparisonSession(
    firstStart,
    firstStart.pendingSessionRevision,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const replacement = state.beginComparisonSession(stale);
  const presentation = present(replacement, { canSendReadySession: true });

  assert.equal(presentation.actionLabel, "正在开启");
  assert.equal(presentation.actionDisabled, true);
  assert.equal(presentation.transcriptReadOnly, true);
  assert.equal(presentation.cardStatusLabel, "上一 Session · 只读");
  assert.equal(presentation.sessionReady, false);
  assert.equal(presentation.sessionStarting, true);
  assert.equal(presentation.verdictEditable, false);
});

test("failed first start exposes the failed group, Run stage, and safe reason", () => {
  const starting = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const failed = state.failComparisonSession(
    starting,
    starting.pendingSessionRevision,
    {
      variantId: "baseline",
      variantName: "基准组",
      stage: "run",
      message:
        "调试环境并发数已达上限 (4/4)，请稍后重试或关闭不再使用的调试页面。",
    },
  );
  const presentation = present(failed);

  assert.equal(presentation.showWarning, false);
  assert.equal(presentation.showAlert, true);
  assert.equal(presentation.failureTitle, "开启 Session 失败 · 基准组");
  assert.equal(
    presentation.failureDetail,
    "启动调试环境：调试环境并发数已达上限 (4/4)，请稍后重试或关闭不再使用的调试页面。",
  );
  assert.equal(presentation.actionLabel, "开启 Session");
  assert.equal(presentation.sessionReady, false);
  assert.equal(presentation.sessionStarting, false);
  assert.equal(presentation.verdictEditable, false);
});

test("failed replacement keeps stale warning and exposes Session-stage failure", () => {
  const firstStart = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const ready = state.completeComparisonSession(
    firstStart,
    firstStart.pendingSessionRevision,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const replacement = state.beginComparisonSession(stale);
  const failed = state.failComparisonSession(
    replacement,
    replacement.pendingSessionRevision,
    {
      variantId: "variant-1",
      variantName: "对照组 1",
      stage: "session",
      message: "创建 ADK Session 失败，请稍后重试。",
    },
  );
  const presentation = present(failed);

  assert.equal(presentation.showWarning, true);
  assert.equal(presentation.showAlert, true);
  assert.equal(presentation.transcriptReadOnly, true);
  assert.equal(presentation.cardStatusLabel, "上一 Session · 只读");
  assert.equal(presentation.actionLabel, "开启新 Session");
  assert.equal(presentation.actionDisabled, false);
  assert.equal(presentation.failureTitle, "开启 Session 失败 · 对照组 1");
  assert.equal(
    presentation.failureDetail,
    "创建 ADK Session：创建 ADK Session 失败，请稍后重试。",
  );
  assert.equal(presentation.sessionReady, false);
  assert.equal(presentation.sessionStarting, false);
  assert.equal(presentation.verdictEditable, false);
});
