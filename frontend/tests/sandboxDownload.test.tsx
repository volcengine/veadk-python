import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SandboxFileContext, sandboxFilePath } from "../src/ui/SandboxFileLink";
import { Markdown } from "../src/ui/Markdown";
const { download } = vi.hoisted(() => ({ download: vi.fn() }));
vi.mock("../src/adk/client", () => ({ fetchSessionFile: download }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../src/ui/EChartsDiagram", () => ({ EChartsDiagram: () => null }));
vi.mock("../src/ui/MermaidDiagram", () => ({ MermaidDiagram: () => null }));
vi.mock("../src/ui/VisualizationPanel", () => ({ VisualizationPanel: () => null }));
let host: HTMLDivElement;
let root: Root;
let click: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  download.mockReset().mockResolvedValue(new Blob(["report"]));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:report"), revokeObjectURL: vi.fn() }));
  click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(async () => { await act(() => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function render(text = "[report](/data/output/report.pdf)", sessionId = "session-one", scoped = true) {
  await act(() => root.render(<SandboxFileContext.Provider value={scoped ? { appName: "runtime-app", sessionId } : null}><Markdown text={text} /></SandboxFileContext.Provider>));
}
async function activate() { await act(() => { host.querySelector("a")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })); }); }
it.each(["/data/output/report.pdf", "/data/workspace/分析 结果.xlsx", "/data/output/sub/file.txt"])("accepts %s", (path) => expect(sandboxFilePath(encodeURI(path))).toBe(path));
it.each([undefined, "https://example.com/data/output/a", "/data/output2/a", "/data/output/", "/data/output/../secret", "/data/workspace/./a", "/data/output/%2e%2e/a", "/data/output/a%00b", "/data/output/a%5Cb", "/data/output/a?x=1", "/data/output/a#hash", "/data/output/%", "/etc/passwd"])("rejects %s", (path) => expect(sandboxFilePath(path)).toBeNull());
it("downloads history Markdown with current session and releases the object URL", async () => {
  await render("[分析结果](</data/workspace/分析 结果.xlsx>)"); await activate();
  expect(download).toHaveBeenCalledWith("runtime-app", "session-one", "/data/workspace/分析 结果.xlsx", expect.any(AbortSignal));
  expect(click.mock.instances[0].download).toBe("分析 结果.xlsx");
  expect(click.mock.instances[0].href).toBe("blob:report");
  await new Promise((resolve) => setTimeout(resolve, 5));
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report");
  expect(document.querySelector('a[download]')).toBeNull();
});
it("preserves external and unscoped links and prioritizes sandbox video downloads", async () => {
  await render("[site](https://example.com)"); expect(host.querySelector("a")!.target).toBe("_blank");
  await render(undefined, undefined, false); expect(host.querySelector("a")!.target).toBe("_blank");
  await render("[movie](/data/output/movie.mp4)"); expect(host.querySelector("video")).toBeNull(); await activate(); expect(download).toHaveBeenCalled();
});
it("shows a pending state, ignores duplicate clicks, then allows retry after a failure", async () => {
  let reject!: (error: Error) => void;
  download.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  await render(); await activate(); await activate();
  expect(download).toHaveBeenCalledTimes(1); expect(host.querySelector("a")!.getAttribute("aria-disabled")).toBe("true");
  expect(host.textContent).toContain("markdown.downloading");
  await act(() => reject(new Error("private server response")));
  expect(host.querySelector('[role="alert"]')!.textContent?.trim()).toBe("markdown.downloadFailed");
  expect(host.textContent).not.toContain("private");
  await activate(); expect(download).toHaveBeenCalledTimes(2); expect(host.querySelector('[role="alert"]')).toBeNull();
});
it.each(["resolve", "reject"])("aborts old scope and ignores late %s", async (result) => {
  let resolve!: (blob: Blob) => void; let reject!: (error: Error) => void;
  download.mockImplementationOnce(() => new Promise((ok, fail) => { resolve = ok; reject = fail; }));
  await render(); await activate(); const signal = download.mock.calls[0][3];
  await render(undefined, "session-two"); expect(signal.aborted).toBe(true);
  await act(() => result === "resolve" ? resolve(new Blob()) : reject(new Error("late")));
  expect(click).not.toHaveBeenCalled(); expect(host.querySelector('[role="alert"]')).toBeNull();
  await activate(); expect(download.mock.calls[1][1]).toBe("session-two");
});

it("hides legacy card content while preserving the answer and prominent download control", async () => {
  await render('Answer\n\n[report](/data/output/report.pdf)\n\n<file-card size="100">arkdrive_user_upload/private/report.pdf</file-card>\n<personal-drive-enable-card>Enable drive</personal-drive-enable-card>');
  expect(host.textContent).toContain("Answer");
  expect(host.textContent).not.toContain("arkdrive_user_upload");
  expect(host.textContent).not.toContain("Enable drive");
  expect(host.querySelector("a")!.className).toBe("sandbox-file-download");
  expect(host.querySelector("a")!.textContent).toContain("markdown.downloadFile");
  await render('Before\n\n<file-card>hidden even without closing tag');
  expect(host.textContent).toContain("Before");
  expect(host.textContent).not.toContain("hidden even");
});
