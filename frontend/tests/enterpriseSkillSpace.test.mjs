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
const translations = JSON.parse(readFileSync(new URL("../src/i18n/resources/zh-CN/ui.json", import.meta.url), "utf8"));
const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/ui/skills/EnterpriseSkillSpace.tsx", import.meta.url))],
  bundle: true, format: "cjs", platform: "node", write: false,
  external: ["react", "react-dom", "react-dom/*"],
  plugins: [{ name: "shared-space-test", setup(builder) {
    const mocks = {
      "react-i18next": `const resources = ${JSON.stringify(translations)};
        const t = (key, options = {}) => {
          const value = key.split('.').reduce((obj, part) => obj?.[part], resources);
          const label = typeof value === 'string' ? value : key === 'skillCenter.skillCountValue' ? '{{count}} 技能' : key;
          return label.replace(/{{(\\w+)}}/g, (_, name) => options[name] ?? '');
        };
        export const useTranslation = () => ({t});`,
      "../../adk/skills": `export const ensureSharedSkillSpace = (...args) => globalThis.sharedSpaceApi(...args);`,
      "./SkillErrorDetails": `import {createElement as h} from 'react';
        export const normalizeSkillError = error => error;
        export const SkillErrorDetails = ({error}) => h('span', null, error.message);`,
      "../LibraryResourceCard": `import {createElement as h} from 'react';
        export const LibraryResourceCard = ({title, description, status, metadata, detailAction, action}) => h('article', null,
          h('h2', null, title), status, h('p', null, description),
          ...metadata.map((item, index) => h('span', {key:index}, item.value)),
          h('button', {disabled:detailAction.disabled, onClick:detailAction.onClick}, detailAction.label),
          action ? h('button', {onClick:action.onClick}, action.label) : null);`,
    };
    builder.onResolve({ filter: /.*/ }, ({path}) => path in mocks ? {path, namespace:"test-mock"} : undefined);
    builder.onLoad({filter: /.*/, namespace:"test-mock"}, ({path}) => ({contents:mocks[path]}));
  }}],
});
const module = {exports:{}};
Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
const {EnterpriseSkillSpace} = module.exports;

async function mount(api, props = {}) {
  const dom = new JSDOM('<div id="root"></div>', {url:"http://localhost"});
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  Object.defineProperty(globalThis, "navigator", {value:dom.window.navigator, configurable:true});
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.sharedSpaceApi = api;
  const {createRoot} = require("react-dom/client");
  const root = createRoot(document.getElementById("root"));
  const opened = [];
  const render = async (next = {}) => act(async () => root.render(React.createElement(EnterpriseSkillSpace, {
    key:next.region || "cn-beijing", region:"cn-beijing", active:true, revision:0,
    onOpen:space => opened.push(space), ...props, ...next,
  })));
  await render();
  return {opened, render, close:async () => { await act(async () => root.unmount()); dom.window.close(); }};
}

test("an empty shared space remains visible and opens its real resource", async () => {
  const space = {id:"shared", name:"studio_enterprise_shared", region:"cn-beijing", isShared:true, canWrite:false, skillCount:0};
  const ui = await mount(async () => space);
  try {
    assert.match(document.body.textContent, /企业共享空间/);
    assert.match(document.body.textContent, /全员可见/);
    assert.match(document.body.textContent, /0 技能/);
    await act(async () => document.querySelector("button").click());
    assert.equal(ui.opened[0], space);
    assert.doesNotMatch(document.body.textContent, /新建|删除|上传/);
  } finally { await ui.close(); }
});

test("failure keeps the entry, announces the error and supports retry", async () => {
  let calls = 0;
  const ui = await mount(async () => {
    if (++calls === 1) throw new Error("temporarily unavailable");
    return {id:"shared", isShared:true, skillCount:0};
  });
  try {
    assert.equal(document.querySelector("button").disabled, true);
    assert.match(document.querySelector('[role="alert"]').textContent, /temporarily unavailable/);
    await act(async () => [...document.querySelectorAll("button")].at(-1).click());
    assert.equal(calls, 2);
    assert.equal(document.querySelector('[role="alert"]'), null);
    assert.equal(document.querySelector("button").disabled, false);
  } finally { await ui.close(); }
});

test("switching regions ignores stale responses and aborts the old request", async () => {
  let finishOld;
  let oldSignal;
  const ui = await mount(({region, signal}) => {
    if (region === "cn-beijing") { oldSignal = signal; return new Promise(resolve => {finishOld = resolve;}); }
    return Promise.resolve({id:"singapore", region, isShared:true});
  });
  try {
    assert.equal(document.querySelector("button").disabled, true);
    await ui.render({region:"ap-southeast-1"});
    assert.equal(oldSignal.aborted, true);
    await act(async () => finishOld({id:"beijing", isShared:true}));
    await act(async () => document.querySelector("button").click());
    assert.equal(ui.opened[0].id, "singapore");
  } finally { await ui.close(); }
});
