// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MpaTaskEditor } from "../src/cronjobs/MpaTaskEditor";
import { channelRequest } from "../src/adk/client";
vi.mock("../src/adk/client", () => ({
  channelRequest: vi.fn(),
  ChannelApiError: class extends Error {
    constructor(public status: number) {
      super(String(status));
    }
  },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../src/ui/SandboxControls", () => ({
  DialogShell: ({ children }: { children: React.ReactNode }) => (
    <div role="dialog">{children}</div>
  ),
}));
vi.mock("../src/components/primitives/Select/Select", () => ({
  Select: ({ options, ...props }: any) => (
    <select {...props}>
      {options.map((o: any) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("../src/ui/DeploymentSelect", () => ({
  DeploymentSelect: ({ ariaLabel, value, options, onChange }: any) => (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o: any) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
const runtime = { runtimeId: "r-bots", region: "cn-beijing", name: "Bots" };
const task = {
  id: "task-a",
  name: "Daily",
  enabled: true,
  prompt: "Report",
  schedule: { type: "Daily", time: "09:00", timezone: "Asia/Shanghai" },
  delivery: {
    channel: "Feishu",
    targetId: "oc_same",
    appId: "bot-b",
    receiveIdType: "chat_id",
    bestEffort: true,
    threadId: "omt_thread",
    replyMessageId: "om_reply",
  },
};
const request = vi.mocked(channelRequest);
const save = vi.fn();
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  save.mockReset();
  request.mockReset();
  request.mockImplementation(async (_ep, path) =>
    path === "/capabilities"
      ? { multiBotChannels: ["feishu"] }
      : {
          channels: [
            { channel: "feishu", appId: "bot-a", appName: "A", enabled: true },
            { channel: "feishu", appId: "bot-b", appName: "B", enabled: true },
          ],
        },
  );
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
async function render(value = task) {
  await act(async () =>
    root.render(
      <MpaTaskEditor
        runtime={runtime}
        task={value}
        copy={false}
        busy={false}
        error=""
        onClose={() => {}}
        onSave={save}
      />,
    ),
  );
}
async function submit() {
  await act(async () =>
    host
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
}
it("selects the persisted delivery bot and preserves thread metadata", async () => {
  await render();
  expect(
    host.querySelector<HTMLSelectElement>(
      'select[aria-label="mpa.manage.botAccount"]',
    )?.value,
  ).toBe("bot-b");
  await submit();
  expect(save.mock.calls[0][0].delivery).toEqual(task.delivery);
});
it("keeps appId when editing the target but clears target-specific thread fields", async () => {
  await render();
  const input = host.querySelector<HTMLInputElement>('input[maxlength="512"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, "oc_other");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await submit();
  expect(save.mock.calls[0][0].delivery).toMatchObject({
    appId: "bot-b",
    targetId: "oc_other",
  });
  expect(save.mock.calls[0][0].delivery.threadId).toBeUndefined();
});
it("requires an explicit bot for an ambiguous old task", async () => {
  await render({
    ...task,
    delivery: { ...task.delivery, appId: undefined },
  } as typeof task);
  await submit();
  expect(save).not.toHaveBeenCalled();
  expect(host.textContent).toContain("mpa.manage.selectBot");
});
it("removes appId when switching to Web delivery", async () => {
  await render();
  const select = host.querySelector<HTMLSelectElement>(
    'select[aria-label="mpa.manage.delivery"]',
  )!;
  await act(async () => {
    select.value = "Web";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await submit();
  expect(save.mock.calls[0][0].delivery).not.toHaveProperty("appId");
});
it("shows account read errors and prevents Feishu submission", async () => {
  request.mockRejectedValue(new Error("private upstream failure"));
  await render();
  await submit();
  expect(save).not.toHaveBeenCalled();
  expect(host.textContent).toContain("mpa.manage.botsFailed");
  expect(host.textContent).not.toContain("private upstream failure");
});

async function choose(label: string, value: string) {
  const select = host.querySelector<HTMLSelectElement>(
    `select[aria-label="${label}"]`,
  )!;
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
it("uses the chosen account for a copied task and resets thread metadata when changing bots", async () => {
  await act(async () =>
    root.render(
      <MpaTaskEditor
        runtime={runtime}
        task={task}
        copy
        busy={false}
        error=""
        onClose={() => {}}
        onSave={save}
      />,
    ),
  );
  await choose("mpa.manage.botAccount", "bot-a");
  await submit();
  expect(save.mock.calls[0][0].delivery).toMatchObject({
    appId: "bot-a",
    targetId: "oc_same",
  });
  expect(save.mock.calls[0][0].delivery).not.toHaveProperty("threadId");
});
it("selects a single enabled bot for a legacy task", async () => {
  request.mockImplementation(async (_ep, path) =>
    path === "/capabilities"
      ? { multiBotChannels: ["feishu"] }
      : { channels: [{ channel: "feishu", appId: "bot-a", enabled: true }] },
  );
  await render({
    ...task,
    delivery: { ...task.delivery, appId: undefined },
  } as typeof task);
  await submit();
  expect(save.mock.calls[0][0].delivery.appId).toBe("bot-a");
});
it.each([[], [{ channel: "feishu", appId: "bot-b", enabled: false }]])(
  "blocks missing or disabled delivery bots: %j",
  async (channels) => {
    request.mockImplementation(async (_ep, path) =>
      path === "/capabilities"
        ? { multiBotChannels: ["feishu"] }
        : { channels },
    );
    await render();
    await submit();
    expect(save).not.toHaveBeenCalled();
  },
);
it("does not auto-select a single disabled account", async () => {
  request.mockImplementation(async (_ep, path) =>
    path === "/capabilities"
      ? { multiBotChannels: ["feishu"] }
      : { channels: [{ channel: "feishu", appId: "bot-a", enabled: false }] },
  );
  await render({
    ...task,
    delivery: { ...task.delivery, appId: undefined },
  } as typeof task);
  expect(
    host.querySelector<HTMLSelectElement>(
      'select[aria-label="mpa.manage.botAccount"]',
    )?.value,
  ).toBe("");
  await submit();
  expect(save).not.toHaveBeenCalled();
});
it("retains legacy Feishu editing when multi-bot capability is absent", async () => {
  request.mockResolvedValue({ serverSideBinding: true });
  await render();
  await submit();
  expect(save.mock.calls[0][0].delivery).toEqual(task.delivery);
  expect(request).toHaveBeenCalledTimes(1);
});
it("retains legacy editing if the capability endpoint is unsupported", async () => {
  const { ChannelApiError } = await import("../src/adk/client");
  request.mockRejectedValue(new ChannelApiError(404));
  await render();
  await submit();
  expect(save).toHaveBeenCalled();
});
it("reports denied bot listing and permits a clean retry", async () => {
  const { ChannelApiError } = await import("../src/adk/client");
  request.mockRejectedValueOnce(new ChannelApiError(403));
  await render();
  expect(host.textContent).toContain("mpa.manage.botsUnauthorized");
  const retry = [...host.querySelectorAll("button")].find(
    (b) => b.textContent === "mpa.manage.retryBots",
  )!;
  await act(async () => retry.click());
  await submit();
  expect(save).toHaveBeenCalled();
});
it("cancels and ignores late capability responses after switching to Web", async () => {
  let resolve!: (value: unknown) => void;
  let signal!: AbortSignal;
  request.mockImplementation((_ep, _path, init) => {
    signal = init!.signal as AbortSignal;
    return new Promise((done) => {
      resolve = done;
    });
  });
  await render();
  await submit();
  expect(save).not.toHaveBeenCalled();
  await choose("mpa.manage.delivery", "Web");
  expect(signal.aborted).toBe(true);
  await act(async () => resolve({ multiBotChannels: ["feishu"] }));
  await submit();
  expect(save.mock.calls[0][0].delivery.channel).toBe("Web");
  expect(request).toHaveBeenCalledTimes(1);
});
it("ignores late list results and errors after the editor is closed", async () => {
  let resolve!: (value: unknown) => void;
  let signal!: AbortSignal;
  request.mockImplementation(async (_ep, path, init) =>
    path === "/capabilities"
      ? { multiBotChannels: ["feishu"] }
      : new Promise((done) => {
          signal = init!.signal as AbortSignal;
          resolve = done;
        }),
  );
  await render();
  await act(async () => root.render(null));
  expect(signal.aborted).toBe(true);
  await act(async () =>
    resolve({
      channels: [{ channel: "feishu", appId: "bot-a", enabled: true }],
    }),
  );
  expect(save).not.toHaveBeenCalled();
});
it("cancels a capability failure after unmount without showing it", async () => {
  let reject!: (reason: unknown) => void;
  request.mockImplementation(
    () =>
      new Promise((_done, fail) => {
        reject = fail;
      }),
  );
  await render();
  await act(async () => root.render(null));
  await act(async () => reject(new Error("late failure")));
  expect(host.textContent).toBe("");
});
