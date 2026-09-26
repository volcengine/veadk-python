import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);
const React = require("react");
const { act } = React;
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost", pretendToBeVisual: true });
const globals = {
  window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
  HTMLElement: dom.window.HTMLElement, HTMLInputElement: dom.window.HTMLInputElement,
  HTMLFormElement: dom.window.HTMLFormElement,
  Node: dom.window.Node, IS_REACT_ACT_ENVIRONMENT: true,
};
const previous = new Map(Object.keys(globals).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
const { createRoot } = require("react-dom/client");
const { I18nextProvider } = require("react-i18next");
const i18n = require("i18next").createInstance();
await i18n.init({ lng: "zh-CN", resources: Object.fromEntries(["zh-CN", "en-US"].map((locale) => [locale, {
  create: JSON.parse(readFileSync(new URL(`../src/i18n/resources/${locale}/create.json`, import.meta.url), "utf8")),
}])) });
const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/create/ContextCompressionFields.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*", "react-i18next"],
  plugins: [{ name: "no-css-in-dom-test", setup(builder) {
    builder.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
  } }],
});
const loaded = { exports: {} };
Function("require", "module", "exports", result.outputFiles[0].text)(require, loaded, loaded.exports);
const { ContextCompressionFields } = loaded.exports;

test.after(() => {
  dom.window.close();
  for (const [key, descriptor] of previous) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

for (const variant of ["traditional", "workbench"]) {
  test(`${variant} preserves capacity when toggled and prevents changes while disabled`, async () => {
    const root = createRoot(document.getElementById("root"));
    let policy = { mode: "auto", context_window: 32000, output_reserve: 4000 };
    let disabled = false;
    const render = () => root.render(React.createElement(I18nextProvider, { i18n },
      React.createElement(ContextCompressionFields, { variant, value: policy, disabled,
        onChange(next) { policy = next; render(); } })));
    try {
      await act(render);
      const control = document.querySelector('[role="switch"]');
      assert.ok(control);
      assert.equal(control.getAttribute("aria-checked"), "true");
      assert.equal(control.getAttribute("aria-label"), "自动压缩上下文");
      await act(async () => control.click());
      assert.deepEqual(policy, { mode: "off", context_window: 32000, output_reserve: 4000 });
      assert.match(document.body.textContent, /不自动整理上下文/);
      await act(async () => control.click());
      assert.equal(policy.mode, "auto");
      disabled = true;
      await act(render);
      assert.equal(control.disabled, true);
      await act(async () => control.click());
      assert.equal(policy.mode, "auto");
      assert.ok([...document.querySelectorAll('input[type="number"]')].every((input) => input.disabled));
    } finally { await act(async () => root.unmount()); }
  });
}

test("invalid capacity is visible, correction and clear reach the draft, and labels are bilingual", async () => {
  const root = createRoot(document.getElementById("root"));
  let policy = { mode: "auto", context_window: -1 };
  const render = () => root.render(React.createElement(I18nextProvider, { i18n },
    React.createElement(ContextCompressionFields, { variant: "workbench", value: policy,
      onChange(next) { policy = next; render(); } })));
  try {
    await act(render);
    assert.match(document.querySelector('[role="alert"]').textContent, /正整数/);
    const input = document.querySelector('input[type="number"]');
    const setValue = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    await act(async () => { setValue.call(input, "64000"); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    assert.equal(policy.context_window, 64000);
    assert.equal(document.querySelector('[role="alert"]'), null);
    await act(async () => { setValue.call(input, ""); input.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
    assert.equal(policy.context_window, undefined);
    await act(async () => i18n.changeLanguage("en-US"));
    assert.equal(document.querySelector('[role="switch"]').getAttribute("aria-label"), "Automatic context compression");
  } finally { await act(async () => root.unmount()); }
});


test("percentage controls preserve ratios and reject invalid ordering until corrected", async () => {
  const root = createRoot(document.getElementById("root"));
  let policy = { mode: "auto" };
  const render = () => root.render(React.createElement(I18nextProvider, { i18n },
    React.createElement(ContextCompressionFields, { variant: "workbench", value: policy,
      onChange(next) { policy = next; render(); } })));
  try {
    await act(render);
    const inputs = [...document.querySelectorAll('input[type="number"]')];
    assert.equal(inputs.length, 6);
    assert.equal(inputs[3].placeholder, "80");
    const setValue = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set;
    const change = async (index, value) => act(async () => {
      setValue.call(inputs[index], value);
      inputs[index].dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    await change(3, "75");
    assert.equal(policy.trigger_ratio, 0.75);
    await change(4, "90");
    assert.equal(policy.target_ratio, 0.9);
    assert.ok(document.querySelector('[role="alert"]'));
    await change(4, "50");
    assert.equal(policy.target_ratio, 0.5);
    assert.equal(document.querySelector('[role="alert"]'), null);
    await change(3, "");
    assert.equal(policy.trigger_ratio, undefined);
    await act(async () => inputs[3].dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    assert.equal(policy.mode, "auto");
  } finally { await act(async () => root.unmount()); }
});
