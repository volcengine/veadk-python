import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);

async function bundle(entry) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    bundle: true, format: "cjs", platform: "node", write: false, outdir: "out", jsx: "automatic",
    external: ["react", "react-dom", "react-dom/*"], loader: { ".css": "empty" },
    plugins: [{ name: "source-name-boundaries", setup(b) {
      b.onLoad({ filter: /adk\/client\.ts$/ }, () => ({
        contents: "export const studioFetch = (...args) => globalThis.nameApiFetch(...args);", loader: "js",
      }));
      b.onLoad({ filter: /CodeBrowserDialog\.tsx$/ }, () => ({
        contents: "export function CodeBrowserDialog(props) { globalThis.nameBrowserProps = props; return null; }", loader: "js",
      }));
      b.onLoad({ filter: /IntelligentProjectLibrary\.tsx$/ }, args => ({
        contents: readFileSync(args.path, "utf8") + `
          import { i18n as testI18n } from "../i18n/runtime";
          import enCreate from "../i18n/resources/en-US/create.json";
          import zhCreate from "../i18n/resources/zh-CN/create.json";
          import enSandbox from "../i18n/resources/en-US/sandbox.json";
          import zhSandbox from "../i18n/resources/zh-CN/sandbox.json";
          testI18n.addResourceBundle("en-US", "create", enCreate);
          testI18n.addResourceBundle("zh-CN", "create", zhCreate);
          testI18n.addResourceBundle("en-US", "sandbox", enSandbox);
          testI18n.addResourceBundle("zh-CN", "sandbox", zhSandbox);
          export { testI18n };
        `, loader: "tsx",
      }));
    }}],
  });
  const module = { exports: {} };
  Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
  return module.exports;
}

function fixtures() {
  const project = { schemaVersion: "1", origin: "migration", projectId: "a".repeat(32),
    name: "迁移项目", createdAt: "2026-09-10T00:00:00Z", updatedAt: "2026-09-10T01:00:00Z",
    latestVersionId: "c".repeat(32), latestVersionCreatedAt: "2026-09-10T01:00:00Z",
    latestVersionVerified: true, latestAgentName: "original-agent", versionCount: 2 };
  const first = { schemaVersion: "1", producer: "migration", projectId: project.projectId,
    versionId: "b".repeat(32), parentVersionId: null, sourceSessionId: "migration-one",
    createdAt: project.createdAt, name: "基线版", intentSummary: "迁移完成", acceptanceCriteria: [],
    artifactSha256: "d".repeat(64), validationReportSha256: "e".repeat(64), artifactSize: 25,
    fileCount: 1, agentName: "original-agent", entryPoint: "app.py", verified: true,
    validationSummary: "已验证", gateSummary: [], validatedAt: project.createdAt,
    migrationFramework: "any" };
  const latest = { ...first, producer: "intelligent-development", versionId: project.latestVersionId,
    parentVersionId: first.versionId, createdAt: project.updatedAt, name: null };
  return { project, versions: [latest, first] };
}

test("source names share normalized Unicode boundaries and reject unsafe text", async () => {
  const { normalizeSourceName, sourceNameError } = await bundle("../src/adk/sourceProjectName.ts");
  for (const value of ["", "   "]) assert.equal(sourceNameError(value), "required");
  for (const value of ["名".repeat(129), "😀".repeat(129)]) assert.equal(sourceNameError(value), "tooLong");
  for (const value of ["\nname", "name\t", "name\0", "name\u007f", "name\u0085", "name\u202e",
    "name\u2066", "name\u200b", "name\u2028", "name\u2029", "<img onerror=alert(1)>", "x>", "\ud800"]) {
    assert.equal(sourceNameError(value), "invalidCharacters", JSON.stringify(value));
  }
  for (const value of ["名".repeat(128), "😀".repeat(128), "e\u0301".repeat(128), "../a; $value & 'b'"]) {
    assert.equal(sourceNameError(value), null);
  }
  assert.equal(normalizeSourceName("  Cafe\u0301  "), "Café");
});

test("rename clients only send display names and reject mismatched responses", async () => {
  const client = await bundle("../src/adk/intelligentDevelopment.ts");
  const { project, versions } = fixtures();
  const requests = [];
  const controller = new AbortController();
  globalThis.nameApiFetch = async (url, options) => {
    requests.push({ url, options });
    const { name } = JSON.parse(options.body);
    return Response.json(url.includes("/versions/")
      ? { version: { ...versions[0], name } } : { project: { ...project, name } });
  };
  try {
    const renamed = await client.renameIntelligentDevelopmentProject(project.projectId, "  Cafe\u0301  ", controller.signal);
    assert.equal(renamed.name, "Café");
    await client.renameIntelligentDevelopmentVersion(project.projectId, versions[0].versionId, "Release", controller.signal);
    assert.equal(requests[0].options.method, "PATCH");
    assert.equal(requests[0].options.signal, controller.signal);
    assert.deepEqual(JSON.parse(requests[0].options.body), { name: "Café" });
    await assert.rejects(client.renameIntelligentDevelopmentProject(project.projectId, "<script>"));
    assert.equal(requests.length, 2);
    globalThis.nameApiFetch = async () => Response.json({ project: { ...project, projectId: "wrong", name: "Release" } });
    await assert.rejects(client.renameIntelligentDevelopmentProject(project.projectId, "Release"));
    globalThis.nameApiFetch = async () => Response.json({ version: { ...versions[0], versionId: "wrong", name: "Release" } });
    await assert.rejects(client.renameIntelligentDevelopmentVersion(project.projectId, versions[0].versionId, "Release"));
    globalThis.nameApiFetch = async () => Response.json({ detail: { message: "Storage unavailable" } }, { status: 503 });
    await assert.rejects(client.renameIntelligentDevelopmentProject(project.projectId, "Release"), /Storage unavailable/);
  } finally { delete globalThis.nameApiFetch; }
});

test("migrated names use existing icon controls, preserve input on failure and update all labels", async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost", pretendToBeVisual: true });
  dom.window.localStorage.setItem("agentkit.studio.locale", "zh-CN");
  const previous = new Map();
  const globals = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement, HTMLInputElement: dom.window.HTMLInputElement,
    Node: dom.window.Node, Element: dom.window.Element, DocumentFragment: dom.window.DocumentFragment,
    ShadowRoot: dom.window.ShadowRoot, MutationObserver: dom.window.MutationObserver,
    Event: dom.window.Event, CustomEvent: dom.window.CustomEvent, MouseEvent: dom.window.MouseEvent,
    getComputedStyle: dom.window.getComputedStyle, IS_REACT_ACT_ENVIRONMENT: true };
  for (const [key, value] of Object.entries(globals)) {
    previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  }
  const data = fixtures();
  const patches = [];
  let finish;
  let staleRead;
  let delayRead = false;
  globalThis.nameApiFetch = async (url, options = {}) => {
    if (options.method === "PATCH") {
      patches.push({ url, name: JSON.parse(options.body).name });
      return new Promise(resolve => { finish = resolve; });
    }
    if (url.includes("/source")) {
      const version = data.versions.find(item => url.includes(item.versionId));
      return Response.json({ ...version, sessionId: version.sourceSessionId, deployable: true,
        files: [{ path: "app.py", content: "agent = object()" }] });
    }
    if (url.endsWith("/versions")) return Response.json({ versions: data.versions });
    if (delayRead) {
      delayRead = false;
      const old = { ...data.project };
      return new Promise(resolve => { staleRead = () => resolve(Response.json({ projects: [old] })); });
    }
    return Response.json({ projects: [data.project] });
  };
  const React = require("react");
  const { act } = React;
  const root = require("react-dom/client").createRoot(document.getElementById("root"));
  const selections = [];
  const props = { origin: "migration", capabilities: { projectStorageEnabled: true },
    capabilitiesLoading: false, creating: false, onSelectBaseVersion: value => selections.push(value),
    onClearBaseVersion() {}, onDownload: async () => {}, onDeploy() {} };
  const click = async element => act(async () => { element.focus(); element.click(); });
  const input = () => document.querySelector('[role="dialog"] input');
  const save = () => document.querySelector('[aria-label="保存名称"]');
  const type = async value => act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(input(), value);
    input().dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
  const submit = () => document.querySelector("form").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  try {
    const app = await bundle("../src/create/IntelligentProjectLibrary.tsx");
    await act(async () => root.render(React.createElement(app.IntelligentProjectLibrary, props)));
    const projectEdit = document.querySelector('[aria-label="修改项目名称"]');
    assert.equal(projectEdit.textContent, "");
    assert.ok(projectEdit.querySelector("svg"));
    await click(document.querySelector(".ic-project-disclosure"));
    assert.equal(document.querySelectorAll('[aria-label="修改版本名称"]').length, 2);
    assert.match(document.querySelector(".ic-version-name").textContent, /^版本 · /);
    assert.equal(document.querySelector(".ic-version-status").textContent, "最新版本");
    delayRead = true;
    await click(document.querySelector('[aria-label="刷新项目列表"]'));
    await click(projectEdit);
    assert.equal(document.activeElement, input());
    assert.equal(input().selectionEnd, data.project.name.length);
    assert.equal(save().disabled, true);
    await type("<img src=x onerror=alert(1)>");
    assert.equal(save().disabled, true);
    assert.ok(document.querySelector('[role="alert"]'));
    assert.equal(document.querySelector('[role="dialog"] img'), null);
    await type("名".repeat(129));
    assert.equal(save().disabled, true);
    await type("新项目 & 发布");
    assert.equal(save().disabled, false);
    await act(async () => {
      input().dispatchEvent(new dom.window.CompositionEvent("compositionstart", { bubbles: true }));
      submit();
      const enter = new dom.window.KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true, cancelable: true });
      input().dispatchEvent(enter);
      assert.equal(enter.defaultPrevented, true);
      input().dispatchEvent(new dom.window.CompositionEvent("compositionend", { bubbles: true }));
      const safari = new dom.window.KeyboardEvent("keydown", { key: "Enter", keyCode: 229, bubbles: true, cancelable: true });
      input().dispatchEvent(safari);
      assert.equal(safari.defaultPrevented, true);
    });
    assert.equal(patches.length, 0);
    await act(async () => { submit(); submit(); });
    assert.equal(patches.length, 1);
    assert.equal(input().disabled, true);
    assert.equal(document.querySelector(".sandbox-control-close").disabled, true);
    await act(async () => finish(Response.json({ detail: { message: "Storage temporarily unavailable" } }, { status: 503 })));
    assert.equal(input().value, "新项目 & 发布");
    assert.match(document.querySelector('[role="alert"]').textContent, /Storage temporarily unavailable/);
    await click(save());
    data.project.name = "新项目 & 发布";
    await act(async () => finish(Response.json({ project: data.project })));
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(document.activeElement, projectEdit);
    await act(async () => staleRead());
    assert.equal(document.querySelector(".ic-project-copy strong").textContent, data.project.name);
    assert.equal(document.querySelector(".ic-project-disclosure").getAttribute("aria-expanded"), "true");
    await click(document.querySelector('[aria-label="修改版本名称"]'));
    await type("生产可用版");
    await click(save());
    data.versions[0].name = "生产可用版";
    await act(async () => finish(Response.json({ version: data.versions[0] })));
    assert.equal(document.querySelector(".ic-version-name").textContent, "生产可用版");
    const button = label => [...document.querySelectorAll("button")].find(item => item.textContent === label);
    await click(button("去优化"));
    assert.deepEqual(selections[0], { projectId: data.project.projectId, versionId: data.versions[0].versionId,
      projectName: data.project.name, versionLabel: "生产可用版" });
    await click(button("对比版本"));
    await click(button("查看对比"));
    assert.equal(globalThis.nameBrowserProps.comparison.baseLabel, "基线版");
    assert.equal(globalThis.nameBrowserProps.comparison.targetLabel, "生产可用版");
    await click(projectEdit);
    await type("未保存名称");
    await act(async () => input().dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(patches.length, 3);
    await act(async () => app.testI18n.changeLanguage("en-US"));
    await click(document.querySelector('[aria-label="Edit project name"]'));
    assert.equal(document.querySelector('[role="dialog"] h2').textContent, "Edit project name");
    assert.ok(document.querySelector('[aria-label="Save name"] svg'));
    await act(async () => root.render(React.createElement(app.IntelligentProjectLibrary,
      { ...props, origin: "intelligent-development" })));
    assert.equal(document.querySelector('.ic-name-edit'), null);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    delete globalThis.nameApiFetch;
    delete globalThis.nameBrowserProps;
    for (const [key, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  }
});
