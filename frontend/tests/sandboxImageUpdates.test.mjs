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
const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/ui/SystemInfo.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*"],
  plugins: [{ name: "test-stubs", setup(b) {
    b.onResolve({ filter: /^react-i18next$/ }, () => ({ path: "translations", namespace: "i18n-mock" }));
    b.onLoad({ filter: /.*/, namespace: "i18n-mock" }, () => ({ contents: `
      const resources = ${JSON.stringify({
        "zh-CN": JSON.parse(readFileSync(new URL("../src/i18n/resources/zh-CN/ui.json", import.meta.url), "utf8")),
        "en-US": JSON.parse(readFileSync(new URL("../src/i18n/resources/en-US/ui.json", import.meta.url), "utf8")),
      })};
      export function useTranslation() { return { t(key, options = {}) {
        const value = key.split(".").reduce((obj, part) => obj?.[part], resources[globalThis.sandboxTestLocale || "zh-CN"]) || key;
        return value.replace(/{{(\\w+)}}/g, (_, name) => options[name] || "");
      } }; }
    `, loader: "js" }));
    b.onResolve({ filter: /\/adk\/client$/ }, () => ({ path: "client", namespace: "mock" }));
    b.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: `
      export const getSystemInfo = (...args) => globalThis.sandboxApi.getSystemInfo(...args);
      export const getSandboxImageUpdates = (...args) => globalThis.sandboxApi.getSandboxImageUpdates(...args);
      export const updateSandboxTool = (...args) => globalThis.sandboxApi.updateSandboxTool(...args);
      export const listIdentityUserPools = async () => [];
      export const getEnvironmentResources = async () => null;
    `, loader: "js" }));
    b.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
  } }],
});
const module = { exports: {} };
Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
const { SystemInfo } = module.exports;

const state = {
  toolId: "shared", provider: "volcengine", region: "cn-shanghai", toolType: "CodeEnv",
  status: "Ready", currentImage: "registry/code:1", latestImage: "registry/code:2",
  needsImageUpdate: true, needsModelEnvUpdate: false, canUpdateModelEnv: false,
  modelEnvError: "", error: "", canUpdate: true,
};

async function mount(api) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { pretendToBeVisual: true });
  const values = { window: dom.window, document: dom.window.document,
    navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement,
    Element: dom.window.Element, SVGElement: dom.window.SVGElement,
    getComputedStyle: dom.window.getComputedStyle,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    IS_REACT_ACT_ENVIRONMENT: true, sandboxApi: api };
  const previous = new Map(Object.keys(values).map(k => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
  for (const [k, value] of Object.entries(values)) Object.defineProperty(globalThis, k, { configurable: true, writable: true, value });
  const { createRoot } = require("react-dom/client");
  const root = createRoot(dom.window.document.getElementById("root"));
  await act(async () => root.render(React.createElement(SystemInfo, {
    version: "test", localMode: true, role: "admin", provider: "volcengine", region: "cn-beijing", onBack() {},
  })));
  return { document: dom.window.document, async cleanup() {
    await act(async () => root.unmount()); dom.window.close();
    for (const [k, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, k, descriptor); else delete globalThis[k];
    }
  } };
}

function api(overrides = {}) {
  return {
    async getSystemInfo() { return { storage: { tosAddress: "" }, sandboxTools: [
      { kind: "codex", label: "Codex Sandbox", toolId: "shared", snapshot: false },
      { kind: "deepseek_harness", label: "DeepSeek Harness Sandbox", toolId: "shared", snapshot: false },
    ] }; },
    async getSandboxImageUpdates() { return [state]; },
    async updateSandboxTool() { return { updated: true, state: { ...state, canUpdate: false, needsImageUpdate: false, currentImage: state.latestImage } }; },
    ...overrides,
  };
}

test("shared Codex and DSH rows disable together and refresh after one update", async () => {
  let finish; let calls = 0;
  const view = await mount(api({ updateSandboxTool() { calls++; return new Promise(resolve => { finish = resolve; }); } }));
  try {
    const buttons = [...view.document.querySelectorAll(".system-info-resource-update")];
    assert.equal(buttons.length, 2);
    await act(async () => { buttons[0].click(); buttons[1].click(); });
    assert.equal(calls, 1);
    assert.ok(buttons.every(b => b.disabled));
    await act(async () => finish({ updated: true, state: { ...state, currentImage: state.latestImage, needsImageUpdate: false, canUpdate: false } }));
    assert.equal(view.document.querySelectorAll(".system-info-resource-update").length, 0);
    assert.equal([...view.document.querySelectorAll('[role="status"]')].filter(n => n.textContent === "已更新").length, 2);
    assert.doesNotMatch(view.document.body.textContent, /cn-shanghai/);
    assert.ok([...view.document.querySelectorAll(".system-info-tool a")].every(link => link.href.includes("cn-shanghai")));
  } finally { await view.cleanup(); }
});

test("failed update shows a shared error and permits retry", async () => {
  let calls = 0;
  const view = await mount(api({ async updateSandboxTool() { calls++; if (calls === 1) throw new Error("更新失败，请重试"); return { updated: false, state: { ...state, canUpdate: false } }; } }));
  try {
    await act(async () => view.document.querySelector(".system-info-resource-update").click());
    assert.equal(view.document.querySelectorAll('.system-info-inline-error[role="alert"]').length, 2);
    assert.equal(view.document.querySelector(".system-info-resource-update").disabled, false);
    await act(async () => view.document.querySelectorAll(".system-info-resource-update")[1].click());
    assert.equal(calls, 2);
  } finally { await view.cleanup(); }
});

test("version inspection failure is visible and refresh retries", async () => {
  let calls = 0;
  const view = await mount(api({ async getSandboxImageUpdates() { calls++; if (calls === 1) throw new Error("版本检查失败"); return [state]; } }));
  try {
    assert.match(view.document.body.textContent, /查询沙箱版本失败/);
    assert.equal(view.document.querySelectorAll(".system-info-resource-update").length, 0);
    await act(async () => view.document.querySelector(".system-info-refresh").click());
    assert.equal(calls, 2);
    assert.equal(view.document.querySelectorAll(".system-info-resource-update").length, 2);
  } finally { await view.cleanup(); }
});


test("sandbox update controls use the English locale", async () => {
  globalThis.sandboxTestLocale = "en-US";
  const view = await mount(api());
  try {
    assert.match(view.document.body.textContent, /Check for updates/);
    assert.match(view.document.querySelector(".system-info-resource-update").getAttribute("aria-label"), /^Update /);
  } finally {
    await view.cleanup();
    delete globalThis.sandboxTestLocale;
  }
});
