import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MpaCronTasks } from "../src/cronjobs/MpaCronTasks";
import { MpaTaskEditor } from "../src/cronjobs/MpaTaskEditor";
import { MpaTaskDetail, mpaErrorKey } from "../src/cronjobs/MpaTaskDetail";
import {
  fetchMpaCronTasks,
  fetchMpaRuns,
  manageMpaTask,
  type MpaCronTask,
} from "../src/adk/mpaCronTasks";
import {
  calendarTimes,
  formatTime,
  monthDays,
  scheduleText,
  taskStatus,
} from "../src/cronjobs/mpaSchedule";
const { list, runs, write } = vi.hoisted(() => ({
  list: vi.fn(),
  runs: vi.fn(),
  write: vi.fn(),
}));
vi.mock("../src/adk/client", () => ({
  listMpaCronTasks: list,
  listMpaRuns: runs,
  requestMpaTask: write,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));
vi.mock("../src/ui/SandboxControls", () => ({
  DialogShell: ({
    children,
    title,
    onClose,
    busy,
  }: {
    children: React.ReactNode;
    title: string;
    onClose: () => void;
    busy?: boolean;
  }) => (
    <div role="dialog">
      <h2>{title}</h2>
      <button disabled={busy} onClick={onClose}>
        close
      </button>
      {children}
    </div>
  ),
}));
vi.mock("../src/ui/DeploymentSelect", () => ({
  DeploymentSelect: ({
    ariaLabel,
    value,
    options,
    onChange,
  }: {
    ariaLabel: string;
    value: string;
    options: { value: string; label: string }[];
    onChange: (s: string) => void;
  }) => (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("@openai/apps-sdk-ui/components/Menu", () => {
  const Part = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  );
  return {
    Menu: Object.assign(Part, {
      Trigger: Part,
      Content: Part,
      Item: ({
        children,
        onSelect,
      }: {
        children: React.ReactNode;
        onSelect: () => void;
      }) => <button onClick={onSelect}>{children}</button>,
    }),
  };
});
const runtime = { runtimeId: "r1", region: "cn-beijing", name: "Runtime One" };
const task: MpaCronTask = {
  id: "t1",
  name: "Report",
  agentId: "agent1",
  prompt: "News",
  version: 3,
  enabled: true,
  schedule: { type: "Daily", timezone: "Asia/Shanghai", time: "09:00" },
  lastRunAt: "2026-09-15T00:00:00Z",
  lastRunStatus: "Succeeded",
};
const page = {
  items: [task],
  total: 1,
  hasMore: false,
  nextOffset: null,
  overview: { executionCount: 4, successRate: 0.75 },
};
let root: Root, host: HTMLDivElement;
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
async function render(
  node: React.ReactNode = <MpaCronTasks runtime={runtime} />,
) {
  if (!host) {
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
  }
  await act(async () => root.render(node));
}
async function click(text: string) {
  const button = [...host.querySelectorAll("button")].find(
    (b) => b.textContent === text || b.getAttribute("aria-label") === text,
  );
  expect(button, `button ${text}`).toBeTruthy();
  await act(async () => button!.click());
}
async function field(label: string, value: string) {
  if (label === "mpa.manage.lastStatus") {
    await click(`mpa.manage.${value}`);
    return;
  }
  const element =
    host.querySelector(`[aria-label="${label}"]`) ||
    [...host.querySelectorAll("label")]
      .find((l) => l.textContent === label)
      ?.querySelector("input,textarea");
  expect(element, `field ${label}`).toBeTruthy();
  await act(async () => {
    const proto =
      element instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : element instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(element, value);
    element!.dispatchEvent(
      new Event(element instanceof HTMLSelectElement ? "change" : "input", {
        bubbles: true,
      }),
    );
  });
}
async function submit() {
  await act(async () =>
    [...host.querySelectorAll("form")]
      .at(-1)!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
}
beforeEach(() => {
  list.mockResolvedValue(page);
  runs.mockResolvedValue({
    items: [],
    total: 0,
    hasMore: false,
    nextOffset: null,
  });
  write.mockResolvedValue({ task, run: { id: "run1" }, removed: true });
});
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  host?.remove();
  host = undefined!;
  vi.resetAllMocks();
});
it("uses no requests without selection and switches targets without stale data", async () => {
  await render(<MpaCronTasks />);
  expect(list).not.toHaveBeenCalled();
  let resolve!: (p: typeof page) => void;
  list.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
  await render();
  expect(host.textContent).toContain("mpa.loading");
  const signal = list.mock.calls[0][3];
  await render(<MpaCronTasks runtime={{ ...runtime, runtimeId: "r2" }} />);
  expect(signal.aborted).toBe(true);
  await act(async () =>
    resolve({ ...page, items: [{ ...task, name: "stale" }] }),
  );
  expect(host.textContent).not.toContain("stale");
});
it("loads all pages for calendar/filtering and paginates the list locally", async () => {
  list
    .mockResolvedValueOnce({
      ...page,
      items: Array.from({ length: 10 }, (_, n) => ({ ...task, id: `t${n}` })),
      hasMore: true,
      nextOffset: 20,
    })
    .mockResolvedValueOnce({
      ...page,
      items: [{ ...task, id: "last", name: "Last" }],
    });
  await render();
  expect(list.mock.calls[1][1]).toBe(20);
  await click("mpa.next");
  expect(host.textContent).toContain("Last");
  await click("mpa.previous");
  await field("mpa.manage.lastStatus", "Failed");
  expect(host.textContent).toContain("mpa.empty");
  await field("mpa.manage.lastStatus", "all");
  await field("mpa.search", "report");
  await submit();
  expect(list.mock.calls.at(-1)![2]).toBe("report");
  await click("mpa.refresh");
  expect(host.textContent).toContain("75%");
  await click("mpa.manage.calendar");
  expect(host.querySelectorAll(".mpa-calendar-day")).toHaveLength(42);
  await click("mpa.manage.prevMonth");
  await click("mpa.manage.nextMonth");
  await click("mpa.manage.today");
  await click("mpa.manage.list");
});
it("opens detail, editor, copy and delete; submits scoped versioned actions", async () => {
  await render();
  await click("Report");
  expect(runs).toHaveBeenCalledWith(runtime, "t1", 0, expect.any(AbortSignal));
  await click("close");
  await click("mpa.manage.detail");
  await click("close");
  await click("mpa.manage.edit");
  await field("mpa.manage.name", "Edited");
  await submit();
  expect(write.mock.calls.at(-1)![3]).toMatchObject({
    name: "Edited",
    expectedVersion: 3,
  });
  await click("mpa.manage.copy");
  expect(write).toHaveBeenCalledTimes(1);
  await submit();
  expect(write.mock.calls.at(-1)![2]).toBe("");
  expect(write.mock.calls.at(-1)![3]).toMatchObject({
    clientToken: expect.any(String),
  });
  await click("mpa.manage.enabled Report");
  expect(write.mock.calls.at(-1)![3]).toEqual({
    enabled: false,
    expectedVersion: 3,
  });
  await click("mpa.manage.run Report");
  expect(write.mock.calls.at(-1)![2]).toBe("/t1/run");
  await click("mpa.manage.delete");
  await click("mpa.manage.cancel");
  await click("mpa.manage.delete");
  await act(async () =>
    [...host.querySelectorAll('[role="dialog"] button')]
      .find((b) => b.textContent === "mpa.manage.delete")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true })),
  );
  expect(write.mock.calls.at(-1)![1]).toBe("DELETE");
});
it("keeps retry tokens after errors and prevents duplicate writes", async () => {
  await render();
  write.mockRejectedValueOnce(new Error("MPA_HTTP_409"));
  await click("mpa.manage.run Report");
  expect(host.textContent).toContain("mpa.manage.conflict");
  const token = write.mock.calls[0][3].clientToken;
  await click("mpa.manage.run Report");
  expect(write.mock.calls[1][3].clientToken).toBe(token);
  let resolve!: (v: unknown) => void;
  write.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
  await click("mpa.manage.enabled Report");
  await click("mpa.manage.enabled Report");
  expect(write).toHaveBeenCalledTimes(3);
  await act(async () => resolve({ task }));
});
it("supports create, retains form on failure, and rejects malformed mutation results", async () => {
  await render();
  await click("mpa.manage.create");
  await field("mpa.manage.name", "New");
  await field("mpa.manage.agent", "agent");
  await field("mpa.manage.prompt", "prompt");
  write.mockResolvedValueOnce({});
  await submit();
  expect(host.textContent).toContain("mpa.invalidResponse");
  const token = write.mock.calls[0][3].clientToken;
  await submit();
  expect(write.mock.calls[1][3].clientToken).toBe(token);
  expect(host.querySelector('[role="dialog"]')).toBeNull();
  await click("mpa.manage.edit");
  await click("mpa.manage.cancel");
});
it.each([
  "MPA_HTTP_401",
  "MPA_HTTP_403",
  "MPA_HTTP_404",
  "MPA_HTTP_422",
  "MPA_HTTP_409",
  "MPA_INVALID_RESPONSE",
  "network",
])("reports and retries %s", async (e) => {
  list.mockRejectedValueOnce(new Error(e));
  await render();
  expect(host.textContent).toContain(mpaErrorKey(new Error(e)));
  await click("mpa.refresh");
  expect(host.textContent).toContain("Report");
});
it("ignores late errors and write completion after unmount", async () => {
  let reject!: (e: unknown) => void;
  list.mockImplementationOnce(() => new Promise((_, r) => (reject = r)));
  await render();
  await act(async () => root.unmount());
  await act(async () => reject("late"));
  host.remove();
  host = undefined!;
  await render();
  write.mockImplementationOnce(() => new Promise((_, r) => (reject = r)));
  await click("mpa.manage.run Report");
  const signal = write.mock.calls[0][4];
  await act(async () => root.unmount());
  expect(signal.aborted).toBe(true);
  await act(async () => reject(new Error("late")));
});
it("rejects missing task version and invalid pagination", async () => {
  list.mockResolvedValueOnce({
    ...page,
    items: [{ ...task, version: undefined }],
  });
  await render();
  await click("mpa.manage.enabled Report");
  expect(write).not.toHaveBeenCalled();
  expect(host.textContent).toContain("mpa.invalidResponse");
  list.mockResolvedValueOnce({ ...page, hasMore: true, nextOffset: 0 });
  await click("mpa.refresh");
  expect(host.textContent).toContain("mpa.invalidResponse");
});
it("handles empty pages, unknown statuses and IME search", async () => {
  list.mockResolvedValueOnce({
    ...page,
    overview: undefined,
    items: [
      {
        ...task,
        lastRunAt: null,
        agentId: undefined,
        lastRunStatus: null,
        enabled: false,
      },
    ],
  });
  await render();
  expect(host.textContent).toContain("mpa.manage.Pending");
  const input = host.querySelector("input")!;
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    ),
  );
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    ),
  );
  await submit();
  expect(list).toHaveBeenCalledTimes(1);
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    ),
  );
  list.mockResolvedValueOnce({ ...page, items: [] });
  await submit();
  expect(host.textContent).toContain("mpa.empty");
  expect(mpaErrorKey("offline")).toBe("mpa.loadFailed");
});
it("loads run pages and handles retry, null dates, errors and stale history", async () => {
  runs.mockResolvedValueOnce({
    items: [
      {
        id: "run1",
        status: "Failed",
        scheduledAt: "2026-09-15T00:00:00Z",
        errorMessage: "Failed",
        durationMs: 45,
      },
      {
        id: "run2",
        status: "Succeeded",
        startedAt: "2026-09-15T00:00:00Z",
        scheduledAt: "2026-09-15",
        sessionId: "session1",
      },
    ],
    total: 21,
    hasMore: true,
    nextOffset: 20,
  });
  await render(
    <MpaTaskDetail task={task} runtime={runtime} onClose={() => {}} />,
  );
  expect(host.textContent).toContain("45 ms");
  expect(host.textContent).toContain("session1");
  await click("mpa.next");
  expect(runs.mock.calls.at(-1)![2]).toBe(20);
  await click("mpa.previous");
  runs.mockRejectedValueOnce(new Error("MPA_HTTP_401"));
  await click("mpa.refresh");
  expect(host.textContent).toContain("mpa.authRequired");
  await click("mpa.refresh");
  expect(host.textContent).toContain("mpa.manage.noRuns");
});
const identity = (key: string) => key;
it("formats schedule types and expands recurring dates in their timezone", () => {
  expect(formatTime(null, "en")).toBe("—");
  expect(formatTime("bad", "en")).toBe("—");
  expect(taskStatus({ ...task, runningAt: "now" })).toBe("Running");
  const day = new Date("2026-09-15T00:00:00");
  for (const schedule of [
    { type: "Once", runAt: "2026-09-15T01:00:00Z" },
    {
      type: "Interval",
      intervalSeconds: 3600,
      anchorAt: "2026-09-15T00:00:00Z",
    },
    { type: "Daily", time: "09:00" },
    { type: "Weekly", time: "09:00", weekdays: [2] },
    { type: "Monthly", time: "09:00", monthDays: [15] },
    { type: "Cron", cronExpression: "0 9 * * *" },
    { type: "Cron", cronExpression: "0 9 15 * *" },
    { type: "Cron", cronExpression: "0 9 * * 2" },
  ]) {
    const sample = {
      ...task,
      schedule: { ...schedule, timezone: "Asia/Shanghai" },
    };
    expect(scheduleText(sample, identity, "en")).toContain(schedule.type);
    expect(calendarTimes(sample, day)).not.toBeNull();
  }
  expect(calendarTimes({ ...task, enabled: false }, day)).toBeNull();
  expect(calendarTimes({ ...task, createdAt: "2027-01-01" }, day)).toBeNull();
  expect(
    calendarTimes({ ...task, schedule: { type: "Daily" } }, day),
  ).toBeNull();
  expect(
    calendarTimes(
      { ...task, schedule: { type: "Weekly", time: "09:00", weekdays: [1] } },
      day,
    ),
  ).toBeNull();
  expect(
    calendarTimes(
      { ...task, schedule: { type: "Monthly", time: "09:00", monthDays: [1] } },
      day,
    ),
  ).toBeNull();
  expect(
    calendarTimes(
      { ...task, schedule: { type: "Once", runAt: "2027-01-01" } },
      day,
    ),
  ).toBeNull();
  expect(
    calendarTimes(
      { ...task, schedule: { type: "Interval", intervalSeconds: 1 } },
      day,
    ),
  ).toBeNull();
  expect(
    calendarTimes(
      {
        ...task,
        schedule: { type: "Interval", intervalSeconds: 3600 },
        nextRunAt: "2027-01-01",
      },
      day,
    ),
  ).toBeNull();
  expect(
    calendarTimes(
      {
        ...task,
        schedule: { type: "Cron", cronExpression: "*/5 * * * *" },
        nextRunAt: "2026-09-15T01:00:00Z",
      },
      day,
    )?.nextOnly,
  ).toBe(true);
  expect(
    calendarTimes(
      { ...task, schedule: { type: "Cron", cronExpression: "bad" } },
      day,
    ),
  ).toBeNull();
  expect(monthDays(day)).toHaveLength(42);
});
it("skips nonexistent DST wall times and preserves repeated wall times", () => {
  const sample = {
    ...task,
    schedule: { type: "Daily", timezone: "America/New_York", time: "02:30" },
  };
  expect(calendarTimes(sample, new Date("2026-03-08T00:00:00"))).toBeNull();
  expect(
    calendarTimes(
      { ...sample, schedule: { ...sample.schedule, time: "01:30" } },
      new Date("2026-11-01T00:00:00"),
    )?.count,
  ).toBe(2);
});
it.each([401, 403, 404, 409, 422, 500])(
  "does not echo upstream bodies %s",
  async (status) => {
    const req = vi.fn().mockResolvedValue(new Response("secret", { status }));
    await expect(
      manageMpaTask(req, runtime, "POST", "/id/run", {}),
    ).rejects.toThrow(`MPA_HTTP_${status}`);
    await expect(fetchMpaRuns(req, runtime, "id", 0)).rejects.toThrow(
      `MPA_HTTP_${status}`,
    );
  },
);
it("validates run and mutation responses and builds encoded routes", async () => {
  const request = vi
    .fn()
    .mockImplementation(() => Promise.resolve(new Response("{}")));
  await manageMpaTask(request, runtime, "DELETE", "/t1");
  expect(request.mock.calls[0][1].body).toBeUndefined();
  await manageMpaTask(request, runtime, "POST", "", { clientToken: "id" });
  expect(request.mock.calls[1][1].body).toBe('{"clientToken":"id"}');
  for (const body of ["bad", "null", "[]"]) {
    const req = vi
      .fn()
      .mockImplementation(() => Promise.resolve(new Response(body)));
    await expect(manageMpaTask(req, runtime, "POST", "")).rejects.toThrow(
      "MPA_INVALID_RESPONSE",
    );
    await expect(fetchMpaRuns(req, runtime, "id", 0)).rejects.toThrow(
      "MPA_INVALID_RESPONSE",
    );
  }
  for (const value of [
    { items: [null], total: 1, hasMore: false },
    { items: [], total: -1, hasMore: false },
    { items: [], total: 1, hasMore: true, nextOffset: 0 },
  ])
    await expect(
      fetchMpaRuns(
        vi.fn().mockResolvedValue(new Response(JSON.stringify(value))),
        runtime,
        "id",
        0,
      ),
    ).rejects.toThrow("MPA_INVALID_RESPONSE");
  const result = { items: [], total: 0, hasMore: false, nextOffset: null };
  expect(
    await fetchMpaRuns(
      vi.fn().mockResolvedValue(new Response(JSON.stringify(result))),
      runtime,
      "id",
      0,
    ),
  ).toEqual(result);
});
it("submits every schedule type and preserves delivery metadata on edit", async () => {
  const save = vi.fn();
  await render(
    <MpaTaskEditor
      task={{
        ...task,
        delivery: { channel: "Feishu", targetId: "group", threadId: "thread" },
        jitterSeconds: 12,
        timeoutSeconds: 120,
      }}
      copy={false}
      busy={false}
      error=""
      onClose={() => {}}
      onSave={save}
    />,
  );
  await submit();
  expect(save.mock.calls[0][0].delivery.threadId).toBe("thread");
  for (const type of ["Weekly", "Monthly", "Cron", "Interval", "Once"]) {
    await field("mpa.manage.schedule", type);
    if (type === "Once")
      await field("mpa.manage.localTime", "2030-01-01T09:00");
    await submit();
    expect(save.mock.calls.at(-1)![0].schedule.type).toBe(type);
  }
  await field("mpa.manage.delivery", "Web");
  await submit();
  expect(save.mock.calls.at(-1)![0].delivery).toMatchObject({
    channel: "Web",
    targetId: null,
  });
});
it("validates editor required values, dates, zones, weekdays, intervals and cron", async () => {
  const save = vi.fn();
  await render(
    <MpaTaskEditor
      task={task}
      copy={false}
      busy={false}
      error=""
      onClose={() => {}}
      onSave={save}
    />,
  );
  await field("mpa.manage.timezone", "bad/zone");
  await submit();
  expect(host.textContent).toContain("timezoneInvalid");
  await field("mpa.manage.timezone", "Asia/Shanghai");
  await field("mpa.manage.schedule", "Once");
  await submit();
  expect(host.textContent).toContain("futureTime");
  await field("mpa.manage.schedule", "Interval");
  await field("mpa.manage.interval", "20");
  await submit();
  expect(host.textContent).toContain("intervalInvalid");
  await field("mpa.manage.schedule", "Cron");
  await field("mpa.manage.Cron", "bad");
  await submit();
  expect(host.textContent).toContain("cronFields");
  await field("mpa.manage.schedule", "Weekly");
  await field("mpa.manage.weekdays", "1,1");
  await submit();
  expect(host.textContent).toContain("daysInvalid");
  await field("mpa.manage.weekdays", "0");
  await submit();
  expect(host.textContent).toContain("daysInvalid");
  await field("mpa.manage.schedule", "Monthly");
  await field("mpa.manage.monthDays", "31,32");
  await submit();
  expect(host.textContent).toContain("daysInvalid");
  await field("mpa.manage.monthDays", "1");
  await field("mpa.manage.name", " ");
  await submit();
  expect(host.textContent).toContain("required");
  expect(save).not.toHaveBeenCalled();
});
it("honors editor IME and busy guard", async () => {
  const save = vi.fn();
  await render(
    <MpaTaskEditor
      task={task}
      copy={false}
      busy={false}
      error=""
      onClose={() => {}}
      onSave={save}
    />,
  );
  const input = host.querySelector("input")!;
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    ),
  );
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    ),
  );
  await submit();
  expect(save).not.toHaveBeenCalled();
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    ),
  );
  await submit();
  expect(save).toHaveBeenCalledTimes(1);
  await render(
    <MpaTaskEditor
      task={task}
      copy={false}
      busy
      error=""
      onClose={() => {}}
      onSave={save}
    />,
  );
  await submit();
  expect(save).toHaveBeenCalledTimes(1);
});
it("edits time, recipient and checkbox and preserves interval anchors", async () => {
  const save = vi.fn();
  await render(
    <MpaTaskEditor
      task={{
        ...task,
        schedule: {
          type: "Interval",
          intervalSeconds: 90,
          anchorAt: "2026-01-01T00:00:00Z",
        },
        delivery: { channel: "Web" },
      }}
      copy={false}
      busy={false}
      error="server error"
      onClose={() => {}}
      onSave={save}
    />,
  );
  await submit();
  expect(save.mock.calls[0][0].schedule.anchorAt).toBe("2026-01-01T00:00:00Z");
  await field("mpa.manage.schedule", "Daily");
  await field("mpa.manage.time", "10:30");
  await field("mpa.manage.delivery", "Feishu");
  await field("mpa.manage.target", "group2");
  await act(async () =>
    host.querySelector<HTMLInputElement>('[type="checkbox"]')!.click(),
  );
  await submit();
  expect(save.mock.calls.at(-1)![0]).toMatchObject({
    enabled: false,
    delivery: { channel: "Feishu", targetId: "group2" },
    schedule: { time: "10:30" },
  });
});
it("initializes a one-shot edit and cancels it", async () => {
  const close = vi.fn();
  await render(
    <MpaTaskEditor
      task={{
        ...task,
        schedule: { type: "Once", runAt: "2030-01-01T10:00:00Z" },
      }}
      copy={false}
      busy={false}
      error=""
      onClose={close}
      onSave={() => {}}
    />,
  );
  expect(
    host.querySelector<HTMLInputElement>('[type="datetime-local"]')!.value,
  ).toContain("2030");
  await click("mpa.manage.cancel");
  expect(close).toHaveBeenCalled();
});
it.each([
  { prompt: {} },
  { nextRunAt: {} },
  { lastRunStatus: {} },
  { overview: { executionCount: "bad", successRate: 1 } },
  { overview: { executionCount: 1, successRate: "bad" } },
])("rejects malformed optional fields %j", async (patch) => {
  const data =
    "overview" in patch
      ? { ...page, ...patch }
      : { ...page, items: [{ ...task, ...patch }] };
  await expect(
    fetchMpaCronTasks(
      vi.fn().mockResolvedValue(new Response(JSON.stringify(data))),
      runtime,
      0,
      "",
    ),
  ).rejects.toThrow("MPA_INVALID_RESPONSE");
});
it("renders fallback history values and ignores late history results", async () => {
  let resolve!: (v: unknown) => void;
  let reject!: (e: unknown) => void;
  runs.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
  await render(
    <MpaTaskDetail task={task} runtime={runtime} onClose={() => {}} />,
  );
  await render(
    <MpaTaskDetail
      task={{ ...task, id: "other" }}
      runtime={runtime}
      onClose={() => {}}
    />,
  );
  await act(async () =>
    resolve({
      items: [{ id: "old", status: "Running", scheduledAt: "2026-01-01" }],
      total: 1,
      hasMore: false,
    }),
  );
  expect(host.textContent).not.toContain("mpa.manage.Running");
  runs.mockResolvedValueOnce({
    items: [{ id: "new", status: "Queued", scheduledAt: "bad" }],
    total: 1,
    hasMore: false,
  });
  await click("mpa.refresh");
  expect(host.textContent).toContain("—");
  runs.mockImplementationOnce(() => new Promise((_, r) => (reject = r)));
  await click("mpa.refresh");
  await act(async () => root.unmount());
  await act(async () => reject("old"));
});
it("renders calendar occurrences including grouped intervals and complex cron hints", async () => {
  const at = new Date();
  at.setDate(15);
  at.setHours(12, 0, 0, 0);
  const iso = at.toISOString();
  list.mockResolvedValueOnce({
    ...page,
    items: [
      {
        ...task,
        schedule: { type: "Interval", intervalSeconds: 3600, anchorAt: iso },
      },
      {
        ...task,
        id: "complex",
        name: "Complex",
        schedule: { type: "Cron", cronExpression: "*/15 * * * *" },
        nextRunAt: iso,
      },
    ],
  });
  await render();
  await click("mpa.manage.calendar");
  expect(host.textContent).toContain("mpa.manage.nextOnly");
  const button = host.querySelector<HTMLButtonElement>(".mpa-calendar-task")!;
  await act(async () => button.click());
  expect(runs).toHaveBeenCalled();
});
it.each([
  { timezone: "bad/zone" },
  { timezone: 3 },
  { runAt: "invalid" },
  { runAt: 3 },
  { weekdays: {} },
  { monthDays: [1, "2"] },
])("rejects unsafe calendar schedule %j", async (patch) => {
  await expect(
    fetchMpaCronTasks(
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...page,
            items: [{ ...task, schedule: { ...task.schedule, ...patch } }],
          }),
        ),
      ),
      runtime,
      0,
      "",
    ),
  ).rejects.toThrow("MPA_INVALID_RESPONSE");
});
it("rejects unsafe optional agent fields", async () => {
  await expect(
    fetchMpaCronTasks(
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ ...page, items: [{ ...task, agentId: {} }] }),
          ),
        ),
      runtime,
      0,
      "",
    ),
  ).rejects.toThrow("MPA_INVALID_RESPONSE");
});
it("accepts valid calendar arrays and zoned one-shot values", async () => {
  const data = {
    ...page,
    items: [
      {
        ...task,
        schedule: {
          type: "Once",
          runAt: "2030-01-01T00:00:00Z",
          weekdays: [1],
          monthDays: [2],
        },
      },
    ],
  };
  expect(
    await fetchMpaCronTasks(
      vi.fn().mockResolvedValue(new Response(JSON.stringify(data))),
      runtime,
      0,
      "",
    ),
  ).toEqual(data);
});
it.each([
  { errorMessage: {} },
  { sessionId: [] },
  { startedAt: 3 },
  { durationMs: -1 },
  { durationMs: "bad" },
])("rejects unsafe run detail fields %j", async (patch) => {
  await expect(
    fetchMpaRuns(
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              items: [
                {
                  id: "one",
                  status: "Failed",
                  scheduledAt: "2026-09-15",
                  ...patch,
                },
              ],
              total: 1,
              hasMore: false,
            }),
          ),
        ),
      runtime,
      "one",
      0,
    ),
  ).rejects.toThrow("MPA_INVALID_RESPONSE");
});
it("accepts a typed execution history response", async () => {
  const data = {
    items: [
      {
        id: "one",
        status: "Succeeded",
        scheduledAt: "2026-09-15",
        startedAt: null,
        durationMs: 50,
        sessionId: "s1",
        errorMessage: null,
      },
    ],
    total: 1,
    hasMore: false,
    nextOffset: null,
  };
  expect(
    await fetchMpaRuns(
      vi.fn().mockResolvedValue(new Response(JSON.stringify(data))),
      runtime,
      "one",
      0,
    ),
  ).toEqual(data);
});
