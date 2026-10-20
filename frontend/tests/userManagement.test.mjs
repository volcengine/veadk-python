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
const resources = JSON.parse(readFileSync(new URL("../src/i18n/resources/zh-CN/users.json", import.meta.url), "utf8"));
const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/users/UserManagement.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*"],
  plugins: [{ name: "user-test-adapters", setup(builder) {
    builder.onResolve({ filter: /^react-i18next$/ }, () => ({ path: "translations", namespace: "mock-i18n" }));
    builder.onLoad({ filter: /.*/, namespace: "mock-i18n" }, () => ({ contents: `
      const resources = ${JSON.stringify(resources)};
      export function useTranslation() { return { i18n: {resolvedLanguage: 'zh-CN'}, t(key, options = {}) {
        const value = key.split('.').reduce((obj, part) => obj?.[part], resources) || options.defaultValue || key;
        return value.replace(/{{(\\w+)}}/g, (_, name) => options[name] ?? '');
      } }; }
    ` }));
    builder.onResolve({ filter: /\/adk\/users$/ }, () => ({ path: "users", namespace: "mock-users" }));
    builder.onLoad({ filter: /.*/, namespace: "mock-users" }, () => ({ contents: `
      export const STUDIO_ROLES = ['super_admin', 'admin', 'developer', 'user'];
      export class UserManagementError extends Error { constructor(code, status) { super(code); this.code = code; this.status = status; } }
      export const listStudioUsers = (...args) => globalThis.usersApi.list(...args);
      export const updateStudioUserRole = (...args) => globalThis.usersApi.update(...args);
    ` }));
    builder.onResolve({ filter: /\/text-shimmer\/TextShimmer$/ }, () => ({ path: "shimmer", namespace: "mock-shimmer" }));
    builder.onLoad({ filter: /.*/, namespace: "mock-shimmer" }, () => ({ contents: `import { createElement } from 'react'; export const TextShimmer = ({children}) => createElement('span', null, children);` }));
    builder.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
  } }],
});
const module = { exports: {} };
Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
const { UserManagement } = module.exports;
const owner = { id: "owner", name: "Owner", email: "owner@example.com", role: "super_admin", status: "EXTERNAL_PROVIDER", lastLogin: "", protected: true, currentUser: true, roleConflict: false };
const member = { ...owner, id: "member", name: "Member", email: "member@example.com", role: "user", protected: false, currentUser: false };
const page = (items) => ({ items, total: items.length, poolTotal: 2, page: 1, pageSize: 20, userPoolId: "pool", clientId: "client", provider: "volcengine" });

async function mount(api) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost", pretendToBeVisual: true });
  const globals = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node, IS_REACT_ACT_ENVIRONMENT: true, usersApi: api };
  const previous = new Map(Object.keys(globals).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false; };
  const root = require("react-dom/client").createRoot(document.getElementById("root"));
  await act(async () => root.render(React.createElement(UserManagement, { onBack() {} })));
  return { dom, async close() {
    await act(async () => root.unmount()); dom.window.close();
    for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  } };
}

test("protected administrator stays read-only and role changes show persisted success", async () => {
  let current = member;
  const writes = [];
  const mounted = await mount({ list: async () => page([owner, current]), update: async (user, role) => { writes.push({ user, role }); current = { ...current, role }; return current; } });
  try {
    const buttons = () => [...document.querySelectorAll('button')];
    assert.equal(buttons().filter((button) => button.textContent === "更改角色").length, 1);
    assert.match(document.body.textContent, /初始超级管理员/);
    await act(async () => buttons().find((button) => button.textContent === "更改角色").click());
    assert.ok(document.querySelector("dialog[open]"));
    await act(async () => document.querySelector('dialog button[aria-label="角色"]').click());
    await act(async () => [...document.querySelectorAll('dialog [role="option"]')].find((option) => option.textContent.includes("开发者")).click());
    await act(async () => buttons().find((button) => button.textContent === "保存角色").click());
    assert.equal(writes[0].role, "developer");
    assert.equal(writes[0].user.role, "user");
    assert.equal(document.querySelector("dialog"), null);
    assert.match(document.body.textContent, /已将 Member 设置为开发者/);
  } finally { await mounted.close(); }
});

test("load errors remain distinct from empty results and can be retried", async () => {
  let attempts = 0;
  const mounted = await mount({ list: async () => { if (++attempts === 1) throw new Error("network"); return page([]); } });
  try {
    assert.ok(document.querySelector('[role="alert"]'));
    assert.doesNotMatch(document.body.textContent, /没有匹配的用户/);
    await act(async () => [...document.querySelectorAll("button")].find((button) => button.textContent === "重试").click());
    assert.equal(document.querySelector('[role="alert"]'), null);
    assert.match(document.body.textContent, /没有匹配的用户/);
  } finally { await mounted.close(); }
});

test("conflicting memberships can be repaired to ordinary user access", async () => {
  let current = { ...member, roleConflict: true };
  const writes = [];
  const mounted = await mount({ list: async () => page([current]), update: async (user, role) => { writes.push({ user, role }); current = { ...current, role, roleConflict: false }; return current; } });
  try {
    const buttons = () => [...document.querySelectorAll("button")];
    await act(async () => buttons().find((button) => button.textContent === "更改角色").click());
    const save = buttons().find((button) => button.textContent === "保存角色");
    assert.equal(save.disabled, false);
    await act(async () => save.click());
    assert.equal(writes[0].role, "user");
    assert.equal(document.querySelector("dialog"), null);
  } finally { await mounted.close(); }
});
