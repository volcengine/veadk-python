import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);
const React = require("react");
const { act } = React;
const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/ui/new-chat-modes/NewChatAgentPicker.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*"],
  plugins: [{ name: "recovery-test", setup(b) {
    const mocks = {
      "react-i18next": 'const t = key => key; export const useTranslation = () => ({ t });',
      "../../adk/client": 'export const getRuntimes = async () => ({ runtimes: [], nextToken: "" });',
      "../../adk/sandbox": 'export const sandboxClient = { listAgentSessions: (...args) => globalThis.recoveryApi(...args) }; export const sandboxStatusLabel = value => value;',
      "../../adk/requestError": 'export const formatRequestError = error => error.message;',
      "@openai/apps-sdk-ui/components/EmptyMessage": 'import React from "react"; const Part = ({children}) => React.createElement("div", null, children); export const EmptyMessage = Object.assign(Part, {Icon: Part, Title: Part, Description: Part});',
    };
    b.onResolve({ filter: /.*/ }, args => args.path in mocks ? { path: args.path, namespace: "recovery-mock" } : undefined);
    b.onLoad({ filter: /.*/, namespace: "recovery-mock" }, args => ({ contents: mocks[args.path], loader: "js" }));
    b.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
  }}],
});
const module = { exports: {} };
Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);

test("keeps agents usable, shows paused recovery without polling, and cancels timers on close", async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { pretendToBeVisual: true });
  const values = {
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement, Node: dom.window.Node,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  const previous = Object.fromEntries([...Object.keys(values), "recoveryApi"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  let timerId = 1000;
  const timers = new Map();
  const originalSetTimeout = dom.window.setTimeout.bind(dom.window);
  const originalClearTimeout = dom.window.clearTimeout.bind(dom.window);
  dom.window.setTimeout = (callback, delay, ...args) => {
    if (delay !== 3000) return originalSetTimeout(callback, delay, ...args);
    timers.set(++timerId, callback);
    return timerId;
  };
  dom.window.clearTimeout = id => { timers.delete(id); originalClearTimeout(id); };
  const live = { id: "live", resourceType: "session", status: "Ready", displayName: "Live Hermes" };
  let finishRefresh;
  let calls = 0;
  globalThis.recoveryApi = async (kind, options) => {
    assert.equal(kind, "hermes");
    calls++;
    if (calls === 2) await new Promise(resolve => { finishRefresh = resolve; });
    options.onRecoveryStatus(calls !== 2, calls <= 2);
    return calls === 2 ? [live, { ...live, id: "restored", displayName: "Restored Hermes" }] : [live];
  };
  const { createRoot } = require("react-dom/client");
  const root = createRoot(dom.window.document.getElementById("root"));
  const doc = dom.window.document;
  const openHermes = async () => {
    await act(async () => doc.querySelector(".new-chat-agent-picker__trigger").click());
    await act(async () => [...doc.querySelectorAll('[role="menuitem"]')].find(el => el.textContent.includes("types.hermes")).click());
  };
  try {
    await act(async () => root.render(React.createElement(module.exports.NewChatAgentPicker, {
      runtimeScope: "all", onSelectRuntime: async () => {}, onSelectSandboxSession: async () => {},
    })));
    await openHermes();
    assert.equal(doc.querySelectorAll('[role="option"]').length, 1);
    assert.equal(doc.querySelector('[role="option"]').disabled, false);
    assert.match(doc.querySelector('[role="status"]').textContent, /restoringHistory/);
    assert.match(doc.querySelector('[role="status"]').textContent, /recoveryPaused/);
    assert.equal(timers.size, 1);
    const [id, callback] = timers.entries().next().value;
    timers.delete(id);
    await act(async () => callback());
    assert.equal(doc.querySelectorAll('[role="option"]').length, 1);
    assert.equal(timers.size, 0);
    await act(async () => finishRefresh());
    assert.equal(doc.querySelectorAll('[role="option"]').length, 2);
    assert.match(doc.querySelector('[role="status"]').textContent, /recoveryPaused/);
    assert.doesNotMatch(doc.querySelector('[role="status"]').textContent, /restoringHistory/);
    assert.equal(doc.querySelector('[role="status"] button'), null);
    assert.equal(timers.size, 0);
    await act(async () => doc.querySelector(".new-chat-agent-picker__trigger").click());
    await openHermes();
    assert.equal(timers.size, 1);
    await act(async () => doc.querySelector(".new-chat-agent-picker__trigger").click());
    assert.equal(timers.size, 0);
    assert.equal(calls, 3);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  }
});
