// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MpaChannelsAutomation } from "../src/automations/mpa-channels/MpaChannelsAutomation";
import {
  getRuntimes,
  channelRequest,
  ChannelApiError,
  RuntimeListError,
  type CloudRuntime,
  type RuntimePage,
  type StudioRole,
} from "../src/adk/client";

vi.mock("../src/adk/client", () => ({
  getRuntimes: vi.fn(),
  channelRequest: vi.fn(),
  ChannelApiError: class extends Error {
    constructor(public status: number) {
      super(String(status));
    }
  },
  RuntimeListError: class extends Error {
    constructor(
      message: string,
      public status: number,
    ) {
      super(message);
    }
  },
}));
const translate = (key: string, options?: Record<string, string>) =>
  key === "mpaChannels.optionMetadata"
    ? `${options?.creator} | ${options?.createdAt}`
    : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { resolvedLanguage: "en-US", language: "en-US" },
  }),
}));
vi.mock("@openai/apps-sdk-ui/components/Button", () => ({
  Button: ({
    color: _c,
    variant: _v,
    size: _s,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    color?: string;
    variant?: string;
    size?: string;
  }) => <button {...props} />,
}));
const sdk = vi.hoisted(() => ({ open: vi.fn(), destroy: vi.fn() }));
vi.mock("@wecom/wecom-aibot-sdk/dist/wecom-aibot-sdk.esm.js", () => ({
  default: { destroy: vi.fn() },
  WecomAIBotSDK: class {
    openBotInfoAuthWindow = sdk.open;
    destroy = sdk.destroy;
  },
}));

let root: Root;
let host: HTMLDivElement;
const list = vi.mocked(getRuntimes);
const request = vi.mocked(channelRequest);
const back = vi.fn();
const runtime = (
  runtimeId: string,
  region = "cn-beijing",
  extra: Partial<CloudRuntime> = {},
): CloudRuntime => ({
  runtimeId,
  region,
  name: runtimeId,
  status: "Ready",
  author: "",
  agentCategory: "mpa",
  isMine: true,
  canDelete: true,
  ...extra,
});
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  list.mockReset();
  request.mockReset();
  back.mockReset();
  sdk.open.mockReset();
  sdk.destroy.mockReset();
  list.mockResolvedValue({
    runtimes: [runtime("alpha"), runtime("beta", "cn-shanghai")],
    nextToken: "",
  });
  request.mockImplementation(async (_ep, path) => {
    if (path === "/capabilities")
      return {
        serverSideBinding: true,
        bindingReady: true,
        channels: ["feishu", "wecom", "dingtalk"],
        credentialBindingChannels: ["feishu", "wecom", "dingtalk"],
      };
    if (path.endsWith("/diagnostics"))
      return {
        configured: false,
        gatewayConfigured: true,
        routeConfigured: true,
        missingConfiguration: [],
        deliveryHealth: "not_observed",
      };
    if (path.startsWith("/chat-permissions")) return { permissions: [] };
    return {
      id: "pending",
      status: "PENDING",
      qrCodeImage: "https://example.com/qr",
      loginUrl: "https://example.com/auth",
      pollAfterSeconds: 1,
    };
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
async function render(
  role: StudioRole = "admin",
  scope: "mine" | "all" = "mine",
) {
  await act(async () =>
    root.render(
      <MpaChannelsAutomation role={role} runtimeScope={scope} onBack={back} />,
    ),
  );
}
async function click(label: string) {
  const element = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (b) => b.textContent === label || b.getAttribute("aria-label") === label,
  );
  expect(element, label).toBeDefined();
  await act(async () => element!.click());
}
async function select(name: string) {
  await click("mpaChannels.selectAgent");
  const option = [
    ...host.querySelectorAll<HTMLButtonElement>('[role="option"]'),
  ].find((b) => b.textContent?.startsWith(name));
  expect(option).toBeDefined();
  await act(async () => option!.click());
}
async function search(value: string) {
  const input = host.querySelector<HTMLInputElement>('input[type="search"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

it("lists authorized MPA runtimes and only mounts channels after explicit selection", async () => {
  await render();
  expect(list).toHaveBeenCalledWith(
    expect.objectContaining({
      agentCategory: "mpa",
      scope: "mine",
      region: "all",
      signal: expect.any(AbortSignal),
    }),
  );
  expect(request).not.toHaveBeenCalled();
  await select("beta");
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({ runtimeId: "beta", region: "cn-shanghai" }),
    "/capabilities",
    expect.anything(),
  );
  expect(host.querySelectorAll('[role="tab"]')).toHaveLength(3);
  await click("backToAutomations");
  expect(back).toHaveBeenCalledOnce();
});

it("shows the name once with description, compact creator/time and Runtime context", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-15T22:30:00Z"));
  list.mockResolvedValueOnce({
    runtimes: [
      runtime("alpha", "cn-beijing", {
        name: "Project helper",
        description: "Answers project questions",
        author: "Example creator",
        createdAt: "2026-09-15T08:30:00Z",
      }),
    ],
    nextToken: "",
  });
  await render();
  await click("mpaChannels.selectAgent");
  const option = host.querySelector<HTMLButtonElement>('[role="option"]')!;
  expect(option.textContent?.match(/Project helper/g)).toHaveLength(1);
  expect(option.textContent).toContain("Answers project questions");
  expect(option.textContent).toContain("Example creator");
  expect(option.textContent).toContain("Example creator | 14 hours ago");
  expect(option.title).toContain("Answers project questions");
  expect(option.title).toContain("Example creator");
  expect(option.textContent).toContain("cn-beijing · alpha");
});

it("uses placeholders for empty metadata and invalid creation timestamps", async () => {
  list.mockResolvedValueOnce({
    runtimes: [
      runtime("alpha", "cn-beijing", {
        description: " ",
        author: " ",
        createdAt: "not-a-date",
      }),
    ],
    nextToken: "",
  });
  await render();
  await click("mpaChannels.selectAgent");
  const option = host.querySelector('[role="option"]')!;
  expect(option.textContent).toContain("mpaChannels.noDescription");
  expect(option.textContent).toContain("mpaChannels.unknownCreator");
  expect(option.textContent).toContain("—");
  expect(option.textContent).not.toContain("Invalid Date");
});

it.each<StudioRole>(["user", "developer"])(
  "blocks %s before fetching any data",
  async (role) => {
    await render(role);
    expect(host.textContent).toContain("mpaChannels.unauthorized");
    expect(list).not.toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
  },
);

it("supports super admins, pagination, same IDs in different regions and legacy category omission", async () => {
  list.mockResolvedValueOnce({
    runtimes: [
      runtime("same"),
      runtime("general", "cn-beijing", { agentCategory: "general" }),
    ],
    nextToken: "page2",
  });
  list.mockResolvedValueOnce({
    runtimes: [runtime("same", "cn-shanghai", { agentCategory: undefined })],
    nextToken: "",
  });
  await render("super_admin", "all");
  await click("mpaChannels.loadMore");
  expect(list.mock.calls[1][0]).toMatchObject({
    nextToken: "page2",
    scope: "all",
    agentCategory: "mpa",
  });
  await click("mpaChannels.selectAgent");
  expect(host.querySelectorAll('[role="option"]')).toHaveLength(2);
  expect(host.textContent).not.toContain("general");
  await search("cn-shanghai");
  expect(host.querySelectorAll('[role="option"]')).toHaveLength(1);
  await act(async () =>
    host.querySelector<HTMLButtonElement>('[role="option"]')!.click(),
  );
  expect(request.mock.calls[0][0]).toMatchObject({
    runtimeId: "same",
    region: "cn-shanghai",
  });
});

it("separates empty, failed and forbidden lists and allows retry", async () => {
  list.mockRejectedValueOnce(new RuntimeListError("failed", 500));
  await render();
  expect(host.textContent).toContain("mpaChannels.loadFailed");
  expect(host.textContent).not.toContain("mpaChannels.empty");
  list.mockResolvedValueOnce({ runtimes: [], nextToken: "" });
  await click("mpaChannels.retry");
  expect(host.textContent).toContain("mpaChannels.empty");
  list.mockRejectedValueOnce(new RuntimeListError("forbidden", 403));
  await click("mpaChannels.refresh");
  expect(host.textContent).toContain("mpaChannels.unauthorized");
  expect(request).not.toHaveBeenCalled();
});

it("keeps current options and channels when loading a later page fails", async () => {
  list.mockResolvedValueOnce({
    runtimes: [runtime("alpha")],
    nextToken: "page2",
  });
  await render();
  await select("alpha");
  list.mockRejectedValueOnce(new Error("offline"));
  await click("mpaChannels.loadMore");
  expect(host.querySelectorAll('[role="tab"]')).toHaveLength(3);
  list.mockResolvedValueOnce({ runtimes: [runtime("beta")], nextToken: "" });
  await click("mpaChannels.retry");
  expect(list.mock.calls[2][0]?.nextToken).toBe("page2");
  await select("beta");
});

it("aborts list requests and ignores late responses after scope changes", async () => {
  let resolve!: (page: RuntimePage) => void;
  list.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  await render();
  expect(host.textContent).toContain("mpaChannels.loading");
  const signal = list.mock.calls[0][0]!.signal!;
  await render("admin", "all");
  expect(signal.aborted).toBe(true);
  await act(async () =>
    resolve({ runtimes: [runtime("stale")], nextToken: "" }),
  );
  await click("mpaChannels.selectAgent");
  expect(host.textContent).not.toContain("stale");
});

it("cancels pairing and resets modes when choosing another runtime", async () => {
  vi.useFakeTimers();
  await render();
  await select("alpha");
  await click("channels.bind");
  expect(host.querySelector(".runtime-channels-qr")).not.toBeNull();
  await select("beta");
  expect(host.querySelector(".runtime-channels-qr")).toBeNull();
  request.mockClear();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(request).not.toHaveBeenCalled();
  await act(async () =>
    host.querySelector<HTMLInputElement>('input[value="manual"]')!.click(),
  );
  await select("alpha");
  expect(
    host.querySelector<HTMLInputElement>('input[value="quick"]')?.checked,
  ).toBe(true);
});

it("ignores late capability responses from the old runtime", async () => {
  let resolve!: (value: unknown) => void;
  request.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  await render();
  await select("alpha");
  const signal = request.mock.calls[0][2]!.signal!;
  await select("beta");
  expect(signal.aborted).toBe(true);
  request.mockClear();
  await act(async () =>
    resolve({
      serverSideBinding: true,
      bindingReady: true,
      channels: ["feishu"],
    }),
  );
  expect(request).not.toHaveBeenCalled();
});

it("closes SDK authorization on runtime switch and discards late credentials", async () => {
  let resolve!: (value: unknown) => void;
  sdk.open.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await render();
  await select("alpha");
  await click("channels.provider_wecom");
  await click("channels.bind");
  await select("beta");
  await act(async () =>
    resolve({ botid: "discarded-bot", secret: "test-only-value" }),
  );
  expect(sdk.destroy).toHaveBeenCalled();
  expect(
    request.mock.calls.some(([, path]) => path === "/wecom/bindings"),
  ).toBe(false);
});

it("removes management state immediately when administrator access is lost", async () => {
  await render();
  await select("alpha");
  list.mockClear();
  request.mockClear();
  await render("user");
  expect(host.querySelector('[role="tab"]')).toBeNull();
  expect(list).not.toHaveBeenCalled();
  expect(request).not.toHaveBeenCalled();
});

it("keeps unsupported Runtime errors in the selected panel", async () => {
  request.mockRejectedValueOnce(new ChannelApiError(404));
  await render();
  await select("alpha");
  expect(host.textContent).toContain("channels.unsupported");
  await select("beta");
  expect(host.textContent).not.toContain("channels.unsupported");
});

it("searches without IME Enter selecting an agent and restores focus on Escape", async () => {
  await render();
  await click("mpaChannels.selectAgent");
  await search("missing");
  expect(host.textContent).toContain("mpaChannels.noMatches");
  const input = host.querySelector<HTMLInputElement>('input[type="search"]')!;
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        isComposing: true,
        bubbles: true,
      }),
    ),
  );
  expect(request).not.toHaveBeenCalled();
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
    ),
  );
  expect(document.activeElement?.getAttribute("aria-label")).toBe(
    "mpaChannels.selectAgent",
  );
});
