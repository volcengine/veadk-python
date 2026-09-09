import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);
const resources = JSON.parse(
  readFileSync(
    new URL("../src/i18n/resources/zh-CN/migrations.json", import.meta.url),
    "utf8",
  ),
);

const bundle = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/migrations/MigrationEvaluation.tsx", import.meta.url),
    ),
  ],
  bundle: true,
  external: ["react", "react-dom", "react-dom/*"],
  format: "cjs",
  platform: "node",
  plugins: [
    {
      name: "migration-evaluation-test-stubs",
      setup(buildContext) {
        buildContext.onResolve({ filter: /^react-i18next$/ }, () => ({
          path: "translations",
          namespace: "i18n-mock",
        }));
        buildContext.onLoad(
          { filter: /.*/, namespace: "i18n-mock" },
          () => ({
            contents: `
              const resources = ${JSON.stringify(resources)};
              export function useTranslation() {
                return {
                  t(key, options = {}) {
                    const value = key.split(".").reduce(
                      (current, part) => current?.[part],
                      resources,
                    ) ?? key;
                    return typeof value === "string"
                      ? value.replace(/{{(\\w+)}}/g, (_, name) => String(options[name] ?? ""))
                      : key;
                  },
                };
              }
            `,
            loader: "js",
          }),
        );
        buildContext.onLoad({ filter: /\.css$/ }, () => ({
          contents: "",
          loader: "js",
        }));
      },
    },
  ],
  write: false,
});
const module = { exports: {} };
Function("require", "module", "exports", bundle.outputFiles[0].text)(
  require,
  module,
  module.exports,
);
const {
  createMigrationEvaluationDraft,
  MigrationEvaluationResult,
  MigrationEvaluationSetup,
} = module.exports;

const dimensionIds = [
  "semantic_fidelity",
  "output_contract",
  "workflow_tool_fidelity",
  "context_memory_fidelity",
  "boundary_error_fidelity",
  "safety_refusal_fidelity",
];
const capability = {
  available: true,
  dimensions: dimensionIds.map((id) => ({ id })),
};

async function mount(elementFactory) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {
    pretendToBeVisual: true,
  });
  const values = {
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    Element: dom.window.Element,
    HTMLElement: dom.window.HTMLElement,
    SVGElement: dom.window.SVGElement,
    Node: dom.window.Node,
    Event: dom.window.Event,
    MouseEvent: dom.window.MouseEvent,
    KeyboardEvent: dom.window.KeyboardEvent,
    getComputedStyle: dom.window.getComputedStyle,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  const previous = new Map(
    Object.keys(values).map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(globalThis, key, {
      configurable: true,
      value,
      writable: true,
    });
  }

  const React = require("react");
  const { act } = React;
  const { createRoot } = require("react-dom/client");
  const container = dom.window.document.getElementById("root");
  const root = createRoot(container);
  const render = async (props) => {
    await act(async () => {
      root.render(elementFactory(React, props));
    });
  };

  return {
    act,
    container,
    document: dom.window.document,
    render,
    settle: () => act(() => new Promise((resolve) => setTimeout(resolve, 0))),
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      for (const [key, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else delete globalThis[key];
      }
    },
  };
}

test("selects a custom evaluation method before editing questions", async () => {
  const view = await mount((React) => {
    function Harness() {
      const [draft, setDraft] = React.useState(() => ({
        ...createMigrationEvaluationDraft(),
        enabled: false,
      }));
      return React.createElement(MigrationEvaluationSetup, {
        value: draft,
        onChange: setDraft,
        capability,
        disabled: false,
        errors: {},
      });
    }
    return React.createElement(Harness);
  });
  try {
    await view.render();
    const toggle = view.container.querySelector('[role="switch"]');
    toggle.focus();
    await view.act(async () => toggle.click());
    await view.settle();

    const method = view.document.querySelector(
      ".migration-evaluation-advanced",
    );
    const questions = view.document.querySelector(".migration-evaluation-cases");
    assert.ok(
      method.compareDocumentPosition(questions) &
        view.document.defaultView.Node.DOCUMENT_POSITION_FOLLOWING,
    );

    const custom = view.document.querySelector('input[value="custom"]');
    await view.act(async () => custom.click());
    assert.equal(custom.checked, true);
    assert.equal(
      view.document.querySelectorAll(".migration-evaluation-dimensions input")
        .length,
      dimensionIds.length,
    );

    const dimensionInputs = view.document.querySelectorAll(
      '.migration-evaluation-dimensions input[type="checkbox"]',
    );
    const safety = dimensionInputs[dimensionInputs.length - 1];
    await view.act(async () => safety.click());
    assert.equal(safety.checked, true);

    const dialog = view.document.querySelector('[role="dialog"]');
    const dialogButtons = dialog.querySelectorAll("button:not([disabled])");
    dialogButtons[dialogButtons.length - 1].focus();
    await view.act(async () => {
      view.document.defaultView.dispatchEvent(
        new view.document.defaultView.KeyboardEvent("keydown", {
          key: "Tab",
          bubbles: true,
        }),
      );
    });
    assert.equal(
      view.document.activeElement,
      dialog.querySelector(".migration-evaluation-drawer__close"),
    );

    await view.act(async () => {
      view.document.defaultView.dispatchEvent(
        new view.document.defaultView.KeyboardEvent("keydown", {
          key: "Escape",
          bubbles: true,
        }),
      );
    });
    assert.equal(view.document.querySelector('[role="dialog"]'), null);
    assert.equal(view.document.activeElement, toggle);

    const editButton = view.container.querySelector(
      ".migration-evaluation-setup__summary button",
    );
    editButton.focus();
    await view.act(async () => editButton.click());
    const scrim = view.document.querySelector(".migration-evaluation-drawer");
    await view.act(async () => {
      scrim.dispatchEvent(
        new view.document.defaultView.MouseEvent("mousedown", {
          bubbles: true,
        }),
      );
    });
    assert.equal(view.document.querySelector('[role="dialog"]'), null);
    assert.equal(view.document.activeElement, editButton);
  } finally {
    await view.cleanup();
  }
});

test("loads and renders the HTML report only after the user opens it", async () => {
  let loadCalls = 0;
  const evaluation = {
    enabled: true,
    state: "completed",
    message: "done",
    dimensions: dimensionIds.slice(0, 3),
    report: {
      schemaVersion: 1,
      kind: "report",
      assetId: "report-1",
      version: "v1",
      versionId: "version-1",
      sha256: "a".repeat(64),
      sizeBytes: 20,
      size: 20,
      createdAt: "2026-09-09T00:00:00Z",
      acl: "owner",
      viewReady: true,
      downloadReady: true,
    },
  };
  const view = await mount((React, props) =>
    React.createElement(MigrationEvaluationResult, {
      evaluation,
      report: null,
      reportLoading: false,
      reportError: "",
      actionError: "",
      busy: false,
      reportDownloading: false,
      onResume() {},
      onRetry() {},
      onLoadReport() {
        loadCalls += 1;
      },
      onDownloadReport() {},
      ...props,
    }),
  );
  try {
    await view.render();
    assert.equal(loadCalls, 0);
    assert.equal(view.document.querySelector("iframe"), null);

    const viewButton = view.document.querySelector(
      ".migration-evaluation-report-actions .is-primary",
    );
    viewButton.focus();
    await view.act(async () => viewButton.click());
    await view.settle();
    assert.equal(loadCalls, 1);
    assert.ok(view.document.querySelector('[role="dialog"]'));
    assert.equal(view.document.querySelector("iframe"), null);
    assert.match(view.document.body.textContent, /正在读取评测报告/);

    await view.render({ reportError: "报告读取失败" });
    const retry = view.document.querySelector(
      ".migration-evaluation-drawer .migration-evaluation-failure button",
    );
    await view.act(async () => retry.click());
    assert.equal(loadCalls, 2);

    await view.render({
      report: "<!doctype html><html><body>report ready</body></html>",
      reportError: "",
    });
    const iframe = view.document.querySelector("iframe");
    assert.match(iframe.getAttribute("srcdoc"), /report ready/);

    await view.act(async () => {
      view.document.defaultView.dispatchEvent(
        new view.document.defaultView.KeyboardEvent("keydown", {
          key: "Escape",
          bubbles: true,
        }),
      );
    });
    assert.equal(view.document.querySelector('[role="dialog"]'), null);
    assert.equal(view.document.activeElement, viewButton);
  } finally {
    await view.cleanup();
  }
});
