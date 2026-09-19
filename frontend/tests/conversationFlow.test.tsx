// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { ConversationFlow } from "../src/components/ai-app/ConversationFlow/ConversationFlow";
import type { ConversationFlowProps, ConversationMessage } from "../src/components/ai-app/ConversationFlow/ConversationFlow.types";

vi.mock("../src/components/ai-app/ConversationFlow/ConversationRichContent", () => ({
  ConversationMarkdown: ({ text }: { text: string }) => <div data-renderer="markdown">{text}</div>,
  ConversationVisualization: ({ kind, source }: { kind: string; source: string }) => <div data-renderer={kind}>{source}</div>,
}));

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: true, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.mocked(navigator.clipboard.writeText).mockReset().mockResolvedValue(undefined);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });

async function render(messages: readonly ConversationMessage[], props: Omit<ConversationFlowProps, "messages"> = {}) {
  await act(async () => root.render(<ConversationFlow messages={messages} {...props} />));
}
async function click(element: Element | null) {
  expect(element).not.toBeNull();
  await act(async () => (element as HTMLElement).click());
}
function button(label: string) { return host.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`); }

it("preserves block order, renders system messages distinctly, and lets blocks override legacy content", async () => {
  await render([
    { id: "system", role: "system", content: "系统说明", name: "消息来源" },
    { id: "user", role: "user", content: "分析资料" },
    { id: "assistant", role: "assistant", content: "旧正文不应出现", steps: [{ id: "old", type: "reasoning", title: "旧思考不应出现" }], blocks: [
      { id: "first", type: "markdown", text: "开始分析" },
      { id: "tool", type: "tool", title: "检索资料", input: "{}" },
      { id: "chart", type: "visualization", kind: "echarts", source: "图表数据" },
      { id: "last", type: "markdown", text: "最终结论" },
    ] },
  ]);
  expect(Array.from(host.querySelectorAll(".studio-conversation-message")).map(node => node.getAttribute("data-role"))).toEqual(["system", "user", "assistant"]);
  expect(host.querySelector('[data-role="system"]')?.getAttribute("aria-label")).toBe("消息来源");
  expect(host.querySelector(".studio-conversation-message__avatar, .studio-conversation-message__name")).toBeNull();
  expect(host.textContent).not.toContain("消息来源");
  expect(host.textContent).not.toContain("旧正文");
  expect(host.textContent).not.toContain("旧思考");
  const blocks = host.querySelector(".studio-conversation-blocks")!.children;
  expect(Array.from(blocks).map(node => node.textContent)).toEqual(["开始分析", "检索资料已完成", "图表数据", "最终结论"]);
});

it("keeps valid zero metrics and hides negative or non-finite values", async () => {
  await render([{ id: "a", role: "assistant", durationMs: 0, ttftMs: 0, tokens: 0, model: "model-a" }]);
  expect(Array.from(host.querySelectorAll(".studio-conversation-message__metric dd")).map(node => node.textContent)).toEqual(["0 ms", "0 ms", "0", "model-a"]);
  await render([{ id: "a", role: "assistant", durationMs: -1, ttftMs: Infinity, tokens: NaN }]);
  expect(host.querySelector(".studio-conversation-message__metrics")).toBeNull();
});

it("updates message and step clocks without new events or rerendering reply content", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(1_800_000_000_000);
  let contentRenders = 0;
  function ReplyContent() {
    contentRenders += 1;
    return <p>等待工具完成</p>;
  }
  const message: ConversationMessage = {
    id: "live", role: "assistant", status: "running", startedAt: Date.now(), content: <ReplyContent />,
    steps: [{ id: "tool", type: "tool", title: "读取数据", status: "running", startedAt: Date.now() - 500 }],
  };
  try {
    await render([message]);
    const duration = () => host.querySelector(".studio-conversation-message__metric dd")?.textContent;
    const stepDuration = () => host.querySelector(".studio-conversation-step__duration")?.textContent;
    expect(duration()).toBe("0.0 s");
    expect(stepDuration()).toBe("0.5 s");
    await act(async () => vi.advanceTimersByTime(1200));
    expect(duration()).toBe("1.2 s");
    expect(stepDuration()).toBe("1.7 s");
    expect(contentRenders).toBe(1);
    await render([{ ...message, status: "cancelled" }]);
    const frozen = [duration(), stepDuration()];
    await act(async () => vi.advanceTimersByTime(2000));
    expect([duration(), stepDuration()]).toEqual(frozen);
  } finally {
    vi.useRealTimers();
  }
});

it("copies explicit text, emits controlled feedback, and allows stop only while running", async () => {
  const onRetry = vi.fn();
  const onFeedback = vi.fn();
  const onStop = vi.fn();
  const message = { id: "a", role: "assistant" as const, content: <strong>结构化回答</strong>, copyText: "可复制原文" };
  const handlers = { onRetry, onFeedback, onStop };
  await render([message], handlers);
  await click(button("复制消息"));
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("可复制原文");
  expect(button("已复制消息")).not.toBeNull();
  await click(button("重新生成回复"));
  expect(onRetry).toHaveBeenCalledWith("a");
  await click(button("有帮助"));
  expect(onFeedback).toHaveBeenLastCalledWith("a", "like");
  await render([{ ...message, feedback: "like" }], handlers);
  expect(button("有帮助")?.getAttribute("aria-pressed")).toBe("true");
  await click(button("有帮助"));
  expect(onFeedback).toHaveBeenLastCalledWith("a", null);
  expect(button("停止生成")).toBeNull();
  await render([{ ...message, status: "running" }], handlers);
  expect(button("重新生成回复")?.disabled).toBe(true);
  expect(button("没有帮助")?.disabled).toBe(true);
  await click(button("停止生成"));
  expect(onStop).toHaveBeenCalledWith("a");
  await render([{ ...message, status: "cancelled" }], handlers);
  expect(button("停止生成")).toBeNull();
  expect(host.querySelector(".studio-conversation-message__status")?.textContent).toBe("已停止");
});

it("reports clipboard failures and ignores a stale copy completion after content changes", async () => {
  vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error("Clipboard unavailable"));
  await render([{ id: "a", role: "assistant", content: "第一版" }]);
  await click(button("复制消息"));
  expect(host.querySelector(".studio-conversation-message__action-status")?.textContent).toBe("复制失败，请选择文字手动复制");
  let finish!: () => void;
  vi.mocked(navigator.clipboard.writeText).mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
  await click(button("复制消息"));
  expect(button("复制消息")?.disabled).toBe(true);
  await render([{ id: "a", role: "assistant", content: "第二版" }]);
  expect(button("复制消息")?.disabled).toBe(false);
  await act(async () => finish());
  expect(button("已复制消息")).toBeNull();
  expect(host.querySelector(".studio-conversation-message__action-status")?.textContent).toBe("");
});

it("keeps tool input and output independently collapsible and makes closed regions inert", async () => {
  await render([{ id: "a", role: "assistant", blocks: [{ id: "tool", type: "tool", title: "查询库存", status: "running", input: '{"sku":"A"}', output: '{"count":3}' }] }]);
  const outer = host.querySelector(".studio-conversation-step__dropdown > button")!;
  expect(outer.getAttribute("aria-expanded")).toBe("false");
  expect(host.querySelector(".studio-conversation-step__details")?.hasAttribute("inert")).toBe(true);
  expect(host.querySelectorAll(".studio-conversation-step__io-dropdown")).toHaveLength(0);
  await click(outer);
  const io = Array.from(host.querySelectorAll(".studio-conversation-step__io-dropdown"));
  expect(io).toHaveLength(2);
  expect(io.map(node => node.querySelector("button")!.getAttribute("aria-expanded"))).toEqual(["true", "true"]);
  await click(io[0].querySelector("button"));
  expect(io[0].querySelector("button")?.getAttribute("aria-expanded")).toBe("false");
  expect(io[0].querySelector(".studio-conversation-step__io-body")?.hasAttribute("inert")).toBe(true);
  expect(io[1].querySelector("button")?.getAttribute("aria-expanded")).toBe("true");
  await click(outer);
  expect(host.querySelector(".studio-conversation-step__details")?.hasAttribute("inert")).toBe(true);
  await click(outer);
  expect(io[0].querySelector("button")?.getAttribute("aria-expanded")).toBe("false");
  expect(io[1].querySelector("button")?.getAttribute("aria-expanded")).toBe("true");
});

it("animates only newly added steps and preserves existing disclosure state across streamed updates", async () => {
  const matchMedia = window.matchMedia;
  window.matchMedia = vi.fn(query => ({ ...matchMedia(query), matches: false }));
  const first = { id: "first", type: "tool" as const, title: "读取数据", status: "complete" as const, input: "{}" };
  const second = { id: "second", type: "tool" as const, title: "分析数据", status: "running" as const };
  try {
    await render([{ id: "a", role: "assistant", status: "running", blocks: [first] }]);
    const existing = host.querySelector('[data-step-id="first"]')!;
    const disclosure = existing.querySelector("button")!;
    expect(existing.hasAttribute("data-entering")).toBe(false);
    await click(disclosure);
    await render([{ id: "a", role: "assistant", status: "running", blocks: [first, second] }]);
    const added = host.querySelector('[data-step-id="second"]')!;
    expect(added.hasAttribute("data-entering")).toBe(true);
    expect(host.querySelector('[data-step-id="first"]')).toBe(existing);
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");

    const animationEnd = new Event("animationend", { bubbles: true });
    Object.defineProperty(animationEnd, "animationName", { value: "studio-conversation-step-content-in" });
    await act(async () => added.firstElementChild!.dispatchEvent(animationEnd));
    await render([
      { id: "a", role: "assistant", status: "complete", blocks: [first, { ...second, status: "complete" }] },
      { id: "b", role: "assistant", status: "running", steps: [first] },
    ]);
    expect(host.querySelector('[data-step-id="second"]')).toBe(added);
    expect(added.hasAttribute("data-entering")).toBe(false);
    const sameIdInNewMessage = host.querySelectorAll('[data-step-id="first"]')[1];
    expect(sameIdInNewMessage.hasAttribute("data-entering")).toBe(true);
    await act(async () => sameIdInNewMessage.querySelector<HTMLButtonElement>("button")!.focus());
    expect(sameIdInNewMessage.hasAttribute("data-entering")).toBe(false);

    await render([{ id: "a", role: "assistant", status: "running", blocks: [first] }]);
    await render([{ id: "a", role: "assistant", status: "running", blocks: [first, second] }]);
    const retried = host.querySelector('[data-step-id="second"]')!;
    expect(retried).not.toBe(added);
    expect(retried.hasAttribute("data-entering")).toBe(true);
    expect(host.querySelector('[data-step-id="first"]')).toBe(existing);
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
  } finally {
    window.matchMedia = matchMedia;
  }
});

it("shows new steps immediately with reduced motion and does not replay existing collapsed handoff steps", async () => {
  const matchMedia = window.matchMedia;
  window.matchMedia = vi.fn(query => ({ ...matchMedia(query), matches: false }));
  const child = { id: "nested", type: "tool" as const, title: "汇总数据", status: "complete" as const };
  const handoff = { id: "handoff", type: "handoff" as const, title: "交给分析智能体", toAgent: "分析智能体", status: "complete" as const, steps: [child] };
  try {
    await render([{ id: "a", role: "assistant", blocks: [handoff] }]);
    await click(host.querySelector('[data-step-id="handoff"] button'));
    expect(host.querySelector('[data-step-id="nested"]')?.hasAttribute("data-entering")).toBe(false);
    window.matchMedia = matchMedia;
    await render([{ id: "a", role: "assistant", blocks: [handoff, { ...child, id: "new" }] }]);
    expect(host.querySelector('[data-step-id="new"]')?.hasAttribute("data-entering")).toBe(false);
  } finally {
    window.matchMedia = matchMedia;
  }
});

it("dispatches authorization and cancellation callbacks and follows the supplied state", async () => {
  const onAuthorize = vi.fn();
  const onCancel = vi.fn();
  const authorization = { id: "auth", type: "authorization" as const, title: "连接知识库", onAuthorize, onCancel };
  await render([{ id: "a", role: "assistant", blocks: [{ ...authorization, status: "pending" }] }]);
  const actions = () => host.querySelectorAll<HTMLButtonElement>(".studio-conversation-authorization__actions button");
  await click(actions()[0]);
  expect(onAuthorize).toHaveBeenCalledOnce();
  await click(actions()[1]);
  expect(onCancel).toHaveBeenCalledOnce();
  await render([{ id: "a", role: "assistant", blocks: [{ ...authorization, status: "running" }] }]);
  expect(actions()).toHaveLength(1);
  expect(actions()[0].textContent).toBe("取消");
  await render([{ id: "a", role: "assistant", blocks: [{ ...authorization, status: "error" }] }]);
  expect(actions()[0].textContent).toBe("重新授权");
  await render([{ id: "a", role: "assistant", blocks: [{ ...authorization, status: "complete" }] }]);
  expect(actions()).toHaveLength(0);
  expect(host.querySelector(".studio-conversation-authorization__status")?.textContent).toBe("已完成");
});

it("supports user attachments with preview and download actions", async () => {
  const onPreview = vi.fn();
  const onDownload = vi.fn();
  await render([{ id: "u", role: "user", blocks: [{ id: "files", type: "files", files: [{ id: "f", name: "report.md", preview: <p>附件预览内容</p>, onPreview, onDownload }] }] }]);
  const preview = host.querySelector<HTMLElement>(".studio-conversation-file__preview")!;
  expect(preview.hidden).toBe(true);
  expect(preview.hasAttribute("inert")).toBe(true);
  await click(button("预览 report.md"));
  expect(onPreview).toHaveBeenCalledOnce();
  expect(preview.hidden).toBe(false);
  expect(preview.textContent).toBe("附件预览内容");
  await click(button("下载 report.md"));
  expect(onDownload).toHaveBeenCalledOnce();
  await click(button("预览 report.md"));
  expect(preview.hidden).toBe(true);
});

it("preserves handoff context, nested errors, plan statuses, and explicit message errors", async () => {
  await render([{ id: "a", role: "assistant", status: "error", error: "本次执行失败", blocks: [
    { id: "plan", type: "plan", title: "执行计划", items: [{ id: "p", title: "分析资料", status: "complete" }, { id: "q", title: "生成报告", status: "cancelled" }] },
    { id: "handoff", type: "handoff", title: "移交分析任务", fromAgent: "Coordinator", toAgent: "Researcher", status: "error", defaultOpen: true, steps: [{ id: "tool", type: "tool", title: "读取数据", status: "error", error: "数据源暂时不可用", defaultOpen: true }] },
  ] }]);
  expect(host.querySelector(".studio-conversation-handoff__route")?.textContent).toContain("Coordinator");
  expect(host.querySelector(".studio-conversation-handoff__route")?.textContent).toContain("Researcher");
  expect(Array.from(host.querySelectorAll(".studio-conversation-plan__item")).map(node => node.getAttribute("data-status"))).toEqual(["complete", "cancelled"]);
  expect(host.querySelector(".studio-conversation-step__error")?.textContent).toBe("数据源暂时不可用");
  expect(host.querySelector(".studio-conversation-message__error")?.textContent).toBe("本次执行失败");
});

it("only renders attachment downloads for safe URL schemes and inert file data MIME types", async () => {
  const allowed = [
    "https://example.com/report.pdf", "http://example.com/report.csv", "blob:https://example.com/resource-id",
    "/files/report.json", "./files/report.md", "../files/report.txt",
    "data:text/plain;charset=utf-8,hello", "data:text/csv,a%2Cb", "data:application/json,%7B%7D",
    "data:application/pdf;base64,JVBERi0=", "data:application/octet-stream;base64,YQ==",
    "data:image/png;base64,aA==", "data:image/jpeg;base64,aA==", "data:image/webp;base64,aA==",
  ];
  const denied = [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\nscript:alert(1)", "vbscript:msgbox(1)",
    "data:text/html,<script>alert(1)</script>", "data:image/svg+xml,<svg onload='alert(1)' />",
    "data:application/xhtml+xml,<html />", "data:text/plain;unknown=value,hello",
    "//example.com/report.pdf", "/\\example.com/report.pdf", "\\\\example.com/report.pdf",
    "file:///etc/passwd", "mailto:test@example.com", "https://", "http:example.com/report.pdf",
  ];
  await render([{ id: "a", role: "assistant", blocks: [{ id: "files", type: "files", files: [...allowed, ...denied].map((href, index) => ({ id: `file-${index}`, name: `file-${index}`, href })) }] }]);
  expect(Array.from(host.querySelectorAll(".studio-conversation-file__download")).map(link => link.getAttribute("href"))).toEqual(allowed);
});
