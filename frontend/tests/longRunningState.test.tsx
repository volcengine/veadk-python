// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { LongRunningState, type LongRunningStateProps } from "../src/components/composites/LongRunningState";

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  window.matchMedia = vi.fn().mockImplementation(query => ({
    matches: true, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
  }));
});

const steps = [
  { id: "start", title: "理解任务", details: "已确认任务范围" },
  { id: "search", title: "检索资料", details: "检索执行日志" },
  { id: "write", title: "生成结果", details: "结果执行日志" },
];
let root: Root;
let host: HTMLDivElement;
beforeEach(() => { host = document.createElement("div"); document.body.append(host); root = createRoot(host); });
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });

async function render(props: Partial<LongRunningStateProps> = {}) {
  await act(async () => root.render(<LongRunningState steps={steps} currentStep="search" {...props} />));
}
function title() { return host.querySelector('[role="status"]')?.textContent; }
function content() { return host.querySelector<HTMLElement>('[role="region"]')!; }
async function expectTitle(value: string) { await vi.waitFor(() => expect(title()).toBe(value)); }

it("presents the active name, indeterminate progress, and scrollable content in order", async () => {
  await render();
  const component = host.firstElementChild!;
  expect(Array.from(component.children).map(child => child.getAttribute("role"))).toEqual(["status", "progressbar", "region"]);
  expect(title()).toBe("检索资料");
  expect(host.querySelector('[role="progressbar"]')?.hasAttribute("aria-valuenow")).toBe(false);
  expect(content().textContent).toBe("检索执行日志");
  expect(content().tabIndex).toBe(0);
  expect(content().style.maxHeight).toBe("240px");
  expect(host.querySelector("button, ol")).toBeNull();
});

it("updates the step and resets scrolling without stacking old content", async () => {
  await render();
  content().scrollTop = 180;
  await render({ currentStep: "write" });
  await expectTitle("生成结果");
  expect(content().textContent).toBe("结果执行日志");
  expect(content().scrollTop).toBe(0);
  expect(host.querySelectorAll('[role="region"]')).toHaveLength(1);
});

it("keeps the reading position when the current step receives new content", async () => {
  await render();
  content().scrollTop = 120;
  await render({ steps: steps.map(step => step.id === "search" ? { ...step, title: "核对资料", details: "更新后的检索日志" } : step) });
  await expectTitle("核对资料");
  expect(content().textContent).toBe("更新后的检索日志");
  expect(content().scrollTop).toBe(120);
});

it("stops progress at completion, preserves the final result, and supports restarting", async () => {
  await render({ currentStep: null, completedSteps: steps.map(step => step.id) });
  expect(title()).toBe("任务已完成");
  expect(host.firstElementChild?.getAttribute("data-state")).toBe("complete");
  expect(host.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow")).toBe("100");
  expect(content().textContent).toBe("结果执行日志");
  await render({ currentStep: "start", completedSteps: [] });
  await expectTitle("理解任务");
  expect(host.firstElementChild?.getAttribute("data-state")).toBe("running");
  expect(content().textContent).toBe("已确认任务范围");
});

it("handles waiting and empty tasks without claiming completion", async () => {
  await render({ currentStep: null, completedSteps: ["start", "unknown"], detailsMaxHeight: 160 });
  expect(title()).toBe("等待下一步");
  expect(content().textContent).toBe("已确认任务范围");
  expect(content().style.maxHeight).toBe("160px");
  expect(host.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow")).toBe("0");
  await render({ steps: [], currentStep: null });
  await expectTitle("等待任务开始");
  expect(content().textContent).toBe("");
  expect(host.firstElementChild?.getAttribute("data-state")).toBe("idle");
});
