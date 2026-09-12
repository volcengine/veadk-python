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
  return [
    {
    kind: "tool",
      name: "exec_command",
      callId: "command-1",
      args: { command: "npm test" },
    response: status === "failed" ? "exit code 1" : undefined,
    done: status !== "running",
    status,
    ...(defaultOpen ? { defaultOpen: true } : {}),
    },
  ];
}

test("opens a newly failed tool while preserving the user's disclosure choice", async () => {
  const view = await renderBlocks(tool("running"));
  try {
    const button = () => view.container.querySelector(".tool-activity__head");
    const disclosure = () =>
      view.container.querySelector(".tool-activity__collapse");
    assert.equal(button()?.getAttribute("aria-expanded"), "true");

    await view.render(tool("failed", true));
    assert.equal(button()?.getAttribute("aria-expanded"), "true");
    assert.match(disclosure()?.className ?? "", /\bis-open\b/);

    await view.act(async () => button()?.click());
    assert.equal(button()?.getAttribute("aria-expanded"), "false");
    assert.equal(disclosure()?.getAttribute("aria-hidden"), "true");
    assert.ok(disclosure()?.hasAttribute("inert"));

    await view.render(tool("running"));
    await view.render(tool("failed", true));
    assert.equal(button()?.getAttribute("aria-expanded"), "false");
  } finally {
    await view.cleanup();
  }
});

test("reports clipboard failures without an unhandled rejection", async () => {
  const view = await renderBlocks([
    {
      kind: "tool",
      name: "exec_command",
      callId: "command-copy",
      args: { command: "npm test" },
      response: { output: "done" },
      done: true,
      status: "completed",
      defaultOpen: true,
    },
  ]);
  try {
    Object.defineProperty(globalThis.navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("denied");
        },
      },
    });
    const rawButton = [...view.container.querySelectorAll("button")].find(
      (button) => button.textContent?.includes("View raw data"),
    );
    await view.act(async () => rawButton?.click());
    const copyButton = view.container.querySelector(
      ".tool-activity__raw-id button",
    );
    assert.ok(copyButton);
    await view.act(async () => {
      copyButton?.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    assert.match(view.container.textContent ?? "", /Copy failed. Try again./);
    assert.equal(
      view.container.querySelector('[role="alert"]')?.textContent,
      "Copy failed. Try again.",
    );
  } finally {
    await view.cleanup();
  }
});

test("keeps localized labels when read-only tools are grouped", async () => {
  const view = await renderBlocks([
    {
      kind: "tool",
      name: "web_search",
      callId: "search-1",
      args: { query: "A2A" },
      response: { count: 2 },
      done: true,
      status: "completed",
    },
    {
      kind: "tool",
      name: "link_reader",
      callId: "read-1",
      args: { path: "https://example.test" },
      response: { ok: true },
      done: true,
      status: "completed",
    },
  ]);
  try {
    const groupButton = view.container.querySelector(
      ".tool-activity--exploration > .tool-activity__head",
    );
    await view.act(async () => groupButton?.click());

    assert.match(view.container.textContent ?? "", /Web search complete/);
    assert.match(view.container.textContent ?? "", /Webpage read complete/);
  } finally {
    await view.cleanup();
  }
});
