// @vitest-environment jsdom
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { ConversationMarkdown, ConversationVisualization } from "../src/components/ai-app/ConversationFlow/ConversationRichContent";

const chart = vi.hoisted(() => ({ init: vi.fn(), instances: [] as { setOption: ReturnType<typeof vi.fn>; resize: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn> }[] }));
const mermaid = vi.hoisted(() => ({ initialize: vi.fn(), render: vi.fn() }));
vi.mock("echarts", () => ({ init: chart.init }));
vi.mock("mermaid", () => ({ default: mermaid }));

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  Element.prototype.scrollIntoView = vi.fn();
  const style = document.createElement("style");
  style.textContent = '[data-theme="dark"] .studio-conversation-rich-visual { --studio-text-primary: #dbdee7; --studio-bg-panel: #111111 } [data-theme="light"] .studio-conversation-rich-visual { --studio-text-primary: #252934; --studio-bg-panel: #ffffff }';
  document.head.append(style);
});

let root: Root;
let host: HTMLDivElement;
beforeEach(() => {
  vi.clearAllMocks();
  chart.instances = [];
  chart.init.mockImplementation(() => {
    const instance = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
    chart.instances.push(instance);
    return instance;
  });
  mermaid.render.mockResolvedValue({ svg: '<svg viewBox="0 0 100 40"><text>流程</text></svg>' });
  host = document.createElement("div");
  host.dataset.theme = "dark";
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

async function render(content: ReactNode) {
  await act(async () => root.render(content));
}
async function click(selector: string) {
  const button = host.querySelector<HTMLElement>(selector);
  expect(button).not.toBeNull();
  await act(async () => button!.click());
}

const source = "{xAxis:{type:'category',data:['A','B']},yAxis:{type:'value'},series:[{type:'bar',data:[2,5]}]}";

it("renders GFM tables and ordinary code with shared components and safe links", async () => {
  await render(<ConversationMarkdown text={'| 名称 | 结果 |\n| --- | --- |\n| **数据** | [查看](https://example.com) |\n\n```json\n{"ok":true}\n```\n\n[危险](javascript:alert(1))\n\n<script>unsafe()</script>'} />);
  expect(host.querySelector(".studio-table tbody td strong")?.textContent).toBe("数据");
  expect(host.querySelector(".studio-code-block code")?.textContent).toContain('"ok"');
  expect(host.querySelector('a[href="https://example.com"]')?.getAttribute("rel")).toBe("noopener noreferrer");
  expect(host.querySelector('a[href^="javascript:"]')).toBeNull();
  expect(host.querySelector("script")).toBeNull();
});

it("waits for the full chart definition and disposes its instance when source view opens", async () => {
  await render(<ConversationVisualization kind="echarts" source={source.slice(0, 20)} streaming />);
  expect(chart.init).not.toHaveBeenCalled();
  expect(host.querySelector(".studio-code-block")).not.toBeNull();
  expect(host.textContent).toContain("正在生成图表定义");
  await render(<ConversationVisualization kind="echarts" source={source} />);
  expect(chart.init).toHaveBeenCalledTimes(1);
  expect(chart.instances[0].setOption.mock.calls[0][0].series[0].data).toEqual([2, 5]);
  await click('[role="tab"][id$="source-tab"]');
  expect(chart.instances[0].dispose).toHaveBeenCalledTimes(1);
  expect(host.querySelector(".studio-code-block")).not.toBeNull();
});

it("retains completed chart fences while only the trailing incomplete chart is streaming", async () => {
  await render(<ConversationMarkdown text={`\`\`\`EChart\n${source}\n\`\`\`\n\n\`\`\`mermaid\nflowchart LR\n A -->`} streaming />);
  expect(chart.init).toHaveBeenCalledTimes(1);
  expect(mermaid.render).not.toHaveBeenCalled();
  expect(host.querySelector('[data-kind="mermaid"] .studio-code-block')).not.toBeNull();
});

it("rejects executable options and keeps source available", async () => {
  await render(<ConversationVisualization kind="echarts" source="{tooltip:{formatter: function () { return document.cookie; }}}" />);
  expect(chart.init).not.toHaveBeenCalled();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("图表定义无法解析");
  await click('[role="tab"][id$="source-tab"]');
  expect(host.querySelector(".studio-code-block code")?.textContent).toContain("formatter");
});

it("recreates charts when the enclosing theme changes", async () => {
  await render(<ConversationVisualization kind="echarts" source={source} />);
  const first = chart.instances[0];
  await act(async () => {
    host.dataset.theme = "light";
  });
  expect(first.dispose).toHaveBeenCalledTimes(1);
  expect(chart.init).toHaveBeenCalledTimes(2);
  expect(chart.init.mock.calls[chart.init.mock.calls.length - 1]?.[1].textStyle.color).toBe("#252934");
});

it("renders Mermaid under strict security and handles malformed definitions", async () => {
  await render(<ConversationVisualization kind="mermaid" source="flowchart LR\n A --> B" />);
  expect(mermaid.initialize).toHaveBeenLastCalledWith(expect.objectContaining({ securityLevel: "strict", suppressErrorRendering: true }));
  expect(host.querySelector(".studio-conversation-rich-visual__mermaid svg")).not.toBeNull();
  await click('[aria-label="放大图表"]');
  expect(host.querySelector(".studio-conversation-rich-visual__zoom")?.textContent).toContain("125%");
  mermaid.render.mockRejectedValueOnce(new Error("Invalid syntax"));
  await render(<ConversationVisualization kind="mermaid" source="not a diagram" />);
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("图表定义无法解析");
});
