// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ConversationMessageTimingScope, ConversationTimingProvider, useConversationElapsedTime } from "../src/components/ai-app/ConversationFlow/ConversationTiming";
import type { ConversationAssistantMessage, ConversationMessage, ConversationStepBase } from "../src/components/ai-app/ConversationFlow/ConversationFlow.types";

let host: HTMLDivElement;
let root: Root;
const epoch = 1_800_000_000_000;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.useFakeTimers();
  vi.setSystemTime(epoch);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function Label({ kind, id, timing }: { kind: "message" | "step"; id: string; timing: Pick<ConversationStepBase, "status" | "durationMs" | "startedAt" | "endedAt"> }) {
  const elapsed = useConversationElapsedTime(kind, id, timing);
  return <output data-id={id}>{elapsed === undefined ? "none" : Math.round(elapsed)}</output>;
}

async function render(messages: readonly ConversationMessage[], content: React.ReactNode) {
  await act(async () => root.render(<ConversationTimingProvider messages={messages}>{content}</ConversationTimingProvider>));
}

async function advance(ms: number) { await act(async () => { vi.advanceTimersByTime(ms); }); }
function value(id: string) { return host.querySelector(`[data-id="${id}"]`)?.textContent; }

function scoped(message: ConversationAssistantMessage, children?: React.ReactNode) {
  return <ConversationMessageTimingScope messageId={message.id}>
    <Label kind="message" id={message.id} timing={message} />
    {children ?? message.steps?.map(step => <Label key={step.id} kind="step" id={step.id} timing={step} />)}
  </ConversationMessageTimingScope>;
}

it("advances all active clocks without events using one interval without re-rendering rich content", async () => {
  const richRender = vi.fn();
  function RichContent() { richRender(); return <div>图表与 Markdown</div>; }
  const message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", startedAt: epoch - 2000, steps: [
    { id: "tool", type: "tool", title: "工具", status: "running", startedAt: epoch - 1000 },
  ] };
  await render([message], <>{scoped(message)}<RichContent /></>);
  expect(value("reply")).toBe("2000");
  expect(value("tool")).toBe("1000");
  expect(vi.getTimerCount()).toBe(1);
  await advance(1200);
  expect(value("reply")).toBe("3200");
  expect(value("tool")).toBe("2200");
  expect(richRender).toHaveBeenCalledTimes(1);
});

it("keeps a stable baseline across sparse events and calibrates running time without going backward", async () => {
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", durationMs: 500 };
  await render([message], scoped(message));
  await advance(1000);
  expect(value("reply")).toBe("1500");
  message = { ...message, content: "新 token，耗时快照未变" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("1500");
  message = { ...message, durationMs: 3000 };
  await render([message], scoped(message));
  expect(value("reply")).toBe("3000");
  message = { ...message, durationMs: 800 };
  await render([message], scoped(message));
  expect(value("reply")).toBe("3000");
  await advance(500);
  expect(value("reply")).toBe("3500");
});

it("freezes a stopped run with stale duration data and resets a same-id retry", async () => {
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", durationMs: 400 };
  await render([message], scoped(message));
  await advance(1500);
  message = { ...message, status: "cancelled" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("1900");
  expect(vi.getTimerCount()).toBe(0);
  await advance(1000);
  expect(value("reply")).toBe("1900");
  message = { ...message, status: "running" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("0");
  await advance(700);
  message = { ...message, content: "重试 token" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("700");
  message = { ...message, status: "complete", endedAt: Date.now() };
  await render([message], scoped(message));
  expect(value("reply")).toBe("700");
  expect(vi.getTimerCount()).toBe(0);
});

it("uses new final duration or end timestamps authoritatively", async () => {
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", durationMs: 100, startedAt: epoch - 100 };
  await render([message], scoped(message));
  await advance(1000);
  message = { ...message, status: "complete", durationMs: 950 };
  await render([message], scoped(message));
  expect(value("reply")).toBe("950");
  message = { id: "next", role: "assistant", status: "running", startedAt: Date.now() - 500 };
  await render([message], scoped(message));
  await advance(1000);
  message = { ...message, status: "error", endedAt: Date.now() - 200 };
  await render([message], scoped(message));
  expect(value("next")).toBe("1300");
  await advance(500);
  expect(value("next")).toBe("1300");
});

it("registers collapsed handoff steps before their labels mount and stops them with their parent", async () => {
  const step = { id: "nested", type: "tool" as const, title: "查询", status: "running" as const, durationMs: 100 };
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", blocks: [
    { id: "handoff", type: "handoff", title: "移交", toAgent: "analysis", status: "running", steps: [step] },
  ] };
  await render([message], <div>折叠的步骤</div>);
  expect(vi.getTimerCount()).toBe(0);
  await advance(2100);
  const content = <ConversationMessageTimingScope messageId={message.id}><Label kind="step" id={step.id} timing={step} /></ConversationMessageTimingScope>;
  await render([message], content);
  expect(value("nested")).toBe("2200");
  await advance(500);
  message = { ...message, status: "cancelled" };
  await render([message], content);
  expect(value("nested")).toBe("2700");
  await advance(1000);
  expect(value("nested")).toBe("2700");
  expect(vi.getTimerCount()).toBe(0);
});

it("does not count pending time or render NaN and removes inactive intervals", async () => {
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "pending", durationMs: NaN, startedAt: Infinity };
  await render([message], scoped(message));
  expect(value("reply")).toBe("none");
  expect(vi.getTimerCount()).toBe(0);
  await advance(2000);
  message = { ...message, status: "running" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("0");
  await advance(500);
  expect(value("reply")).toBe("500");
  await render([message], null);
  expect(vi.getTimerCount()).toBe(0);
  await render([message], scoped(message));
  expect(vi.getTimerCount()).toBe(1);
  await render([], null);
  expect(vi.getTimerCount()).toBe(0);
  await render([message], scoped(message));
  await act(async () => root.render(null));
  expect(vi.getTimerCount()).toBe(0);
});

it("catches up from wall-clock time after a background pause rather than adding tick counts", async () => {
  const message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running" };
  await render([message], scoped(message));
  vi.setSystemTime(epoch + 60_000);
  await advance(100);
  expect(value("reply")).toBe("60100");
});

it("keeps identically named steps isolated between messages and accepts historical zero times", async () => {
  const first: ConversationAssistantMessage = { id: "first", role: "assistant", status: "running", steps: [{ id: "tool", type: "tool", title: "查询", status: "running", durationMs: 100 }] };
  const second: ConversationAssistantMessage = { id: "second", role: "assistant", durationMs: 0, steps: [{ id: "tool", type: "tool", title: "查询", durationMs: 900 }] };
  await render([first, second], <>{scoped(first)}{scoped(second)}</>);
  await advance(500);
  expect(Array.from(host.querySelectorAll('[data-id="tool"]')).map(item => item.textContent)).toEqual(["600", "900"]);
  expect(value("second")).toBe("0");
  const invalid = { ...second, durationMs: -1 };
  await render([invalid], scoped(invalid));
  expect(value("second")).toBe("none");
});

it("does not invent an elapsed duration for historical records with only a start timestamp", async () => {
  const message: ConversationAssistantMessage = { id: "reply", role: "assistant", startedAt: epoch - 60_000, steps: [
    { id: "tool", type: "tool", title: "查询", startedAt: epoch - 60_000 },
  ] };
  await render([message], scoped(message));
  expect(value("reply")).toBe("none");
  expect(value("tool")).toBe("none");
  expect(vi.getTimerCount()).toBe(0);
});

it("resets a running same-id attempt when its start timestamp changes", async () => {
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", startedAt: epoch - 5000, durationMs: 5000 };
  await render([message], scoped(message));
  await advance(1000);
  expect(value("reply")).toBe("6000");
  message = { ...message, startedAt: Date.now() };
  await render([message], scoped(message));
  expect(value("reply")).toBe("0");
  await advance(500);
  expect(value("reply")).toBe("500");
});

it("registers steps rendered inside custom React content and retains their baseline when collapsed", async () => {
  let step = { id: "nested-custom", status: "running" as const, startedAt: epoch - 500 };
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", content: <div>自定义工具结果</div> };
  const content = () => <ConversationMessageTimingScope messageId={message.id}><Label kind="step" id={step.id} timing={step} /></ConversationMessageTimingScope>;
  await render([message], content());
  expect(value(step.id)).toBe("500");
  await advance(500);
  expect(value(step.id)).toBe("1000");
  await render([message], null);
  expect(vi.getTimerCount()).toBe(0);
  await advance(1000);
  await render([message], content());
  expect(value(step.id)).toBe("2000");
  step = { ...step, startedAt: Date.now() };
  await render([message], content());
  expect(value(step.id)).toBe("0");
  await advance(500);
  message = { ...message, status: "cancelled" };
  await render([message], content());
  expect(value(step.id)).toBe("500");
  expect(vi.getTimerCount()).toBe(0);
});

it("honors an end timestamp even if the status has not changed and ignores stale endpoints on retry", async () => {
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", startedAt: epoch - 1000, endedAt: epoch - 100 };
  await render([message], scoped(message));
  expect(value("reply")).toBe("900");
  expect(vi.getTimerCount()).toBe(0);
  message = { ...message, status: "complete" };
  await render([message], scoped(message));
  await advance(1000);
  message = { ...message, status: "running" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("0");
  await advance(500);
  message = { ...message, content: "重试数据" };
  await render([message], scoped(message));
  expect(value("reply")).toBe("500");
  message = { ...message, endedAt: Date.now() };
  await render([message], scoped(message));
  expect(value("reply")).toBe("500");
  expect(vi.getTimerCount()).toBe(0);
});

it("propagates effective end timestamps to child steps without applying stale endpoints to a retry", async () => {
  const step = { id: "tool", type: "tool" as const, title: "工具", status: "running" as const, startedAt: epoch };
  let message: ConversationAssistantMessage = { id: "reply", role: "assistant", status: "running", startedAt: epoch, steps: [step] };
  await render([message], scoped(message));
  await advance(500);
  message = { ...message, endedAt: Date.now() };
  await render([message], scoped(message));
  await advance(500);
  expect(value("tool")).toBe("500");
  expect(vi.getTimerCount()).toBe(0);
  message = { ...message, startedAt: Date.now() };
  await render([message], scoped(message));
  expect(value("tool")).toBe("0");
  await advance(500);
  expect(value("tool")).toBe("500");

  const nested = { ...step, id: "nested", startedAt: Date.now() };
  message = { id: "handoff-reply", role: "assistant", status: "running", blocks: [
    { id: "handoff", type: "handoff", title: "移交", toAgent: "analysis", status: "running", startedAt: Date.now(), steps: [nested] },
  ] };
  const content = <ConversationMessageTimingScope messageId={message.id}><Label kind="step" id={nested.id} timing={nested} /></ConversationMessageTimingScope>;
  await render([message], content);
  await advance(500);
  message = { ...message, blocks: [{ id: "handoff", type: "handoff", title: "移交", toAgent: "analysis", status: "running", startedAt: nested.startedAt, endedAt: Date.now(), steps: [nested] }] };
  await render([message], content);
  await advance(500);
  expect(value("nested")).toBe("500");
  expect(vi.getTimerCount()).toBe(0);
});
