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
const translations = Object.fromEntries(["zh-CN", "en-US"].map((locale) => [locale,
  JSON.parse(readFileSync(new URL(`../src/i18n/resources/${locale}/sidebar.json`, import.meta.url), "utf8")),
]));
const mocks = {
  "react-i18next": `const resources = ${JSON.stringify(translations)};
    export const useTranslation = () => ({ t: key => key.replace(/^sidebar:/, '').split('.').reduce((value, part) => value?.[part], resources[globalThis.sidebarLocale]) ?? key, i18n: {language: globalThis.sidebarLocale} });`,
  "../i18n": `export const changeLanguage = () => {}; export const DEFAULT_LOCALE = 'zh-CN'; export const resolveSupportedLocale = value => value; export const SUPPORTED_LOCALES = [];`,
  "../adk/identity": `export const displayName = value => value.name; export const profilePictureUrl = value => value.picture;`,
  "../blocks": `export const sessionTitle = () => '';`,
  "./Search": `export const SearchButton = () => null;`,
};
const compiled = await build({
  entryPoints: [fileURLToPath(new URL("../src/ui/Sidebar.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*", "lucide-react"],
  loader: { ".css": "empty", ".module.css": "empty", ".svg": "dataurl" },
  plugins: [{ name: "sidebar-adapters", setup(builder) {
    builder.onResolve({ filter: /.*/ }, ({ path }) => path in mocks ? { path, namespace: "mock" } : undefined);
    builder.onLoad({ filter: /.*/, namespace: "mock" }, ({ path }) => ({ contents: mocks[path] }));
  } }],
});
const module = { exports: {} };
Function("require", "module", "exports", compiled.outputFiles[0].text)(require, module, module.exports);
const { Sidebar } = module.exports;

async function mount({ role = "super_admin", manageUsers = role === "super_admin", usersHandler = true, locale = "zh-CN", activePage = "review-center", narrow = false } = {}) {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost" });
  dom.window.matchMedia = () => ({ matches: narrow, addEventListener() {}, removeEventListener() {} });
  const globals = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true, sidebarLocale: locale };
  const previous = Object.fromEntries(Object.keys(globals).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const calls = [];
  const root = require("react-dom/client").createRoot(document.getElementById("root"));
  const noop = () => {};
  await act(async () => root.render(React.createElement(Sidebar, {
    branding: { title: "Studio" }, cloudProvider: "volcengine", sessions: [], currentSessionId: "", activePage,
    access: { role, capabilities: { manageUsers } }, features: { history: false, search: false },
    ...Object.fromEntries(["onNewChat", "onSearch", "onQuickCreate", "onLibrary", "onAddAgent", "onMyAgents", "onWorkspace", "onApplications", "onCronJobs", "onAgentKitCli", "onDeveloperResources", "onSystemInfo", "onIssueFeedback", "onPickSession", "onDeleteSession", "onLogout"].map((key) => [key, noop])),
    onReviewCenter: () => calls.push("review-center"),
    onUserManagement: usersHandler ? () => calls.push("users") : undefined,
  })));
  return { calls, async close() {
    await act(async () => root.unmount());
    dom.window.close();
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  } };
}

for (const role of ["user", "developer"]) {
  test(`${role} has no administration links or empty group`, async () => {
    const mounted = await mount({ role });
    try {
      assert.equal(document.querySelector('.sidebar-nav--administration'), null);
      assert.equal(document.querySelector('[aria-label="审核中心"]'), null);
      assert.equal(document.querySelector('[aria-label="用户管理"]'), null);
      assert.equal(document.querySelectorAll('nav').length, 1);
    } finally { await mounted.close(); }
  });
}

test("administrator sees Review center in its own group without User management", async () => {
  const mounted = await mount({ role: "admin" });
  try {
    const group = document.querySelector('nav[aria-label="管控"]');
    assert.ok(group);
    assert.deepEqual([...group.querySelectorAll('button')].map((item) => item.textContent), ['审核中心']);
    assert.equal(document.querySelector('nav[aria-label="主导航"] [aria-label="审核中心"]'), null);
    await act(async () => group.querySelector('button').click());
    assert.deepEqual(mounted.calls, ['review-center']);
  } finally { await mounted.close(); }
});

test("super administrator can navigate both entries, with correct active state and collapsed labels", async () => {
  const mounted = await mount({ activePage: "users" });
  try {
    const group = document.querySelector('nav[aria-label="管控"]');
    const buttons = [...group.querySelectorAll('button')];
    assert.deepEqual(buttons.map((item) => item.textContent), ['审核中心', '用户管理']);
    assert.equal(buttons[0].getAttribute('aria-current'), null);
    assert.equal(buttons[1].getAttribute('aria-current'), 'page');
    await act(async () => { buttons[0].click(); buttons[1].click(); });
    assert.deepEqual(mounted.calls, ['review-center', 'users']);
    await act(async () => document.querySelector('[aria-label="收起侧边栏"]').click());
    assert.ok(document.querySelector('.sidebar.is-collapsed'));
    assert.equal(buttons[0].getAttribute('title'), '审核中心');
    assert.equal(buttons[1].getAttribute('aria-label'), '用户管理');
    await act(async () => document.querySelector('[aria-label="展开侧边栏"]').click());
    assert.equal(document.querySelector('.sidebar.is-collapsed'), null);
  } finally { await mounted.close(); }
});

test("User management remains hidden without its capability or navigation handler", async () => {
  for (const options of [{ manageUsers: false }, { usersHandler: false }]) {
    const mounted = await mount(options);
    try { assert.equal(document.querySelector('[aria-label="用户管理"]'), null); }
    finally { await mounted.close(); }
  }
});

test("English navigation uses Administration and remains accessible when automatically collapsed", async () => {
  const mounted = await mount({ locale: "en-US", narrow: true });
  try {
    const group = document.querySelector('nav[aria-label="Administration"]');
    assert.ok(group);
    assert.equal(group.querySelector('.sidebar-nav-group-title').textContent, 'Administration');
    assert.ok(document.querySelector('.sidebar.is-collapsed'));
    assert.deepEqual([...group.querySelectorAll('button')].map((item) => item.getAttribute('aria-label')), ['Review center', 'User management']);
  } finally { await mounted.close(); }
});
