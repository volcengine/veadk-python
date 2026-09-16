import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import test from "node:test";
import { JSDOM } from "jsdom";
const require = createRequire(import.meta.url);

test("process disclosure keeps its state through streaming, completion and replay", async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost" });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage, IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.setItem("agentkit.studio.locale", "zh-CN");
  const result = await build({ entryPoints: [fileURLToPath(new URL("../src/create/DevelopmentProcess.tsx", import.meta.url))], bundle: true, platform: "node", format: "cjs", write: false, jsx: "automatic", external: ["react", "react-dom", "react-dom/*"], plugins: [{ name: "css", setup(b) { b.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" })); } }] });
  const module = { exports: {} };
  Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
  const React = require("react"), { act } = React;
  const root = require("react-dom/client").createRoot(document.getElementById("root"));
  const thinking = { id: "t:r", kind: "thinking", text: "", done: false };
  const tool = { id: "t:c", kind: "tool", itemType: "commandExecution", name: "运行命令", args: { command: "cat agent.py", commandActions: [{ type: "read", name: "agent.py" }] }, done: false };
  const render = (blocks, active, status = "") => act(async () => root.render(React.createElement(module.exports.DevelopmentProcess, { blocks, active, status, render: items => React.createElement("pre", null, JSON.stringify(items)) })));
  try {
    await render([thinking], true);
    let toggle = document.querySelector("button");
    assert.equal(toggle.getAttribute("aria-expanded"), "false");
    assert.match(toggle.textContent, /正在思考/);
    await act(async () => toggle.click());
    await render([{ ...thinking, done: true }, tool], true);
    assert.equal(document.querySelector("button"), toggle, "stable item ID retains the disclosure node");
    assert.equal(toggle.getAttribute("aria-expanded"), "true");
    assert.match(toggle.textContent, /读取文件.*Read project files/);
    await render([{ ...thinking, done: true }, tool], true, "正在恢复连接");
    assert.match(toggle.textContent, /正在恢复连接/);
    await render([{ ...thinking, done: true }, { ...tool, done: true, status: "failed", durationMs: 1400 }, { id: "t:answer", kind: "text", text: "已保留结果" }, { id: "t:r2", kind: "thinking", text: "", done: false }], true);
    assert.equal(toggle.getAttribute("aria-expanded"), "true");
    assert.equal(document.querySelectorAll(".development-process").length, 2, "assistant message splits groups");
    assert.equal(document.querySelector(".development-process__failure"), null, "failed items are not repeated above their original position");
    await act(async () => toggle.click());
    assert.equal(document.querySelector(".development-process__items").hidden, true);
    assert.match(toggle.textContent, /1 次工具调用.*1\.4 秒/);
  } finally { await act(async () => root.unmount()); dom.window.close(); }
});

test("development durations use readable units and carry rounded seconds across boundaries", async () => {
  const dom = new JSDOM('', { url: 'http://localhost' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage });
  localStorage.setItem('agentkit.studio.locale', 'zh-CN');
  const bundled = await build({ stdin: { contents: 'export { formatDevelopmentDuration } from "./src/create/developmentPresentation"; export { i18n } from "./src/i18n/runtime";', resolveDir: fileURLToPath(new URL('../', import.meta.url)) }, bundle: true, platform: 'node', format: 'esm', write: false });
  const { formatDevelopmentDuration, i18n } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString('base64')}#durations`);
  try {
    for (const [input, expected] of [
      [0, '<1 毫秒'], [0.4, '<1 毫秒'], [1, '1 毫秒'], [432, '432 毫秒'], [1000, '1 秒'], [1400, '1.4 秒'],
      [59949, '59.9 秒'], [59950, '1 分'], [60000, '1 分'],
      [1542277, '25 分 42.3 秒'], [3599999, '1 小时'], [3723456, '1 小时 2 分 3.5 秒'],
      [undefined, '未上报'], [NaN, '未上报'], [-1, '未上报'],
    ]) assert.equal(formatDevelopmentDuration(input), expected, String(input));
    await i18n.changeLanguage('en-US');
    for (const [input, expected] of [
      [0, '<1 ms'], [0.4, '<1 ms'], [1, '1 ms'], [432, '432 ms'], [1400, '1.4 s'], [1542277, '25 min 42.3 s'], [3723456, '1 h 2 min 3.5 s'],
    ]) assert.equal(formatDevelopmentDuration(input), expected, String(input));
    await i18n.changeLanguage('zh-CN');
    assert.equal(formatDevelopmentDuration(432), '432 毫秒');
  } finally { dom.window.close(); }
});

test("native actions expose meaningful file, directory, search and tool labels", async () => {
  const dom = new JSDOM('', { url: 'http://localhost' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage });
  localStorage.setItem('agentkit.studio.locale', 'zh-CN');
  const bundled = await build({ entryPoints: [fileURLToPath(new URL('../src/create/developmentPresentation.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false });
  const { developmentToolLabel } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString('base64')}`);
  try {
    const command = { kind: 'tool', itemType: 'commandExecution', name: '运行命令', done: false };
    const cases = [
      [{ ...command, args: { commandActions: [{ type: 'read', name: 'agent.py' }] } }, '读取文件 · Read project files'],
      [{ ...command, args: { commandActions: [{ type: 'listFiles', path: '/workspace' }] } }, '查看目录 · List directory'],
      [{ ...command, args: { commandActions: [{ type: 'search', query: 'root_agent', path: '/workspace' }] } }, '搜索 · Search project files'],
      [{ ...command, args: { command: 'pytest -q', commandActions: [{ type: 'unknown', command: 'pytest -q' }] } }, '执行命令 · Run tests'],
      [{ ...command, itemType: 'fileChange', args: { changes: [{ path: 'agent.py' }, { path: 'test_agent.py' }] } }, '修改文件 · agent.py, test_agent.py'],
      [{ ...command, itemType: 'mcpToolCall', name: 'MCP · docs/search' }, 'MCP · docs/search'],
    ];
    for (const [block, expected] of cases) assert.equal(developmentToolLabel(block), expected);
  } finally { dom.window.close(); }
});

test("delivery stages stay localized after native turn completion and retain stop feedback", async () => {
  const dom = new JSDOM('', {url:'http://localhost'});
  Object.assign(globalThis, {window:dom.window, document:dom.window.document, localStorage:dom.window.localStorage, sessionStorage:dom.window.sessionStorage});
  localStorage.setItem('agentkit.studio.locale','zh-CN');
  const bundled = await build({stdin:{contents:'export { developmentRunStatus, developmentToolLabel } from "./src/create/developmentPresentation"; export { i18n } from "./src/i18n/runtime";',resolveDir:fileURLToPath(new URL('../',import.meta.url))},bundle:true,platform:'node',format:'esm',write:false});
  const {developmentRunStatus, developmentToolLabel, i18n} = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString('base64')}#stages`);
  try {
    for(const [phase,zh,en] of [['outcome_read','正在整理产物','Preparing artifacts'],['delivery','正在整理产物','Preparing artifacts'],['version','正在保存版本','Saving version'],['cycle_complete','正在完成请求','Finishing request'],['reporting','正在补齐交付信息','Completing delivery details']]) {
      const run={phase,state:'running',statusMessage:'旧提示'};
      await i18n.changeLanguage('zh-CN');assert.equal(developmentRunStatus(run),zh);
      await i18n.changeLanguage('en-US');assert.equal(developmentRunStatus(run),en);
      assert.equal(developmentRunStatus({...run,state:'stopping',statusMessage:'Stopping'}),'Stopping');
    }
    await i18n.changeLanguage('zh-CN');
    assert.equal(developmentToolLabel({kind:'tool',itemType:'dynamicToolCall',name:'submit_build_result'}),'提交构建结果');
  } finally {dom.window.close();}
});
