// @vitest-environment jsdom
import React, { act } from "react";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { RuntimeArtifacts } from "../src/runtime-artifacts/RuntimeArtifacts";
import { listRuntimeArtifacts, getRuntimeArtifact, RuntimeArtifactRequestError, type RuntimeArtifactScope } from "../src/adk/runtimeArtifacts";

vi.mock("../src/adk/runtimeArtifacts", () => ({ listRuntimeArtifacts: vi.fn(), getRuntimeArtifact: vi.fn(), MAX_ARTIFACT_PREVIEW_BYTES: 5 * 1024 * 1024,
  RuntimeArtifactRequestError: class extends Error { constructor(message: string, readonly status: number) { super(message); } },
}));
vi.mock("../src/components/ai-app/ConversationFlow/ConversationRichContent", () => ({ ConversationMarkdown: ({ text }: { text: string }) => <p>{text}</p> }));
vi.mock("../src/components/composites/CodeBlock", () => ({ CodeBlock: ({ lines }: { lines: string[] }) => <pre>{lines.join("\n")}</pre> }));
vi.mock("../src/components/composites/FileExplorer/FileExplorerPane", () => ({ fileText: () => "", FileExplorerPane: () => null }));

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: true, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  Element.prototype.scrollIntoView = vi.fn();
});

let host: HTMLDivElement;
let root: Root;
const scope: RuntimeArtifactScope = { runtimeId: "runtime-1", region: "cn-beijing", appName: "runtime_artifacts", sessionId: "session-1" };
const artifact = { path: "reports/report.html", name: "report.html", mimeType: "text/html", sizeBytes: 100, updatedAt: "v1" };
beforeEach(() => {
  vi.mocked(listRuntimeArtifacts).mockReset().mockResolvedValue({ available: true, items: [artifact], nextCursor: null });
  vi.mocked(getRuntimeArtifact).mockReset().mockResolvedValue({ size: 100, text: async () => '<h1>真实产物</h1><script>alert(1)</script>' } as Blob);
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });
async function render(selectedScope = scope, busy = false) {
  await act(async () => root.render(<RuntimeArtifacts key={`${selectedScope.runtimeId}:${selectedScope.sessionId}`} scope={selectedScope} busy={busy} />));
}
async function click(element: Element | null) {
  expect(element).not.toBeNull();
  await act(async () => (element as HTMLElement).click());
}
function button(text: string) { return Array.from(document.querySelectorAll("button")).find(node => node.textContent === text) ?? null; }

it("mounts a single artifact entry in the composer instead of inside transcript replies", () => {
  const source = readFileSync(`${process.cwd()}/src/App.tsx`, "utf8");
  const file = ts.createSourceFile("App.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const entries: ts.JsxSelfClosingElement[] = [];
  let composer: ts.VariableDeclaration | undefined;
  function visit(node: ts.Node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(file) === "composer") composer = node;
    if (ts.isJsxSelfClosingElement(node) && node.tagName.getText(file) === "RuntimeArtifacts") entries.push(node);
    ts.forEachChild(node, visit);
  }
  visit(file);
  expect(entries).toHaveLength(1);
  expect(composer).toBeDefined();
  expect(entries[0].pos).toBeGreaterThan(composer!.pos);
  expect(entries[0].end).toBeLessThan(composer!.end);
  expect(entries[0].getText(file)).toContain("busy={activeConversationBusy}");
  expect(entries[0].getText(file)).toContain("userId");
  expect(entries[0].getText(file)).toContain("currentRuntimeAppName || appName");
});

it("opens from the conversation, selects a nested file, and uses a scriptless preview", async () => {
  await render();
  expect(listRuntimeArtifacts).toHaveBeenCalledTimes(1);
  await click(button("会话产物"));
  expect(listRuntimeArtifacts).toHaveBeenCalledWith(scope, expect.any(AbortSignal), undefined);
  await click(document.querySelector('[role="treeitem"][title="report.html"]'));
  expect(getRuntimeArtifact).toHaveBeenCalledWith(scope, artifact.path, expect.any(AbortSignal));
  const frame = document.querySelector("iframe")!;
  expect(frame.getAttribute("sandbox")).toBe("");
  expect(frame.srcdoc).toContain("真实产物");
  expect(frame.srcdoc).not.toContain("<script");
  await click(document.querySelector('[aria-label="关闭会话产物"]'));
  expect(document.querySelector("iframe")).toBeNull();
});

it("distinguishes missing storage from an empty session and exposes retry after failure", async () => {
  vi.mocked(listRuntimeArtifacts).mockResolvedValueOnce({ available: false, reason: "请检查 Studio 存储配置", items: [], nextCursor: null });
  await render(); await click(button("会话产物"));
  expect(document.body.textContent).toContain("产物存储暂不可用");
  expect(document.body.textContent).toContain("请检查 Studio 存储配置");
  expect(document.body.textContent).not.toContain("这个会话还没有产物");
  vi.mocked(listRuntimeArtifacts).mockRejectedValueOnce(new Error("TOS 权限不足"));
  await click(button("刷新"));
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("TOS 权限不足");
  vi.mocked(listRuntimeArtifacts).mockResolvedValueOnce({ available: true, items: [], nextCursor: null });
  await click(button("重试"));
  expect(document.body.textContent).toContain("这个会话还没有产物");
});

it("aborts stale requests and closes old artifacts when the session changes", async () => {
  let finish!: (value: Awaited<ReturnType<typeof listRuntimeArtifacts>>) => void;
  vi.mocked(listRuntimeArtifacts).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  await render(); await click(button("会话产物"));
  const signal = vi.mocked(listRuntimeArtifacts).mock.calls[0][1]!;
  expect(button("刷新")?.disabled).toBe(true);
  await render({ ...scope, sessionId: "session-2" });
  expect(signal.aborted).toBe(true);
  await act(async () => finish({ available: true, items: [artifact], nextCursor: null }));
  expect(document.querySelector('[role="treeitem"]')).toBeNull();
  await click(button("会话产物"));
  expect(listRuntimeArtifacts).toHaveBeenLastCalledWith({ ...scope, sessionId: "session-2" }, expect.any(AbortSignal), undefined);
});

it("refreshes on completion and pages without clearing existing files", async () => {
  vi.mocked(listRuntimeArtifacts).mockResolvedValueOnce({ available: true, items: [artifact], nextCursor: "page-2" });
  await render(scope, true);
  expect(button("会话产物")?.disabled).toBe(false);
  await click(button("会话产物"));
  const second = { ...artifact, path: "notes.txt", name: "notes.txt", mimeType: "text/plain" };
  vi.mocked(listRuntimeArtifacts).mockResolvedValueOnce({ available: true, items: [second], nextCursor: null });
  await click(button("加载更多文件"));
  expect(document.querySelector('[title="report.html"]')).not.toBeNull();
  expect(document.querySelector('[title="notes.txt"]')).not.toBeNull();
  expect(listRuntimeArtifacts).toHaveBeenLastCalledWith(scope, expect.any(AbortSignal), "page-2");
  await render(scope, false);
  expect(listRuntimeArtifacts).toHaveBeenCalledTimes(3);
});

it("reuses preview blobs across switching, reopening, and unchanged refreshes, and reloads changed versions", async () => {
  const second = { ...artifact, path: "notes.txt", name: "notes.txt", mimeType: "text/plain" };
  vi.mocked(listRuntimeArtifacts).mockResolvedValue({ available: true, items: [artifact, second], nextCursor: null });
  await render(); await click(button("会话产物"));
  await click(document.querySelector('[title="report.html"]'));
  await click(document.querySelector('[title="notes.txt"]'));
  await click(document.querySelector('[title="report.html"]'));
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(2);
  await click(document.querySelector('[aria-label="关闭会话产物"]'));
  await click(button("会话产物"));
  expect(document.querySelector("iframe")?.srcdoc).toContain("真实产物");
  expect(listRuntimeArtifacts).toHaveBeenCalledTimes(1);
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(2);
  await click(button("刷新"));
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(2);
  vi.mocked(listRuntimeArtifacts).mockResolvedValueOnce({ available: true, items: [{ ...artifact, updatedAt: "v2" }, second], nextCursor: null });
  await click(button("刷新"));
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(3);
});

it("warms files after a reply completes even while the drawer stays closed", async () => {
  vi.mocked(listRuntimeArtifacts).mockResolvedValueOnce({ available: true, items: [], nextCursor: null });
  await render(scope, true);
  expect(getRuntimeArtifact).not.toHaveBeenCalled();
  await render(scope, false);
  expect(listRuntimeArtifacts).toHaveBeenCalledTimes(2);
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(1);
  await click(button("会话产物"));
  await click(document.querySelector('[title="report.html"]'));
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(1);
});

it("removes cached previews if revalidation reports lost access", async () => {
  await render(); await click(button("会话产物"));
  await click(document.querySelector('[title="report.html"]'));
  expect(document.querySelector("iframe")).not.toBeNull();
  vi.mocked(listRuntimeArtifacts).mockRejectedValueOnce(new RuntimeArtifactRequestError("访问权限已撤销", 403));
  await click(button("刷新"));
  expect(document.querySelector("iframe")).toBeNull();
  expect(document.body.textContent).toContain("访问权限已撤销");
  await click(button("重试"));
  expect(getRuntimeArtifact).toHaveBeenCalledTimes(2);
});

it("keeps the HTML body readable while images load and after an image request fails", async () => {
  let fail!: (error: Error) => void;
  vi.mocked(getRuntimeArtifact).mockResolvedValueOnce({ size: 100, text: async () => '<h1>正文先显示</h1><img src="chart.svg">' } as Blob)
    .mockReturnValueOnce(new Promise((_resolve, reject) => { fail = reject; }));
  await render(); await click(button("会话产物"));
  await click(document.querySelector('[title="report.html"]'));
  expect(document.querySelector("iframe")?.srcdoc).toContain("正文先显示");
  expect(document.body.textContent).toContain("正在加载图片");
  await act(async () => fail(new Error("图片请求超时")));
  expect(document.querySelector("iframe")?.srcdoc).toContain("正文先显示");
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("图片请求超时");
});
