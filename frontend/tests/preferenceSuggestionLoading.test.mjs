import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/quality/usePreferenceSuggestions.ts", import.meta.url))],
  bundle: true, platform: "node", format: "cjs", write: false, external: ["react"],
  plugins: [{ name: "suggestion-client", setup(builder) {
    builder.onResolve({ filter: /adk\/quality$/ }, () => ({ path: "quality", namespace: "mock" }));
    builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: `
      export const loadQualityAgentContext = (...args) => globalThis.loadSuggestionContext(...args);
      export const suggestQualityPreferences = (...args) => globalThis.generateFieldSuggestions(...args);
      export class QualityRequestError extends Error { constructor(code, diagnostics) { super(code); this.code = code; this.diagnostics = diagnostics; } }
    ` }));
  } }],
});
const module = { exports: {} };
Function("require", "module", "exports", result.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const { usePreferenceSuggestions } = module.exports;
const fields = ["goal", "scenarios", "successCriteria", "unacceptableErrors"];
const data = field => ({ suggestions: [{ label: field, text: `Suggestion for ${field}` }] });

function setup(t, readContext = async input => ({ name: input.info?.name ?? input.draft.name })) {
  const dom = new JSDOM('<div id="root"></div>');
  const saved = Object.fromEntries(["window", "document", "IS_REACT_ACT_ENVIRONMENT"].map(key => [key, globalThis[key]]));
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
  const root = createRoot(document.getElementById("root"));
  let state;
  const source = { info: null, draft: { name: "orders" } };
  function Probe({ enabled, language, source, preferences }) { state = usePreferenceSuggestions(source, language, enabled, preferences); return null; }
  const render = async (enabled = true, language = "zh-CN", input = source, preferences) => {
    await act(async () => root.render(React.createElement(Probe, { enabled, language, source: input, preferences })));
  };
  let contextReads = 0;
  const requests = [];
  globalThis.loadSuggestionContext = async (...args) => { contextReads++; return readContext(...args); };
  globalThis.generateFieldSuggestions = (body, signal) => new Promise((resolve, reject) => requests.push({ body, signal, resolve, reject }));
  t.after(async () => {
    await act(async () => root.unmount());
    dom.window.close();
    Object.assign(globalThis, saved);
    delete globalThis.loadSuggestionContext;
    delete globalThis.generateFieldSuggestions;
  });
  return { render, requests, get state() { return state; }, get contextReads() { return contextReads; } };
}

const componentFields = ["datasetScenarios", "datasetRequirements", "overallFocus", "toolsFocus", "skillsFocus", "criteria"];
const componentInput = () => ({
  overallPreferences: { name: "订单验收", goal: "验证订单答复", scenarios: "缺少订单号", successCriteria: "先确认订单号", unacceptableErrors: "编造物流状态", preference: "balanced" },
  componentPreferences: { dataset: { preference: "balanced", scenario: "查询配送", requirements: "给出可靠状态", count: 100 }, evaluators: { overallFocus: "任务完成", toolsFocus: "检查订单查询", skillsFocus: "检查报告规范", criteria: "不编造状态", strictness: "balanced" } },
});

test("component fields run independently with shared Agent data and reviewed preference context", async t => {
  const ui = setup(t);
  await ui.render();
  await act(async () => ui.requests.forEach(request => request.resolve(data(request.body.field))));
  const preferences = componentInput();
  await ui.render(true, "zh-CN", undefined, preferences);
  assert.equal(ui.contextReads, 1);
  assert.deepEqual(ui.requests.slice(4).map(request => request.body.field), componentFields);
  assert.ok(ui.requests.slice(4).every(request => request.body.overallPreferences === preferences.overallPreferences && request.body.componentPreferences === preferences.componentPreferences));
  await act(async () => ui.requests[5].resolve(data("datasetRequirements")));
  assert.equal(ui.state.fields.datasetRequirements.loading, false);
  assert.equal(ui.state.fields.datasetScenarios.loading, true);
  await act(async () => ui.requests.slice(4).filter((_, index) => index !== 1).forEach(request => request.resolve(data(request.body.field))));
  await ui.render();
  assert.equal(ui.requests.length, 10);
  assert.deepEqual(ui.state.fields.goal.data, data("goal").suggestions);
  await ui.render(true, "zh-CN", undefined, preferences);
  assert.equal(ui.requests.length, 10);
  await ui.render(false, "zh-CN", undefined, preferences);
  await ui.render(true, "zh-CN", undefined, preferences);
  assert.equal(ui.requests.length, 10);
});

test("changing the reviewed preference invalidates component recommendations and ignores stale responses", async t => {
  const ui = setup(t);
  const preferences = componentInput();
  await ui.render(true, "zh-CN", undefined, preferences);
  const updated = { ...preferences, overallPreferences: { ...preferences.overallPreferences, goal: "验证退款答复" } };
  await ui.render(true, "zh-CN", undefined, updated);
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 12);
  assert.ok(ui.requests.slice(0, 6).every(request => request.signal.aborted));
  await act(async () => ui.requests.slice(0, 6).forEach(request => request.resolve(data("old"))));
  assert.equal(ui.state.fields.datasetScenarios.data, null);
  await act(async () => ui.requests[6].resolve(data("datasetScenarios")));
  assert.deepEqual(ui.state.fields.datasetScenarios.data, data("datasetScenarios").suggestions);
});

test("prepares full context before opening and reuses it for suggestions and subsequent generation", async t => {
  const ui = setup(t);
  await ui.render(false);
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 0);
  await ui.render();
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 4);
  const agent = await ui.state.loadAgent(new AbortController().signal);
  assert.equal(agent, ui.requests[0].body.agent);
  assert.equal(ui.contextReads, 1);
});

test("opening during preparation shares the pending read and closing only cancels model requests", async t => {
  let finish;
  let preparationSignal;
  const ui = setup(t, (_input, signal) => { preparationSignal = signal; return new Promise(resolve => { finish = resolve; }); });
  await ui.render(false);
  await ui.render();
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 0);
  await ui.render(false);
  assert.equal(preparationSignal.aborted, false);
  await act(async () => finish({ name: "orders" }));
  assert.equal(ui.requests.length, 0);
  await ui.render();
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 4);
});

test("waits for verified detail data, ignores unrelated runtime draft updates, and invalidates changed Agent data", async t => {
  const ui = setup(t);
  const pending = { runtimeId: "runtime-1", region: "cn-beijing", appName: "", info: null, infoLoading: true, draft: { name: "display-name" } };
  await ui.render(true, "zh-CN", pending);
  assert.equal(ui.contextReads, 0);
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.state.fields.goal.loading, true);
  const source = { ...pending, infoLoading: false, info: { name: "real-agent", appName: "actual-app", instruction: "Original rules" } };
  await ui.render(true, "zh-CN", source);
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 4);
  await ui.render(true, "zh-CN", { ...source, draft: { name: "Recovered editor draft" } });
  assert.equal(ui.contextReads, 1);
  assert.equal(ui.requests.length, 4);
  assert.ok(ui.requests.every(request => !request.signal.aborted));
  await ui.render(true, "zh-CN", { ...source, info: { ...source.info, instruction: "Updated rules" } });
  assert.equal(ui.contextReads, 2);
  assert.equal(ui.requests.length, 8);
  assert.ok(ui.requests.slice(0, 4).every(request => request.signal.aborted));
});

test("a failed preparation is retryable and language changes reuse Agent metadata", async t => {
  let fail = true;
  const ui = setup(t, async () => {
    if (fail) throw Error("Metadata unavailable");
    return { name: "orders" };
  });
  await ui.render();
  assert.ok(fields.every(field => ui.state.fields[field].error));
  assert.equal(ui.requests.length, 0);
  fail = false;
  await act(async () => ui.state.retry());
  assert.equal(ui.contextReads, 2);
  assert.equal(ui.requests.length, 4);
  await act(async () => ui.requests.forEach(request => request.resolve(data(request.body.field))));
  await ui.render(true, "en-US");
  assert.equal(ui.contextReads, 2);
  assert.equal(ui.requests.length, 8);
  assert.ok(ui.requests.slice(4).every(request => request.body.language === "en-US"));
});

test("changing Agent during preparation cancels old resource reads and ignores late metadata", async t => {
  const reads = [];
  const ui = setup(t, (source, signal) => new Promise(resolve => reads.push({ source, signal, resolve })));
  await ui.render();
  await ui.render(true, "zh-CN", { info: null, draft: { name: "new-agent" } });
  assert.equal(reads.length, 2);
  assert.equal(reads[0].signal.aborted, true);
  await act(async () => reads[0].resolve({ name: "old-agent" }));
  assert.equal(ui.requests.length, 0);
  await act(async () => reads[1].resolve({ name: "new-agent" }));
  assert.equal(ui.requests.length, 4);
  assert.ok(ui.requests.every(request => request.body.agent.name === "new-agent"));
});

test("starts all four fields together, publishes each result immediately, and retries only failures", async t => {
  const ui = setup(t);
  await ui.render();
  assert.deepEqual(ui.requests.map(request => request.body.field), fields);
  assert.equal(ui.contextReads, 1);
  assert.ok(ui.requests.every(request => request.body.agent === ui.requests[0].body.agent));
  await act(async () => ui.requests[2].resolve(data("successCriteria")));
  assert.deepEqual(ui.state.fields.successCriteria.data, data("successCriteria").suggestions);
  assert.equal(ui.state.fields.successCriteria.loading, false);
  assert.equal(ui.state.fields.goal.loading, true);
  await act(async () => {
    ui.requests[0].resolve(data("goal"));
    ui.requests[1].reject(Error("cloud failure"));
    ui.requests[3].resolve(data("unacceptableErrors"));
  });
  assert.ok(ui.state.fields.scenarios.error);
  assert.equal(ui.state.loading, false);
  await act(async () => ui.state.retry());
  assert.equal(ui.requests.length, 5);
  assert.equal(ui.requests[4].body.field, "scenarios");
  assert.equal(ui.contextReads, 1);
  assert.deepEqual(ui.state.fields.goal.data, data("goal").suggestions);
  await act(async () => ui.requests[4].resolve(data("scenarios")));
  await ui.render(false);
  await ui.render(true);
  assert.equal(ui.requests.length, 5);
});

test("cancellation retains completed fields and ignores late results; changed Agent data is not reused", async t => {
  const ui = setup(t);
  await ui.render();
  await act(async () => ui.requests[0].resolve(data("goal")));
  await ui.render(false);
  assert.ok(ui.requests.every(request => request.signal.aborted));
  await act(async () => ui.requests[1].resolve(data("stale")));
  await ui.render(true);
  assert.deepEqual(ui.requests.slice(4).map(request => request.body.field), fields.slice(1));
  assert.equal(ui.state.fields.scenarios.data, null);
  assert.deepEqual(ui.state.fields.goal.data, data("goal").suggestions);
  await ui.render(true, "zh-CN", { info: null, draft: { name: "new-agent" } });
  assert.equal(ui.contextReads, 2);
  assert.equal(ui.state.fields.goal.data, null);
  assert.ok(ui.requests.slice(7).every(request => request.body.agent.name === "new-agent"));
  await act(async () => ui.requests.slice(4, 7).forEach(request => request.resolve(data("old-agent"))));
  assert.equal(ui.state.fields.scenarios.data, null);
});
