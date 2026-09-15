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
    assert.match(toggle.textContent, /读取文件.*agent.py/);
    await render([{ ...thinking, done: true }, tool], true, "正在恢复连接");
    assert.match(toggle.textContent, /正在恢复连接/);
    await render([{ ...thinking, done: true }, { ...tool, done: true, status: "failed", durationMs: 1400 }, { id: "t:answer", kind: "text", text: "已保留结果" }, { id: "t:r2", kind: "thinking", text: "", done: false }], true);
    assert.equal(toggle.getAttribute("aria-expanded"), "true");
    assert.equal(document.querySelectorAll(".development-process").length, 2, "assistant message splits groups");
    assert.match(document.querySelector(".development-process__failure").textContent, /执行失败/);
    await act(async () => toggle.click());
    assert.equal(document.querySelector(".development-process__items").hidden, true);
    assert.match(document.querySelector(".development-process__failure").textContent, /agent.py/);
  } finally { await act(async () => root.unmount()); dom.window.close(); }
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
      [{ ...command, args: { commandActions: [{ type: 'read', name: 'agent.py' }] } }, '读取文件 · agent.py'],
      [{ ...command, args: { commandActions: [{ type: 'listFiles', path: '/workspace' }] } }, '查看目录 · /workspace'],
      [{ ...command, args: { commandActions: [{ type: 'search', query: 'root_agent', path: '/workspace' }] } }, '搜索 · root_agent'],
      [{ ...command, args: { command: 'pytest -q', commandActions: [{ type: 'unknown', command: 'pytest -q' }] } }, '执行命令 · pytest -q'],
      [{ ...command, itemType: 'fileChange', args: { changes: [{ path: 'agent.py' }, { path: 'test_agent.py' }] } }, '修改文件 · agent.py, test_agent.py'],
      [{ ...command, itemType: 'mcpToolCall', name: 'MCP · docs/search' }, 'MCP · docs/search'],
    ];
    for (const [block, expected] of cases) assert.equal(developmentToolLabel(block), expected);
  } finally { dom.window.close(); }
});
