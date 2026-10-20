// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { EditorView } from "@codemirror/view";
import { syntaxTree } from "@codemirror/language";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { FileExplorer, type FileExplorerProps, type FileExplorerEntry } from "../src/components/composites/FileExplorer";
import { formatFileContent } from "../src/components/composites/FileExplorer/formatFileContent";

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  Range.prototype.getClientRects = vi.fn(() => Object.assign([] as DOMRect[], { item: () => null }));
  Range.prototype.getBoundingClientRect = vi.fn(() => new DOMRect());
  Element.prototype.scrollIntoView = vi.fn();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

let host: HTMLDivElement;
let root: Root;
const entries: readonly FileExplorerEntry[] = [
  { id: "a", name: "a.json", type: "file", content: '{"name":"original"}' },
  { id: "b", name: "b.ts", type: "file", content: 'const enabled = true;' },
];
beforeEach(() => { host = document.createElement("div"); document.body.append(host); root = createRoot(host); });
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });

async function render(props: Partial<FileExplorerProps> = {}) {
  await act(async () => {
    root.render(<FileExplorer entries={entries} defaultSelectedId="a" autoFormat={false} {...props} />);
  });
  await act(async () => { await vi.dynamicImportSettled(); });
}
function saveButton() { return host.querySelector<HTMLButtonElement>('[aria-label^="保存 "]')!; }
async function edit(content: string) {
  const editor = host.querySelector<HTMLElement>(".cm-editor")!;
  expect(editor).not.toBeNull();
  const view = EditorView.findFromDOM(editor)!;
  await act(async () => view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: content } }));
}
async function click(element: Element) { await act(async () => (element as HTMLElement).click()); }
function currentText() { return EditorView.findFromDOM(host.querySelector<HTMLElement>(".cm-editor")!)!.state.doc.toString(); }

it("formats compact JSON and TypeScript without changing meaning, and leaves unsupported languages intact", async () => {
  const json = await formatFileContent('{"name":"demo","tools":["search","summarize"]}', "config.json");
  expect(json).toContain("\n");
  expect(JSON.parse(json)).toEqual({ name: "demo", tools: ["search", "summarize"] });
  const ts = await formatFileContent('export function add(a: number, b: number) { return a + b; }', "sum.ts");
  expect(ts).toContain("\n  return a + b;");
  expect(await formatFileContent("x =  1\n", "agent.py")).toBe("x =  1\n");
  await expect(formatFileContent('{"broken":', "config.json")).rejects.toThrow();
});

it.each(["__proto__", "constructor", "toString"])("ignores inherited parser names for %s", async name => {
  const original = "unsupported =  unchanged\n";
  expect(await formatFileContent(original, `notes.${name}`)).toBe(original);
  expect(await formatFileContent(original, "notes.txt", name)).toBe(original);
  const json = await formatFileContent('{"enabled":true}', "config.json", name);
  expect(json).toContain("\n");
  expect(JSON.parse(json)).toEqual({ enabled: true });
});

it.each(["__proto__", "constructor", "toString"])("uses the filename for unknown editor language %s", async language => {
  await render({
    allowEdit: true,
    entries: [{ id: "a", name: "a.ts", type: "file", language, content: "const enabled: boolean = true;" }],
  });
  const editor = EditorView.findFromDOM(host.querySelector<HTMLElement>(".cm-editor")!)!;
  expect(syntaxTree(editor.state).type.name).toBe("Script");
});

it("keeps prototype-like file ids editable with independent drafts and errors", async () => {
  const specialEntries: readonly FileExplorerEntry[] = [
    { id: "__proto__", name: "first.json", type: "file", content: '{"name":"first"}' },
    { id: "constructor", name: "second.json", type: "file", content: '{"name":"second"}' },
    { id: "toString", name: "third.json", type: "file", content: '{"name":"third"}' },
  ];
  const onSave = vi.fn().mockRejectedValueOnce(new Error("Offline")).mockResolvedValue(undefined);
  await render({ entries: specialEntries, defaultSelectedId: "__proto__", allowEdit: true, onSave });
  expect(host.querySelector('[role="alert"]')).toBeNull();
  await edit('{"name":"first draft"}');
  await click(saveButton());
  expect(host.querySelector('[role="alert"]')?.textContent).toBe("保存失败，请重试");
  await click(host.querySelector('[title="second.json"]')!);
  expect(host.querySelector('[role="alert"]')).toBeNull();
  expect(currentText()).toBe('{"name":"second"}');
  await edit('{"name":"second draft"}');
  await click(saveButton());
  expect(onSave).toHaveBeenLastCalledWith("constructor", '{"name":"second draft"}', specialEntries[1]);
  expect(saveButton().disabled).toBe(true);
  await click(host.querySelector('[title="third.json"]')!);
  expect(host.querySelector('[role="alert"]')).toBeNull();
  expect(currentText()).toBe('{"name":"third"}');
  await click(host.querySelector('[title="first.json"]')!);
  expect(currentText()).toBe('{"name":"first draft"}');
  expect(host.querySelector('[role="alert"]')?.textContent).toBe("保存失败，请重试");
  await click(host.querySelector('[aria-label="Copy code"]')!);
  expect(navigator.clipboard.writeText).toHaveBeenLastCalledWith('{"name":"first draft"}');
  await click(saveButton());
  expect(onSave).toHaveBeenLastCalledWith("__proto__", '{"name":"first draft"}', specialEntries[0]);
  expect(host.querySelector('[role="alert"]')).toBeNull();
  expect(saveButton().disabled).toBe(true);
});

it("defaults to read-only wrapping and shows no save action", async () => {
  await render();
  expect(host.querySelector(".cm-editor")).toBeNull();
  expect(saveButton()).toBeNull();
  expect(host.querySelector("[data-word-wrap]")).not.toBeNull();
  expect(host.querySelector('.studio-file-explorer__content')?.getAttribute("data-orientation")).toBe("vertical");
  expect(host.querySelector(".studio-code-block__header")?.closest(".studio-scroll-area")).toBeNull();
});

it("preserves independent drafts when switching files, copies the draft, and calls edit/save handlers", async () => {
  const onEdit = vi.fn();
  const onSave = vi.fn();
  await render({ allowEdit: true, onEdit, onSave });
  expect(saveButton().disabled).toBe(true);
  await edit('{"name":"draft"}');
  expect(onEdit).toHaveBeenLastCalledWith("a", '{"name":"draft"}', entries[0]);
  await click(host.querySelector('[title="b.ts"]')!);
  await act(async () => { await vi.dynamicImportSettled(); });
  expect(currentText()).toBe("const enabled = true;");
  await click(host.querySelector('[title="a.json"]')!);
  await act(async () => { await vi.dynamicImportSettled(); });
  expect(currentText()).toBe('{"name":"draft"}');
  await click(host.querySelector('[aria-label="Copy code"]')!);
  expect(navigator.clipboard.writeText).toHaveBeenLastCalledWith('{"name":"draft"}');
  await click(saveButton());
  expect(onSave).toHaveBeenLastCalledWith("a", '{"name":"draft"}', entries[0]);
  expect(saveButton().disabled).toBe(true);
});

it("retains edits made during saving and prevents duplicate submissions", async () => {
  let finish!: () => void;
  const onSave = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  await render({ allowEdit: true, onSave });
  await edit("first draft");
  await click(saveButton());
  expect(saveButton().getAttribute("aria-busy")).toBe("true");
  await click(saveButton());
  expect(onSave).toHaveBeenCalledTimes(1);
  await edit("newer draft");
  await act(async () => finish());
  expect(currentText()).toBe("newer draft");
  expect(saveButton().disabled).toBe(false);
});

it("keeps failed saves editable and supports retry via Ctrl+S", async () => {
  const onSave = vi.fn().mockRejectedValueOnce(new Error("Offline")).mockResolvedValue(undefined);
  await render({ allowEdit: true, onSave });
  await edit("unsaved draft");
  await click(saveButton());
  expect(host.querySelector('[role="alert"]')?.textContent).toBe("保存失败，请重试");
  expect(currentText()).toBe("unsaved draft");
  await act(async () => host.querySelector(".cm-content")!.dispatchEvent(new KeyboardEvent("keydown", { key: "s", ctrlKey: true, bubbles: true, cancelable: true })));
  expect(onSave).toHaveBeenCalledTimes(2);
  expect(host.querySelector('[role="alert"]')).toBeNull();
  expect(saveButton().disabled).toBe(true);
});

it("disables saving without a handler and can restore horizontal scrolling", async () => {
  await render({ allowEdit: true, wordWrap: false });
  await edit("updated");
  expect(saveButton().disabled).toBe(true);
  expect(host.querySelector("[data-word-wrap]")).toBeNull();
  expect(host.querySelector('.studio-file-explorer__content')?.getAttribute("data-orientation")).toBe("both");
});
