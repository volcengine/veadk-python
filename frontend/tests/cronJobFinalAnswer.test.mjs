import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);

async function loadComponent() {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(
      "../src/cronjobs/CronJobFinalAnswer.tsx",
      import.meta.url,
    ))],
    bundle: true,
    external: ["react", "react-dom", "react-dom/*"],
    format: "cjs",
    platform: "node",
    plugins: [{
      name: "apps-sdk-button-test-stub",
      setup(build) {
        build.onResolve(
          { filter: /^@openai\/apps-sdk-ui\/components\/Button$/ },
          () => ({ path: "button-stub", namespace: "test" }),
        );
        build.onLoad(
          { filter: /^button-stub$/, namespace: "test" },
          () => ({
            contents: `
              import React from "react";
              export function Button({ color, variant, size, pill, uniform, loading, opticallyAlign, ...props }) {
                return <button {...props} />;
              }
            `,
            loader: "tsx",
          }),
        );
      },
    }],
    write: false,
  });
  const module = { exports: {} };
  Function("require", "module", "exports", result.outputFiles[0].text)(
    require,
    module,
    module.exports,
  );
  return module.exports.CronJobFinalAnswer;
}

async function renderFinalAnswer(output, overflowed) {
  const dom = new JSDOM("<!doctype html><div id=\"root\"></div>", {
    pretendToBeVisual: true,
  });
  const globalNames = [
    "window",
    "document",
    "navigator",
    "HTMLElement",
    "Node",
    "Event",
    "MouseEvent",
    "getComputedStyle",
    "requestAnimationFrame",
    "cancelAnimationFrame",
    "ResizeObserver",
    "IS_REACT_ACT_ENVIRONMENT",
  ];
  const previousGlobals = new Map(globalNames.map((name) => [
    name,
    Object.getOwnPropertyDescriptor(globalThis, name),
  ]));

  class TestResizeObserver {
    constructor(callback) {
      this.callback = callback;
    }

    observe(target) {
      this.callback([{ target }]);
    }

    disconnect() {}
  }

  const testGlobals = {
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement,
    Node: dom.window.Node,
    Event: dom.window.Event,
    MouseEvent: dom.window.MouseEvent,
    getComputedStyle: dom.window.getComputedStyle,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    ResizeObserver: TestResizeObserver,
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  for (const [name, value] of Object.entries(testGlobals)) {
    Object.defineProperty(globalThis, name, {
      configurable: true,
      enumerable: true,
      value,
      writable: true,
    });
  }

  Object.defineProperties(dom.window.HTMLParagraphElement.prototype, {
    clientHeight: { configurable: true, get: () => 52 },
    scrollHeight: { configurable: true, get: () => overflowed ? 104 : 52 },
  });

  const React = require("react");
  const { createRoot } = require("react-dom/client");
  const { act } = React;
  const CronJobFinalAnswer = await loadComponent();
  const container = dom.window.document.getElementById("root");
  const root = createRoot(container);
  await act(async () => {
    root.render(React.createElement(CronJobFinalAnswer, { output }));
  });

  return {
    act,
    container,
    cleanup: async () => {
      await act(async () => root.unmount());
      dom.window.close();
      for (const [name, descriptor] of previousGlobals) {
        if (descriptor === undefined) delete globalThis[name];
        else Object.defineProperty(globalThis, name, descriptor);
      }
    },
  };
}

test("keeps a short final answer uncluttered", async () => {
  const view = await renderFinalAnswer("简短回答。", false);
  try {
    assert.equal(view.container.querySelector("p")?.textContent, "简短回答。");
    assert.equal(view.container.querySelector("button"), null);
  } finally {
    await view.cleanup();
  }
});

test("expands and collapses a genuinely overflowing final answer", async () => {
  const view = await renderFinalAnswer("很长的回答。".repeat(80), true);
  try {
    const paragraph = view.container.querySelector("p");
    const button = view.container.querySelector("button");
    assert.ok(paragraph);
    assert.ok(button);
    assert.equal(button.type, "button");
    assert.equal(button.textContent?.trim(), "展开");
    assert.equal(button.getAttribute("aria-expanded"), "false");
    assert.equal(button.getAttribute("aria-controls"), paragraph.id);

    await view.act(async () => button.click());
    assert.equal(button.textContent?.trim(), "收起");
    assert.equal(button.getAttribute("aria-expanded"), "true");
    assert.match(paragraph.parentElement?.className ?? "", /is-expanded/);

    await view.act(async () => button.click());
    assert.equal(button.textContent?.trim(), "展开");
    assert.equal(button.getAttribute("aria-expanded"), "false");
    assert.doesNotMatch(paragraph.parentElement?.className ?? "", /is-expanded/);
  } finally {
    await view.cleanup();
  }
});
