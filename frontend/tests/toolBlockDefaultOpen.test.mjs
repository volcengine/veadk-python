import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);

async function loadBlocks() {
  const result = await build({
    entryPoints: [fileURLToPath(new URL("../src/ui/Blocks.tsx", import.meta.url))],
    bundle: true,
    external: ["react", "react-dom", "react-dom/*"],
    format: "cjs",
    platform: "node",
    plugins: [{
      name: "css-test-stub",
      setup(buildContext) {
        buildContext.onLoad(
          { filter: /\.css$/ },
          () => ({ contents: "export default {};", loader: "js" }),
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
  return module.exports.Blocks;
}

async function renderBlocks(initialBlocks) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {
    pretendToBeVisual: true,
  });
  const globalNames = [
    "window",
    "document",
    "navigator",
    "Element",
    "HTMLElement",
    "SVGElement",
    "Node",
    "Event",
    "MouseEvent",
    "getComputedStyle",
    "requestAnimationFrame",
    "cancelAnimationFrame",
    "IS_REACT_ACT_ENVIRONMENT",
  ];
  const previousGlobals = new Map(globalNames.map((name) => [
    name,
    Object.getOwnPropertyDescriptor(globalThis, name),
  ]));
  const testGlobals = {
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    Element: dom.window.Element,
    HTMLElement: dom.window.HTMLElement,
    SVGElement: dom.window.SVGElement,
    Node: dom.window.Node,
    Event: dom.window.Event,
    MouseEvent: dom.window.MouseEvent,
    getComputedStyle: dom.window.getComputedStyle,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
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

  const React = require("react");
  const { createRoot } = require("react-dom/client");
  const { act } = React;
  const Blocks = await loadBlocks();
  const container = dom.window.document.getElementById("root");
  const root = createRoot(container);
  const render = async (blocks) => {
    await act(async () => {
      root.render(React.createElement(Blocks, { blocks }));
    });
  };
  await render(initialBlocks);

  return {
    act,
    container,
    render,
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

function tool(status, defaultOpen = false) {
  return [{
    kind: "tool",
    name: status === "failed" ? "命令执行失败" : "正在执行命令",
    response: status === "failed" ? "exit code 1" : undefined,
    done: status !== "running",
    status,
    ...(defaultOpen ? { defaultOpen: true } : {}),
  }];
}

test("opens a newly failed tool while preserving the user's disclosure choice", async () => {
  const view = await renderBlocks(tool("running"));
  try {
    const button = () => view.container.querySelector(".tool-head");
    const disclosure = () => view.container.querySelector(".think-collapse");
    assert.equal(button()?.getAttribute("aria-expanded"), "false");

    await view.render(tool("failed", true));
    assert.equal(button()?.getAttribute("aria-expanded"), "true");
    assert.match(disclosure()?.className ?? "", /\bopen\b/);

    await view.act(async () => button()?.click());
    assert.equal(button()?.getAttribute("aria-expanded"), "false");

    await view.render(tool("running"));
    await view.render(tool("failed", true));
    assert.equal(button()?.getAttribute("aria-expanded"), "false");
  } finally {
    await view.cleanup();
  }
});
