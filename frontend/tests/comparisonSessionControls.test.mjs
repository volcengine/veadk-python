import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({
  configFile: new URL("../vite.config.ts", import.meta.url).pathname,
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true, hmr: false, port: 0 },
});

test.after(async () => {
  await server.close();
});

const state = await server.ssrLoadModule(
  "/src/create/comparison/comparisonSessionState.ts",
);
const { comparisonSessionViewModel } = await server.ssrLoadModule(
  "/src/create/comparison/comparisonSessionViewModel.ts",
);
const { ComparisonSessionActionSlot } = await server.ssrLoadModule(
  "/src/create/comparison/ComparisonSessionControls.tsx",
);

function presentation(sessionState, problem = "") {
  return comparisonSessionViewModel(sessionState, {
    problem,
    canSendReadySession: false,
    readyComposerPlaceholder: "输入测试消息",
  });
}

function renderActionSlots(viewModel) {
  return renderToStaticMarkup(
    React.createElement(
      React.Fragment,
      null,
      React.createElement(ComparisonSessionActionSlot, {
        placement: "toolbar",
        viewModel,
        onStartSession: () => {},
      }),
      React.createElement(ComparisonSessionActionSlot, {
        placement: "alert",
        viewModel,
        onStartSession: () => {},
      }),
    ),
  );
}

function countSessionActions(html) {
  return [...html.matchAll(/data-comparison-session-action="true"/g)].length;
}

test("initial Session renders exactly one toolbar action", () => {
  const html = renderActionSlots(
    presentation(state.createComparisonSessionState()),
  );

  assert.equal(countSessionActions(html), 1);
  assert.doesNotMatch(html, /role="alert"/);
  assert.match(html, />开启 Session<\/button>/);
});

test("stale Session renders exactly one alert-owned recovery action", () => {
  const firstStart = state.beginComparisonSession(
    state.createComparisonSessionState(),
  );
  const ready = state.completeComparisonSession(
    firstStart,
    firstStart.pendingSessionRevision,
  );
  const stale = state.markComparisonConfigurationChanged(ready, true);
  const problem = "请先完成「对照组 2」的模型连接配置";
  const html = renderActionSlots(presentation(stale, problem));

  assert.equal(countSessionActions(html), 1);
  assert.match(
    html,
    /id="cw-comparison-session-warning"[^>]*role="alert"/,
  );
  assert.match(html, /对照配置已变化，请开启新 Session/);
  assert.match(html, new RegExp(problem));
  assert.match(html, /title="请先完成「对照组 2」的模型连接配置"/);
  assert.match(html, /data-comparison-session-action="true"[^>]*disabled/);
});

test("failed first start renders an associated alert with visible stage detail", () => {
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
  const html = renderActionSlots(presentation(failed));

  assert.equal(countSessionActions(html), 1);
  assert.match(
    html,
    /id="cw-comparison-session-warning"[^>]*role="alert"/,
  );
  assert.match(html, /开启 Session 失败 · 基准组/);
  assert.match(
    html,
    /启动调试环境：调试环境并发数已达上限 \(4\/4\)，请稍后重试或关闭不再使用的调试页面。/,
  );
});
