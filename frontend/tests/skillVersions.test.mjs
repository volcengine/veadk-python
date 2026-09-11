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
const mocks = {
  "react-i18next": `const resources = ${JSON.stringify(translations)};
    const t = (key, options = {}) => { const value = key.split('.').reduce((obj, part) => obj?.[part], resources); return (typeof value === 'string' ? value : key).replace(/{{(\\w+)}}/g, (_, name) => options[name] ?? ''); };
    export const useTranslation = () => ({ t, i18n: { language: 'zh-CN' } });`,
  "../../adk/skillVersions": `export const listSkillVersions = (...args) => globalThis.versionApi.list(...args); export const uploadSkillVersion = (...args) => globalThis.versionApi.upload(...args);`,
  "../../adk/skills": `export const getManagedSkillFiles = (...args) => globalThis.versionApi.files(...args);`,
  "./SkillErrorDetails": `import { createElement as h } from 'react'; export const normalizeSkillError = error => error; export const SkillErrorDetails = ({ error }) => h('span', null, error.message);`,
  "./SkillFileTree": `import { createElement as h } from 'react'; export const SkillFileTree = ({ files }) => h('pre', null, files.map(file => file.content).join('\\n'));`,
  "../../reviews/ReviewOutcome": `import { createElement as h } from 'react'; export const ReviewStatusLabel = ({ status }) => h('span', null, status); export const ReviewOutcome = ({ application }) => h('div', { 'data-review': application.id }, [application.status, application.reviewer?.name, application.comment, application.reason].filter(Boolean).join(' ')); export const ReviewHistoryList = ({ applications }) => h('div', null, applications.map(application => h(ReviewOutcome, { key: application.id, application })));`,
};
const result = await build({
  entryPoints: [fileURLToPath(new URL('../src/ui/skills/SkillVersionsDialog.tsx', import.meta.url))],
  bundle: true, format: 'cjs', platform: 'node', write: false, external: ['react', 'react-dom', 'react-dom/*'],
  plugins: [{ name: 'version-test', setup(builder) {
    builder.onResolve({ filter: /.*/ }, ({ path }) => path in mocks ? { path, namespace: 'mock' } : path.endsWith('.css') ? { path, namespace: 'empty' } : undefined);
    builder.onLoad({ filter: /.*/, namespace: 'mock' }, ({ path }) => ({ contents: mocks[path] }));
    builder.onLoad({ filter: /.*/, namespace: 'empty' }, () => ({ contents: '' }));
  } }],
});
const module = { exports: {} };
Function('require', 'module', 'exports', result.outputFiles[0].text)(require, module, module.exports);
const { SkillVersionsDialog } = module.exports;
const versions = [
  { skillId: 'skill', name: 'daily-summary', version: 'v2', description: '第二版', status: 'running', createdAt: '2026-09-11T10:00:00Z', isCurrent: true },
  { skillId: 'skill', name: 'daily-summary', version: 'v1', description: '第一版', status: 'running', createdAt: '2026-09-11T09:00:00Z', isCurrent: false },
];
const defaults = { list: async () => ({ items: versions, canUpdate: true, totalCount: 2 }), files: async ({ version }) => [{ path: 'SKILL.md', kind: 'text', content: `文件 ${version}` }] };
async function mount(api = {}, props = {}) {
  const dom = new JSDOM('<button id="launch">版本管理</button><div id="root"></div>', { url: 'http://localhost' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true, versionApi: { ...defaults, ...api } });
  Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
  document.getElementById('launch').focus();
  const { createRoot } = require('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  const inputProps = {
    skill: { skillId: 'skill', skillName: 'daily-summary', version: 'v2' }, space: { id: 'space' }, region: 'cn-beijing',
    reviews: [], onClose: () => {}, onChanged: () => {}, onSubmitReview: async () => {}, ...props,
  };
  await act(async () => root.render(React.createElement(SkillVersionsDialog, inputProps)));
  return { render: async next => act(async () => root.render(React.createElement(SkillVersionsDialog, { ...inputProps, ...next }))), close: async () => { await act(async () => root.unmount()); dom.window.close(); } };
}
const button = name => [...document.querySelectorAll('button')].find(item => item.textContent === name);
const versionButton = version => [...document.querySelectorAll('.skill-versions__version')].find(item => item.querySelector('strong')?.textContent === version);

test('history selection loads exact archived version and submits that version', async () => {
  let submitted;
  const app = await mount({}, { onSubmitReview: async version => { submitted = version; } });
  try {
    assert.match(document.body.textContent, /文件 v2/);
    await act(async () => versionButton('v1').click());
    assert.match(document.body.textContent, /文件 v1/);
    assert.doesNotMatch(document.body.textContent, /文件 v2/);
    await act(async () => button('申请公开').click());
    assert.equal(submitted, 'v1');
  } finally { await app.close(); }
});

test('approval state and reviewer survive reload, and pending/approved versions cannot resubmit', async () => {
  const reviews = [{ id: 'approved', sourceSkillId: 'skill', version: 'v1', status: 'approved', submittedAt: '2026-09-11T09:00:00Z', reviewer: { name: '审核员甲' }, comment: '可以使用' }, { id: 'pending', sourceSkillId: 'skill', version: 'v2', status: 'pending', submittedAt: '2026-09-11T10:00:00Z' }];
  const app = await mount({}, { reviews });
  try {
    assert.equal(button('申请公开').disabled, true);
    await act(async () => versionButton('v1').click());
    assert.equal(button('申请公开').disabled, true);
    assert.match(document.body.textContent, /审核员甲.*可以使用/);
  } finally { await app.close(); }
});

test('returned version can submit again and keeps earlier review details', async () => {
  const reviews = [{ id: 'earlier', sourceSkillId: 'skill', version: 'v2', status: 'returned', submittedAt: '2026-09-11T09:00:00Z', reason: '补充示例' }, { id: 'latest', sourceSkillId: 'skill', version: 'v2', status: 'returned', submittedAt: '2026-09-11T10:00:00Z', reason: '补充引用' }];
  const app = await mount({}, { reviews });
  try {
    assert.equal(button('申请公开').disabled, false);
    assert.match(document.querySelector('[data-review="latest"]').textContent, /补充引用/);
    assert.match(document.querySelector('details').textContent, /补充示例/);
  } finally { await app.close(); }
});

test('upload uses the same skill, refreshes, and selects the returned native version', async () => {
  let uploaded, changed = 0;
  let items = versions;
  const app = await mount({ list: async () => ({ items, canUpdate: true }), upload: async args => {
    uploaded = args;
    items = [{ ...versions[0], version: 'v3' }, ...versions];
    return { skillId: 'skill', name: 'daily-summary', version: 'v3' };
  } }, { onChanged: () => { changed++; } });
  try {
    const file = new window.File(['zip'], 'daily-summary.zip', { type: 'application/zip' });
    const input = document.querySelector('input[type="file"]');
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    await act(async () => input.dispatchEvent(new window.Event('change', { bubbles: true })));
    assert.equal(uploaded.skillId, 'skill'); assert.equal(uploaded.spaceId, 'space'); assert.equal(uploaded.file, file);
    assert.equal(input.value, ''); assert.equal(changed, 1);
    assert.equal(versionButton('v3').getAttribute('aria-pressed'), 'true');
    assert.match(document.body.textContent, /文件 v3/);
  } finally { await app.close(); }
});

test('loading, errors and retry are separate from the empty state', async () => {
  let resolveFirst;
  let calls = 0;
  const first = new Promise(resolve => { resolveFirst = resolve; });
  const app = await mount({ list: async () => { if (++calls === 1) return first; return { items: versions, canUpdate: true }; } });
  try {
    assert.match(document.querySelector('[role="status"]').textContent, /加载/);
    assert.doesNotMatch(document.body.textContent, /暂无版本/);
    await act(async () => resolveFirst(Promise.reject(new Error('版本读取失败'))));
    assert.match(document.querySelector('[role="alert"]').textContent, /版本读取失败/);
    await act(async () => button('重试').click());
    assert.equal(document.querySelectorAll('.skill-versions__version').length, 2);
  } finally { await app.close(); }
});

test('late file responses cannot replace the selected version', async () => {
  let finishOld;
  const app = await mount({ files: async ({ version }) => version === 'v2' ? new Promise(resolve => { finishOld = resolve; }) : [{ path: 'SKILL.md', content: '正确的 v1' }] });
  try {
    await act(async () => versionButton('v1').click());
    await act(async () => finishOld([{ path: 'SKILL.md', content: '过时的 v2' }]));
    assert.match(document.body.textContent, /正确的 v1/);
    assert.doesNotMatch(document.body.textContent, /过时的 v2/);
  } finally { await app.close(); }
});

test('shared skill history has no upload or submit action, and Escape closes dialog', async () => {
  let closed = 0;
  const app = await mount({ list: async () => ({ items: versions, canUpdate: false }) }, { onClose: () => { closed++; } });
  try {
    assert.equal(button('上传新版本'), undefined);
    assert.equal(button('申请公开'), undefined);
    assert.equal(document.activeElement, button('关闭'));
    await act(async () => document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    assert.equal(closed, 1);
  } finally { await app.close(); }
});

test('shared copies display the source version and author while reading the native archive version', async () => {
  const requestedVersions = [];
  const sharedVersion = { ...versions[0], skillId: 'shared-copy', version: 'v1', sourceVersion: 'v2', author: '测试作者' };
  const app = await mount({
    list: async () => ({ items: [sharedVersion], canUpdate: false }),
    files: async ({version}) => { requestedVersions.push(version); return [{path:'SKILL.md', content:'共享的第二版内容'}]; },
  }, {
    skill: {skillId:'shared-copy',skillName:'daily-summary',version:'v1',sourceVersion:'v2',author:'测试作者'},
    space: {id:'shared-space',isShared:true},
  });
  try {
    assert.equal(versionButton('v2').getAttribute('aria-pressed'),'true');
    assert.equal(versionButton('v1'),undefined);
    assert.equal(document.querySelector('.skill-versions__summary h3').textContent,'v2');
    assert.match(document.querySelector('.skill-versions__summary').textContent,/作者：测试作者/);
    assert.match(document.querySelector('.skill-versions__version').textContent,/已公开/);
    assert.doesNotMatch(document.body.textContent,/未申请公开/);
    await act(async()=>versionButton('v2').click());
    assert.deepEqual(requestedVersions,['v1']);
    assert.match(document.body.textContent,/共享的第二版内容/);
    assert.equal(button('申请公开'),undefined);
  } finally { await app.close(); }
});
