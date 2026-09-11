import assert from "node:assert/strict";
import { mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";

// Match the CommonJS module used by the compiled component so context is shared
const { I18nextProvider } = createRequire(import.meta.url)("react-i18next");

const temp = mkdtempSync(join(tmpdir(), "quick-agent-selection-test-"));
after(() => rmSync(temp, { recursive: true, force: true }));
symlinkSync(fileURLToPath(new URL("../node_modules", import.meta.url)), join(temp, "node_modules"), "dir");
const compiledPath = join(temp, "dialog.cjs");
await build({
  entryPoints: [fileURLToPath(new URL("../src/create/deepseek/QuickAgentCreateDialog.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", target: "node20",
  external: ["react", "react-dom", "react-dom/*", "react-i18next", "i18next"],
  loader: { ".css": "empty" }, outfile: compiledPath,
});
const Dialog = createRequire(import.meta.url)(compiledPath).default;
const i18n = i18next.createInstance();
await i18n.init({ lng: "en", resources: { en: { deepseek: { title: "Quick-create Agent", agentType: "Agent type", continue: "Continue", cancel: "Cancel", close: "Close" } } } });

test("the dialog selects a type with native radios and continues only after confirmation", async () => {
  const dom = new JSDOM('<div id="root"><button id="launcher">Create</button></div>', { url: "http://localhost" });
  const globals = { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node, IS_REACT_ACT_ENVIRONMENT: true };
  const previous = Object.fromEntries(Object.keys(globals).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const selected = [];
  let cancelled = 0;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = (open) => React.createElement(I18nextProvider, { i18n }, React.createElement(Dialog, { open, onClose: () => cancelled++, onSelect: (kind) => selected.push(kind) }));
  try {
    document.getElementById("launcher").focus();
    await act(async () => root.render(render(true)));
    const dialog = document.querySelector('[role="dialog"]');
    assert.ok(dialog);
    const radios = [...dialog.querySelectorAll('input[type="radio"]')];
    assert.equal(radios.length, 2);
    assert.equal(radios[0].checked, true);
    assert.equal(dialog.querySelector("table"), null);
    await act(async () => radios[1].click());
    assert.equal(radios[1].checked, true);
    assert.deepEqual(selected, []);
    const proceed = dialog.querySelector('button[type="submit"]');
    assert.ok(proceed, "The type picker must offer a Continue action");
    assert.match(proceed.textContent, /Continue/);
    await act(async () => proceed.click());
    assert.deepEqual(selected, ["deepseek"]);
    await act(async () => root.render(render(false)));
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(document.getElementById("root").inert, false);
    assert.equal(document.activeElement.id, "launcher");
    await act(async () => root.render(render(true)));
    await act(async () => window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", isComposing: true })));
    assert.equal(cancelled, 0);
    await act(async () => window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape" })));
    assert.equal(cancelled, 1);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    for (const key of Object.keys(globals)) {
      if (previous[key]) Object.defineProperty(globalThis, key, previous[key]);
      else delete globalThis[key];
    }
  }
});
