import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
const require = createRequire(import.meta.url);

test("project creation waits for a name, prevents duplicate submissions and preserves the editor in management", async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost", pretendToBeVisual: true });
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  dom.window.localStorage.setItem("agentkit.studio.locale", "zh-CN");
  const previous = new Map();
  for (const [name, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true })) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
  }
  const calls = [];
  let finish;
  let finishRecovery;
  let workspaceState = {status: "ready", sessionId: "one", expireAt: "2099-01-01T00:00:00Z"};
  globalThis.workspaceMock = {
    getWorkspaceState: async () => workspaceState,
    listWorkspaceProjects: async () => [],
    createWorkspaceProject: name => { calls.push(name); return new Promise(resolve => { finish = resolve; }); },
    openWorkspaceProject: name => { assert.equal(name, "my-agent"); return new Promise(resolve => { finishRecovery = resolve; }); },
  };
  const result = await build({
    entryPoints: [fileURLToPath(new URL("../src/create/WorkspaceCreate.tsx", import.meta.url))],
    bundle: true, format: "cjs", platform: "node", write: false, jsx: "automatic", external: ["react", "react-dom/*"],
    plugins: [{ name: "mock-workspace", setup(b) {
      b.onLoad({ filter: /WorkspaceCreate\.tsx$/ }, args => ({
        contents: readFileSync(args.path, "utf8") + `
          import { i18n as testI18n } from "../i18n/runtime";
          import enUi from "../i18n/resources/en-US/ui.json";
          import zhUi from "../i18n/resources/zh-CN/ui.json";
          testI18n.addResourceBundle("en-US", "ui", enUi);
          testI18n.addResourceBundle("zh-CN", "ui", zhUi);
          export { testI18n };
        `, loader: "tsx",
      }));
      b.onLoad({ filter: /workspacePreview\.ts$/ }, () => ({ contents: "export const {getWorkspaceState, listWorkspaceProjects, createWorkspaceProject, openWorkspaceProject} = globalThis.workspaceMock", loader: "js" }));
      b.onLoad({ filter: /TextShimmer\.tsx$/ }, () => ({ contents: "export const TextShimmer = ({children}) => children", loader: "js" }));
      b.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
    }}],
  });
  const module = { exports: {} };
  Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
  const React = require("react");
  const { act } = React;
  const root = require("react-dom/client").createRoot(document.getElementById("root"));
  try {
    await act(async () => root.render(React.createElement(module.exports.WorkspaceCreate, { active: true, onBack() {} })));
    assert.deepEqual(calls, []);
    assert.equal(document.querySelector("form"), null);
    assert.equal(document.querySelector('[role="tab"][aria-selected="true"]').textContent, "代码项目");
    await act(async () => document.querySelector('button[aria-label="新建代码项目"]').click());
    assert.ok(document.querySelector('dialog[open]'));
    assert.equal(document.querySelector('button[type="submit"]').disabled, true);
    const input = document.querySelector("#workspace-project-name");
    await act(async () => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input, "my-agent");
      input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    assert.equal(document.querySelector('button[type="submit"]').disabled, false);
    assert.equal(input.checkValidity(), true);
    await act(async () => {
      document.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
      document.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    });
    assert.deepEqual(calls, ["my-agent"]);
    assert.equal(input.disabled, true);
    await act(async () => finish({ name: "my-agent", sessionId: "one", url: "https://example.com/code-server/", expireAt: "2099-01-01T00:00:00Z", region: "cn-beijing", status: "ready" }));
    let frame = document.querySelector("iframe");
    assert.ok(frame);
    await act(async () => document.querySelector('button[aria-label="全屏"]').click());
    assert.ok(document.querySelector('.workspace-create.is-fullscreen'));
    assert.equal(document.querySelector("iframe"), frame);
    await act(async () => document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(document.querySelector('.workspace-create.is-fullscreen'), null);
    assert.equal(document.querySelector("iframe"), frame);
    assert.ok(document.querySelector('[role="timer"]').textContent.includes("本开发环境将在"));
    const reload = new dom.window.Event("beforeunload", { cancelable: true });
    window.dispatchEvent(reload);
    assert.equal(reload.defaultPrevented, false, "The outer page must not cancel reload after VS Code starts shutting down");
    workspaceState = {status: "sleeping", sessionId: "", expireAt: ""};
    await act(async () => document.dispatchEvent(new dom.window.Event("visibilitychange")));
    assert.match(document.querySelector('[role="status"]').textContent, /正在恢复工作区/);
    assert.equal(document.querySelector("iframe"), frame);
    workspaceState = {status: "ready", sessionId: "resumed", expireAt: "2099-01-01T00:00:00Z"};
    await act(async () => finishRecovery({ ...workspaceState, name: "my-agent", url: "https://example.com/restored/", region: "cn-beijing" }));
    assert.notEqual(document.querySelector("iframe"), frame);
    frame = document.querySelector("iframe");
    assert.match(frame.src, /restored/);
    assert.equal(document.querySelector('.workspace-create__recovery'), null);
    await act(async () => document.querySelector('button[aria-label="返回代码项目"]').click());
    assert.equal(document.querySelector("iframe"), frame);
    assert.equal(frame.parentElement.hidden, true);
    assert.ok(document.querySelector('button[aria-label="新建代码项目"]'));
    assert.equal(document.querySelector("form"), null);
    assert.equal(document.querySelector(".workspace-create__footer"), null);
    await act(async () => module.exports.testI18n.changeLanguage("en-US"));
    assert.equal(document.querySelector('[role="tab"][aria-selected="true"]').textContent, "Code projects");
    await act(async () => document.querySelector('button[aria-label="New code project"]').click());
    assert.equal(document.querySelector("dialog h2").textContent, "New code project");
    assert.equal(document.querySelector("#workspace-project-name").placeholder, "e.g. my-agent");
    assert.equal(document.querySelector('button[type="submit"]').textContent, "Create project");
    assert.doesNotMatch(document.querySelector("dialog").textContent, /[\p{Script=Han}]/u);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    delete globalThis.workspaceMock;
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name];
    }
  }
});
