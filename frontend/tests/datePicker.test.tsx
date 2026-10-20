// @vitest-environment jsdom
import React, { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { DatePicker, type DatePickerProps } from "../src/components/primitives/DatePicker";
import { formatPickerValue, parsePickerValue } from "../src/components/primitives/DatePicker/dateValue";

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  Element.prototype.scrollIntoView = vi.fn();
});

describe("date values", () => {
  it("round trips leap days and rejects impossible dates and zoned values", () => {
    expect(formatPickerValue(parsePickerValue("2028-02-29", "day"), "day")).toBe("2028-02-29");
    expect(() => parsePickerValue("2027-02-29", "day")).toThrow();
    expect(() => parsePickerValue("2028-02-30", "day")).toThrow();
    expect(() => parsePickerValue("2028-02-29T09:00Z", "minute")).toThrow();
    expect(() => parsePickerValue("2028-02-29T09:00+08:00", "minute")).toThrow();
  });
  it("preserves wall time and normalizes minute precision", () => {
    expect(formatPickerValue(parsePickerValue("2028-02-29T09:07:32", "minute"), "minute")).toBe("2028-02-29T09:07");
    expect(formatPickerValue(parsePickerValue("", "minute"), "minute")).toBe("");
    expect(parsePickerValue(null, "day")).toBeNull();
  });
  it("includes the whole day when min/max omit a time", () => {
    expect(formatPickerValue(parsePickerValue("2028-02-29", "minute", "min"), "minute")).toBe("2028-02-29T00:00");
    expect(formatPickerValue(parsePickerValue("2028-02-29", "minute", "max"), "minute")).toBe("2028-02-29T23:59");
  });
});

let root: Root;
let host: HTMLDivElement;
beforeEach(() => { host = document.createElement("div"); document.body.append(host); root = createRoot(host); });
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });

async function render(props: DatePickerProps = {}) {
  await act(async () => root.render(<DatePicker aria-label="Execution date" locale="en-US" {...props} />));
}
async function click(element: Element | null) {
  expect(element).not.toBeNull();
  await act(async () => (element as HTMLElement).click());
}
function day(label: string) {
  return Array.from(document.querySelectorAll<HTMLElement>(".studio-date-picker__day")).find(cell => cell.getAttribute("aria-label")?.includes(label)) ?? null;
}

it("opens the calendar, chooses a date, and closes", async () => {
  const change = vi.fn();
  await render({ defaultValue: "2028-02-28", onChange: change });
  await click(host.querySelector("button"));
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  await click(day("February 29, 2028"));
  expect(change).toHaveBeenLastCalledWith("2028-02-29");
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("completes an empty date-time with the placeholder time", async () => {
  const change = vi.fn();
  await render({ granularity: "minute", placeholderValue: "2028-02-28T09:00", onChange: change });
  await click(host.querySelector("button"));
  await click(day("February 29, 2028"));
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  await click(document.querySelector(".studio-date-picker__done"));
  expect(change).toHaveBeenLastCalledWith("2028-02-29T09:00");
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("keeps a controlled task time unchanged when its timezone changes", async () => {
  const change = vi.fn();
  const props = { value: "2028-03-12T09:00", granularity: "minute" as const, name: "runAt", onChange: change };
  await render({ ...props, timeZone: "Asia/Shanghai" });
  const segments = host.querySelector(".studio-date-picker__segments")!.textContent;
  await render({ ...props, timeZone: "America/Los_Angeles" });
  expect(host.querySelector(".studio-date-picker__segments")!.textContent).toBe(segments);
  expect(change).not.toHaveBeenCalled();
});

it("respects day limits and disables confirmation for out-of-range time", async () => {
  await render({ defaultValue: "2028-02-28T08:00", granularity: "minute", minValue: "2028-02-28T09:00", maxValue: "2028-02-29T18:00" });
  await click(host.querySelector("button"));
  expect(day("February 27, 2028")?.getAttribute("aria-disabled")).toBe("true");
  expect((document.querySelector(".studio-date-picker__done") as HTMLButtonElement).disabled).toBe(true);
});

it("supports segment keyboard editing and controlled reset", async () => {
  function Controlled() {
    const [value, setValue] = useState("2028-02-28");
    return <><DatePicker value={value} onChange={setValue} aria-label="Date" locale="en-US" /><button onClick={() => setValue("")}>Clear</button></>;
  }
  await act(async () => root.render(<Controlled />));
  const segment = host.querySelector<HTMLElement>('[data-type="day"]')!;
  await act(async () => { segment.focus(); segment.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true })); });
  expect(segment.textContent).toBe("29");
  await click(host.querySelector(":scope > button"));
  expect(host.querySelector('[data-type="day"]')?.hasAttribute("data-placeholder")).toBe(true);
});

it("prevents editing when disabled or read-only", async () => {
  await render({ disabled: true, defaultValue: "2028-02-29" });
  expect((host.querySelector("button") as HTMLButtonElement).disabled).toBe(true);
  await render({ readOnly: true, defaultValue: "2028-02-29" });
  await click(host.querySelector("button"));
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("closes on Escape without bubbling to a parent dialog", async () => {
  const parentEscape = vi.fn();
  window.addEventListener("keydown", parentEscape);
  try {
    await render({ defaultValue: "2028-02-29" });
    await click(host.querySelector("button"));
    await act(async () => document.querySelector('[role="dialog"]')!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(parentEscape).not.toHaveBeenCalled();
  } finally { window.removeEventListener("keydown", parentEscape); }
});
