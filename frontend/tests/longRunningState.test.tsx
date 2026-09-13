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
function button(label: string) {
  const element = Array.from(host.querySelectorAll("button")).find(item => item.getAttribute("aria-label") === label || item.textContent === label);
  expect(element).toBeDefined();
  return element!;
}
async function click(label: string) { await act(async () => button(label).click()); }
function details() { return host.querySelector(".studio-long-running-state__details-content:not([data-exiting])")?.textContent; }

it("keeps unchanged step titles mounted while status transitions animate their icons", async () => {
  await render();
  const runningTitle = button("检索资料，进行中").querySelector(".studio-long-running-state__title-text");
  const pendingTitle = button("生成结果，待执行").querySelector(".studio-long-running-state__title-text");
  await render({ currentStep: "write" });
  await vi.waitFor(() => {
    expect(button("检索资料，已完成").querySelectorAll(".studio-long-running-state__title-text")).toHaveLength(1);
    expect(button("生成结果，进行中").querySelectorAll(".studio-long-running-state__title-text")).toHaveLength(1);
  });
  expect(button("检索资料，已完成").querySelector(".studio-long-running-state__title-text")).toBe(runningTitle);
  expect(button("生成结果，进行中").querySelector(".studio-long-running-state__title-text")).toBe(pendingTitle);
});

it("opens completed records without changing the current running step and blocks pending steps", async () => {
  await render();
  expect(button("生成结果，待执行").disabled).toBe(true);
  await click("理解任务，已完成");
  expect(details()).toBe("已确认任务范围");
  expect(button("理解任务，已完成").getAttribute("aria-pressed")).toBe("true");
  expect(host.querySelector('[aria-current="step"]')?.textContent).toContain("检索资料");
  await click("返回当前步骤");
  expect(details()).toBe("检索执行日志");
  expect(document.activeElement).toBe(button("检索资料，进行中"));
});

it("shows only the latest record during repeated history switches", async () => {
  await render({ currentStep: "write" });
  for (const [label, content] of [
    ["理解任务，已完成", "已确认任务范围"],
    ["检索资料，已完成", "检索执行日志"],
    ["理解任务，已完成", "已确认任务范围"],
    ["生成结果，进行中", "结果执行日志"],
  ]) {
    await click(label);
    expect(host.querySelectorAll(".studio-long-running-state__details-content")).toHaveLength(1);
    expect(details()).toBe(content);
  }
});

it("retains the marker through progress and restart so a transition can reverse in place", async () => {
  await render();
  const circle = button("生成结果，待执行").querySelector(".studio-long-running-state__marker-shape circle");
  expect(circle).not.toBeNull();
  await render({ currentStep: "write" });
  expect(button("生成结果，进行中").querySelector(".studio-long-running-state__marker-shape circle")).toBe(circle);
  await render({ currentStep: null, completedSteps: steps.map(step => step.id) });
  expect(button("生成结果，已完成").querySelector(".studio-long-running-state__marker-shape circle")).toBe(circle);
  await render({ currentStep: "start" });
  expect(button("生成结果，待执行").querySelector(".studio-long-running-state__marker-shape circle")).toBe(circle);
});

it("keeps a historical record selected while execution advances, then resumes following progress", async () => {
  await render();
  await click("理解任务，已完成");
  await render({ currentStep: "write" });
  expect(details()).toBe("已确认任务范围");
  expect(host.querySelector('[aria-current="step"]')?.textContent).toContain("生成结果");
  await click("返回当前步骤");
  expect(details()).toBe("结果执行日志");
  await render({ currentStep: null, completedSteps: steps.map(step => step.id) });
  expect(details()).toBe("结果执行日志");
  expect(host.querySelector('[role="status"]')?.textContent).toBe("所有步骤已完成");
  await click("检索资料，已完成");
  expect(details()).toBe("检索执行日志");
});

it("supports controlled record selection and reports returning to live progress as null", async () => {
  const onSelectedStepChange = vi.fn();
  await render({ selectedStep: null, onSelectedStepChange });
  await click("理解任务，已完成");
  expect(onSelectedStepChange).toHaveBeenLastCalledWith("start");
  expect(details()).toBe("检索执行日志");
  await render({ selectedStep: "start", onSelectedStepChange });
  expect(details()).toBe("已确认任务范围");
  await click("返回当前步骤");
  expect(onSelectedStepChange).toHaveBeenLastCalledWith(null);
});

it("clears stale history after a restart and resets the scroll position on record changes", async () => {
  await render({ currentStep: "write" });
  await click("检索资料，已完成");
  const viewport = host.querySelector<HTMLDivElement>(".studio-long-running-state__details-scroll")!;
  viewport.scrollTop = 180;
  await click("理解任务，已完成");
  expect(viewport.scrollTop).toBe(0);
  await render({ currentStep: "start" });
  await render({ currentStep: "search" });
  expect(details()).toBe("检索执行日志");
});

it("honors explicitly incomplete earlier steps and handles an empty task", async () => {
  await render({ currentStep: "write", completedSteps: ["start"] });
  expect(button("检索资料，待执行").disabled).toBe(true);
  expect(host.querySelector(".studio-long-running-state__progress")?.textContent).toBe("已完成 1 / 3");
  await render({ steps: [], currentStep: null });
  expect(host.querySelector(".studio-long-running-state__details-heading")?.textContent).toBe("等待任务开始");
});
