import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);
const React = require("react");
const { act } = React;
const translations = JSON.parse(readFileSync(new URL("../src/i18n/resources/zh-CN/sandbox.json", import.meta.url), "utf8"));
const built = await build({
  entryPoints: [fileURLToPath(new URL("../src/ui/SandboxAgentDetails.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*"],
  plugins: [{ name: "test-stubs", setup(b) {
    b.onResolve({ filter: /^react-i18next$/ }, () => ({ path: "translations", namespace: "mock-i18n" }));
    b.onLoad({ filter: /.*/, namespace: "mock-i18n" }, () => ({ contents: `
      const resources = ${JSON.stringify(translations)};
      export function useTranslation() { return { i18n: { language: "zh-CN" }, t(key, options = {}) {
        return (key.split(".").reduce((obj, part) => obj?.[part], resources) || key).replace(/{{(\\w+)}}/g, (_, key) => options[key] || "");
      } }; }
    ` }));
    b.onResolve({ filter: /\/adk\/sandbox$/ }, () => ({ path: "status", namespace: "mock-status" }));
    b.onLoad({ filter: /.*/, namespace: "mock-status" }, () => ({ contents: 'export const sandboxStatusLabel = status => status === "Wakeable" ? "已休眠" : "异常";' }));
    b.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
  } }],
});
const module = { exports: {} };
Function("require", "module", "exports", built.outputFiles[0].text)(require, module, module.exports);
const { SandboxAgentDetails } = module.exports;

async function mount(callbacks = {}, status = "Wakeable") {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { pretendToBeVisual: true });
  const values = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true };
  const previous = new Map(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const { createRoot } = require("react-dom/client");
  const root = createRoot(dom.window.document.getElementById("root"));
  await act(async () => root.render(React.createElement(SandboxAgentDetails, {
    session: { resourceType: "snapshot", id: "saved", snapshotId: "saved", sourceSessionId: "agent-1", toolName: "hermes", displayName: "测试智能体", createdBy: "Alice", status, createdAt: "2026-09-08", snapshotStatus: "Ready" },
    onBack() {}, async onOpen() {}, async onDelete() {}, ...callbacks,
  })));
  return { document: dom.window.document, async cleanup() {
    await act(async () => root.unmount()); dom.window.close();
    for (const [key, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  } };
}

test("sleeping agent shows wake progress, blocks duplicate actions, and allows retry", async () => {
  let fail; let calls = 0;
  const view = await mount({ onOpen() { calls++; return calls === 1 ? new Promise((_, reject) => { fail = reject; }) : Promise.resolve(); } });
  try {
    assert.match(view.document.body.textContent, /Alice/);
    assert.match(view.document.body.textContent, /已休眠/);
    assert.doesNotMatch(view.document.body.textContent, /快照|Snapshot|Session|Tool|sandbox/i);
    const open = view.document.querySelector(".sandbox-agent-open");
    await act(async () => open.click());
    assert.match(view.document.querySelector('[role="status"]').textContent, /正在唤醒智能体/);
    assert.ok(open.disabled);
    assert.ok(view.document.querySelector(".sandbox-agent-delete").disabled);
    await act(async () => open.click());
    assert.equal(calls, 1);
    await act(async () => fail(new Error("唤醒失败，请重试")));
    assert.match(view.document.querySelector('[role="alert"]').textContent, /唤醒失败/);
    assert.equal(open.disabled, false);
    await act(async () => open.click());
    assert.equal(calls, 2);
    assert.equal(view.document.querySelector('[role="alert"]'), null);
  } finally { await view.cleanup(); }
});

test("failed saved agents remain deletable with agent-only confirmation", async () => {
  let deletes = 0;
  const view = await mount({ async onDelete() { deletes++; } }, "Failed");
  try {
    assert.ok(view.document.querySelector(".sandbox-agent-open").disabled);
    await act(async () => view.document.querySelector(".sandbox-agent-delete").click());
    const confirm = view.document.querySelector('[role="alertdialog"]');
    assert.match(confirm.textContent, /删除智能体/);
    assert.doesNotMatch(confirm.textContent, /快照|Snapshot|Session|Tool/i);
    assert.equal(deletes, 0);
    await act(async () => confirm.querySelector(".confirm-btn--danger").click());
    assert.equal(deletes, 1);
  } finally { await view.cleanup(); }
});
