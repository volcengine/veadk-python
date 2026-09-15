// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RuntimeChannels } from "../src/ui/RuntimeChannels";
import { channelRequest, ChannelApiError } from "../src/adk/client";
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
vi.mock("@openai/apps-sdk-ui/components/Button", () => ({
  Button: ({ color: _c, variant: _v, size: _s, children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}));
vi.mock("../src/components/primitives/Select/Select", () => ({
  Select: ({ options, ...props }: any) => (
    <select {...props}>
      {options.map((o: any) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
const wecomSdk = vi.hoisted(() => ({ open: vi.fn(), destroy: vi.fn() }));
vi.mock("@wecom/wecom-aibot-sdk/dist/wecom-aibot-sdk.esm.js", () => ({
  default: { destroy: vi.fn() },
  WecomAIBotSDK: class {
    openBotInfoAuthWindow = wecomSdk.open;
    destroy = wecomSdk.destroy;
  },
}));
let root: Root;
let host: HTMLDivElement;
const request = vi.mocked(channelRequest);
const pending = {
  id: "binding-1",
  status: "PENDING",
  loginUrl: "https://example.com/authorize",
  qrCodeImage: "https://example.com/qr",
  expiresAt: "2026-09-15T00:00:00Z",
  pollAfterSeconds: 1,
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("localStorage", {
    setItem: vi.fn(),
    getItem: vi.fn(),
    removeItem: vi.fn(),
  });
  sessionStorage.clear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  request.mockReset();
  wecomSdk.open.mockReset();
  wecomSdk.destroy.mockReset();
  request.mockImplementation(async (_ep, path) => {
    if (path === "/capabilities")
      return {
        serverSideBinding: true,
        bindingReady: true,
        credentialBindingChannels: ["wecom", "dingtalk", "feishu"],
        channels: ["feishu", "wecom", "dingtalk"],
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
    if (path === "/feishu/bindings" || path === "/dingtalk/bindings")
      return pending;
    return { ...pending, status: "BOUND" };
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
const render = async () => {
  await act(async () =>
    root.render(<RuntimeChannels runtimeId="runtime-1" region="cn-beijing" />),
  );
};
async function click(label: string) {
  const button = [...host.querySelectorAll("button")].find(
    (b) => b.textContent === label,
  );
  expect(button).toBeDefined();
  await act(async () => button!.click());
}

it("completes server-side binding and stops polling at BOUND", async () => {
  vi.useFakeTimers();
  await render();
  await click("channels.bind");
  expect(host.querySelector(".runtime-channels-qr")).not.toBeNull();
  expect(host.textContent).not.toContain("channels.status_PENDING");
  expect(host.textContent).not.toContain("channels.openQr");
  expect(
    sessionStorage.getItem("mpa-feishu-binding:cn-beijing:runtime-1"),
  ).toBeNull();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(host.textContent).toContain("channels.status_BOUND");
  const calls = request.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(request.mock.calls.length).toBe(calls);
});
it("cancels an in-flight binding request when leaving", async () => {
  await render();
  let signal: AbortSignal | undefined;
  request.mockImplementation(async (_ep, _path, init) => {
    signal = init?.signal as AbortSignal;
    return new Promise(() => {});
  });
  await click("channels.bind");
  await act(async () => root.render(null));
  expect(signal?.aborted).toBe(true);
});
it("shows unsupported images and allows retry after an error", async () => {
  request.mockRejectedValueOnce(new ChannelApiError(404));
  await render();
  expect(host.textContent).toContain("channels.unsupported");
  expect(
    [...host.querySelectorAll("button")].find(
      (b) => b.textContent === "channels.bind",
    ),
  ).toBeUndefined();
  await click("common.retry");
  expect(host.textContent).toContain("channels.bind");
});
it("keeps the group form after a failed save", async () => {
  await render();
  const input = host.querySelector<HTMLInputElement>(
    ".runtime-channels-permissions input",
  )!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, "group-1");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  request.mockRejectedValueOnce(new ChannelApiError(502));
  await act(async () =>
    host
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(input.value).toBe("group-1");
  expect(host.textContent).toContain("channels.requestFailed");
});

it("binds DingTalk through the durable provider endpoint", async () => {
  vi.useFakeTimers();
  await render();
  await click("channels.provider_dingtalk");
  await click("channels.bind");
  expect(
    request.mock.calls.some(([, path]) => path === "/dingtalk/bindings"),
  ).toBe(true);
  expect(
    sessionStorage.getItem("mpa-dingtalk-binding:cn-beijing:runtime-1"),
  ).toBeNull();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(host.textContent).toContain("channels.status_BOUND");
});
it("binds WeCom using a password form without persisting the secret", async () => {
  await render();
  await click("channels.provider_wecom");
  await selectMethod("manual");
  const inputs = [
    host.querySelector<HTMLInputElement>('input[name="botId"]')!,
    host.querySelector<HTMLInputElement>('input[name="secret"]')!,
  ];
  expect(inputs[1]?.type).toBe("password");
  for (const [i, value] of ["test-bot", "test-secret"].entries()) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )!.set!.call(inputs[i], value);
      inputs[i].dispatchEvent(new Event("input", { bubbles: true }));
    });
  }
  await act(async () =>
    host
      .querySelector("form[data-channel-binding]")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  const call = request.mock.calls.find(
    ([, path]) => path === "/wecom/bindings",
  );
  expect(JSON.parse(call![2]!.body as string)).toEqual({
    botId: "test-bot",
    secret: "test-secret",
  });
  expect(inputs[1].value).toBe("");
  expect(JSON.stringify(sessionStorage)).not.toContain("test-secret");
  expect(localStorage.setItem).not.toHaveBeenCalled();
});
it("rejects unsupported providers on older Runtime images", async () => {
  const original = request.getMockImplementation()!;
  request.mockImplementation(async (ep, path, init) =>
    path === "/capabilities"
      ? { serverSideBinding: true, bindingReady: true, channels: ["feishu"] }
      : original(ep, path, init),
  );
  await render();
  await click("channels.provider_dingtalk");
  expect(host.textContent).toContain("channels.unsupported");
  expect(
    request.mock.calls.some(([, path]) => path === "/dingtalk/diagnostics"),
  ).toBe(false);
});
it("moves provider focus with arrow keys and cancels polling when switching", async () => {
  vi.useFakeTimers();
  await render();
  await click("channels.bind");
  const tab = host.querySelector<HTMLButtonElement>(
    '[role="tab"][aria-selected="true"]',
  )!;
  expect(tab).not.toBeNull();
  await act(async () => {
    tab.focus();
    tab.dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
    );
  });
  expect(document.activeElement?.textContent).toBe("channels.provider_wecom");
  const count = request.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(request.mock.calls.length).toBe(count);
});
it("keeps configuration and unobserved delivery distinct", async () => {
  await render();
  expect(host.querySelectorAll(".runtime-channels-status-card")).toHaveLength(
    3,
  );
  expect(host.textContent).toContain("channels.delivery_not_observed");
  expect(host.textContent).not.toContain("channels.delivery_delivered");
});

it("prevents Enter during IME composition including Safari key code", async () => {
  await render();
  const input = host.querySelector<HTMLInputElement>(
    ".runtime-channels-permissions input",
  )!;
  for (const options of [{ isComposing: true }, { keyCode: 229 }]) {
    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
      ...options,
    });
    await act(async () => {
      input.dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(true);
  }
});

it.each(["dingtalk", "wecom"])(
  "does not expose or load group allowlists for %s",
  async (provider) => {
    await render();
    request.mockClear();
    await click(`channels.provider_${provider}`);
    expect(host.textContent).not.toContain("channels.groupsTitle");
    expect(
      request.mock.calls.some(([, path]) =>
        path.startsWith("/chat-permissions"),
      ),
    ).toBe(false);
  },
);

it.each(["dingtalk", "wecom"])(
  "unbinds only the selected %s bot",
  async (provider) => {
    const original = request.getMockImplementation()!;
    let configured = true;
    request.mockImplementation(async (ep, path, init) => {
      if (path === `/${provider}/diagnostics`)
        return {
          configured,
          appId: "bot-1",
          missingConfiguration: [],
          deliveryHealth: "not_observed",
        };
      if (init?.method === "DELETE") {
        configured = false;
        return { success: true };
      }
      return original(ep, path, init);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await render();
    await click(`channels.provider_${provider}`);
    await click("channels.unbind");
    expect(
      request.mock.calls.some(
        ([, path, init]) =>
          path === `?channel=${provider}&appId=bot-1` &&
          init?.method === "DELETE",
      ),
    ).toBe(true);
    expect(host.textContent).toContain("channels.notBound");
    vi.restoreAllMocks();
  },
);

async function fillCredential(name: string, value: string) {
  const input = host.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
  expect(input).toBeTruthy();
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
it("binds WeCom through SDK popup without exposing or persisting returned secrets", async () => {
  wecomSdk.open.mockResolvedValue({ botid: "sdk-bot", secret: "sdk-secret" });
  await render();
  await click("channels.provider_wecom");
  await click("channels.bind");
  expect(wecomSdk.open).toHaveBeenCalledWith(
    expect.objectContaining({ source: "mpa-agent", debug: false }),
  );
  const call = request.mock.calls.find(
    ([, path]) => path === "/wecom/bindings",
  );
  expect(JSON.parse(call![2]!.body as string)).toEqual({
    botId: "sdk-bot",
    secret: "sdk-secret",
  });
  expect(host.textContent).not.toContain("sdk-secret");
  expect(JSON.stringify(sessionStorage)).not.toContain("sdk-secret");
  expect(localStorage.setItem).not.toHaveBeenCalled();
  expect(wecomSdk.destroy).toHaveBeenCalled();
});
it("ignores a late SDK authorization after switching providers", async () => {
  let resolve!: (value: unknown) => void;
  wecomSdk.open.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await render();
  await click("channels.provider_wecom");
  await click("channels.bind");
  await click("channels.provider_dingtalk");
  await act(async () => resolve({ botid: "late-bot", secret: "late-secret" }));
  expect(
    request.mock.calls.some(([, path]) => path === "/wecom/bindings"),
  ).toBe(false);
  expect(wecomSdk.destroy).toHaveBeenCalled();
});
it("sanitizes a blocked popup and permits retry", async () => {
  wecomSdk.open.mockRejectedValue({
    code: "WINDOW_BLOCKED",
    message: "secret-provider-error",
  });
  await render();
  await click("channels.provider_wecom");
  await click("channels.bind");
  expect(host.textContent).toContain("channels.wecomPopupBlocked");
  expect(host.textContent).not.toContain("secret-provider-error");
  wecomSdk.open.mockResolvedValue({
    botid: "retry-bot",
    secret: "retry-secret",
  });
  await click("channels.bind");
  expect(
    request.mock.calls.filter(([, path]) => path === "/wecom/bindings"),
  ).toHaveLength(1);
});
it("cancels popup waiting and rejects malformed results without registering", async () => {
  wecomSdk.open.mockReturnValue(new Promise(() => {}));
  await render();
  await click("channels.provider_wecom");
  await click("channels.bind");
  await click("channels.cancelAuthorization");
  wecomSdk.open.mockResolvedValue({ botid: "bot" });
  await click("channels.bind");
  expect(host.textContent).toContain("channels.wecomInvalidResult");
  expect(
    request.mock.calls.some(([, path]) => path === "/wecom/bindings"),
  ).toBe(false);
});
it("times out popup waiting and releases the SDK", async () => {
  vi.useFakeTimers();
  wecomSdk.open.mockReturnValue(new Promise(() => {}));
  await render();
  await click("channels.provider_wecom");
  await click("channels.bind");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300000);
  });
  expect(host.textContent).toContain("channels.wecomAuthTimeout");
  expect(wecomSdk.destroy).toHaveBeenCalled();
});
it("offers manual DingTalk credentials separately from QR, preserving form on failure", async () => {
  await render();
  await click("channels.provider_dingtalk");
  await selectMethod("manual");
  expect(host.querySelector(".runtime-channels-qr")).toBeNull();
  await fillCredential("clientId", " test-client ");
  await fillCredential("secret", "test-secret");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')!.type,
  ).toBe("password");
  request.mockRejectedValueOnce(new ChannelApiError(502));
  await click("channels.bindCredentials");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')!.value,
  ).toBe("test-secret");
  await click("channels.bindCredentials");
  const calls = request.mock.calls.filter(
    ([, path]) => path === "/dingtalk/bindings/manual",
  );
  expect(calls).toHaveLength(2);
  expect(JSON.parse(calls[1][2]!.body as string)).toEqual({
    clientId: "test-client",
    clientSecret: "test-secret",
  });
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')!.value,
  ).toBe("");
});

it.each(["feishu", "dingtalk"])(
  "regenerates a QR for a configured %s bot without disconnecting it",
  async (provider) => {
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (ep, path, init) =>
      path === `/${provider}/diagnostics`
        ? {
            configured: true,
            appId: "existing-bot",
            missingConfiguration: [],
            deliveryHealth: "not_observed",
          }
        : original(ep, path, init),
    );
    await render();
    if (provider !== "feishu") await click(`channels.provider_${provider}`);
    const regenerate = [...host.querySelectorAll("button")].find(
      (b) => b.textContent === "channels.newQr",
    )!;
    expect(regenerate).toBeDefined();
    expect(regenerate.disabled).toBe(false);
    await click("channels.newQr");
    expect(host.textContent).toContain("channels.pairingTitle");
    if (provider === "feishu")
      expect(host.textContent).toContain("channels.feishuPairingDescription");
    expect(host.textContent).toContain("channels.connected");
    expect(host.querySelector(".runtime-channels-qr")).not.toBeNull();
    expect(host.textContent).not.toContain("channels.status_PENDING");
    expect(host.textContent).not.toContain("channels.openQr");
    expect(
      request.mock.calls.some(
        ([, path, init]) =>
          path === `/${provider}/bindings` && init?.method === "POST",
      ),
    ).toBe(true);
    expect(
      request.mock.calls.some(([, , init]) => init?.method === "DELETE"),
    ).toBe(false);
    expect(regenerate.disabled).toBe(true);
  },
);

it("keeps the configured bot when regenerating a QR fails", async () => {
  const original = request.getMockImplementation()!;
  request.mockImplementation(async (ep, path, init) => {
    if (path === "/feishu/diagnostics")
      return {
        configured: true,
        appId: "existing-bot",
        missingConfiguration: [],
        deliveryHealth: "not_observed",
      };
    if (path === "/feishu/bindings") throw new ChannelApiError(502);
    return original(ep, path, init);
  });
  await render();
  await click("channels.newQr");
  expect(host.textContent).toContain("channels.connected");
  expect(host.textContent).toContain("channels.requestFailed");
  expect(
    request.mock.calls.some(([, , init]) => init?.method === "DELETE"),
  ).toBe(false);
  expect(
    [...host.querySelectorAll("button")].find(
      (b) => b.textContent === "channels.newQr",
    )?.disabled,
  ).toBe(false);
});

it("blocks DingTalk IME Enter and duplicate manual submissions", async () => {
  await render();
  await click("channels.provider_dingtalk");
  await selectMethod("manual");
  await fillCredential("clientId", "manual-client");
  await fillCredential("secret", "manual-secret");
  const input = host.querySelector<HTMLInputElement>('input[name="clientId"]')!;
  const key = new KeyboardEvent("keydown", {
    key: "Enter",
    isComposing: true,
    bubbles: true,
    cancelable: true,
  });
  await act(async () => input.dispatchEvent(key));
  expect(key.defaultPrevented).toBe(true);
  const original = request.getMockImplementation()!;
  request.mockImplementation((ep, path, init) =>
    path === "/dingtalk/bindings/manual"
      ? new Promise(() => {})
      : original(ep, path, init),
  );
  const form = host.querySelector("form[data-channel-binding]")!;
  await act(async () => {
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  expect(
    request.mock.calls.filter(
      ([, path]) => path === "/dingtalk/bindings/manual",
    ),
  ).toHaveLength(1);
});

async function renderBoundWecom() {
  const original = request.getMockImplementation()!;
  request.mockImplementation(async (ep, path, init) =>
    path === "/wecom/diagnostics"
      ? {
          configured: true,
          appId: "existing-wecom",
          missingConfiguration: [],
          deliveryHealth: "not_observed",
        }
      : original(ep, path, init),
  );
  await render();
  await click("channels.provider_wecom");
}
it("reopens WeCom authorization for a configured bot and registers the replacement", async () => {
  wecomSdk.open.mockResolvedValue({
    botid: "replacement-wecom",
    secret: "test-replacement-secret",
  });
  await renderBoundWecom();
  await click("channels.newQr");
  expect(wecomSdk.open).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain("channels.pairingTitle");
  expect(host.textContent).toContain("channels.wecomPairingDescription");
  const call = request.mock.calls.find(
    ([, path]) => path === "/wecom/bindings",
  );
  expect(JSON.parse(call![2]!.body as string)).toEqual({
    botId: "replacement-wecom",
    secret: "test-replacement-secret",
  });
  expect(
    request.mock.calls.some(([, , init]) => init?.method === "DELETE"),
  ).toBe(false);
  expect(host.textContent).not.toContain("test-replacement-secret");
  expect(host.textContent).toContain("channels.status_BOUND");
});
it("cancels WeCom regeneration while retaining the connected bot", async () => {
  wecomSdk.open.mockReturnValue(new Promise(() => {}));
  await renderBoundWecom();
  await click("channels.newQr");
  expect(host.textContent).toContain("channels.connected");
  await click("channels.cancelAuthorization");
  expect(
    request.mock.calls.some(([, path]) => path === "/wecom/bindings"),
  ).toBe(false);
  expect(host.textContent).toContain("channels.connected");
  expect(
    [...host.querySelectorAll("button")].find(
      (b) => b.textContent === "channels.newQr",
    )?.disabled,
  ).toBe(false);
  expect(wecomSdk.destroy).toHaveBeenCalled();
});
it("allows retrying configured WeCom regeneration after a blocked popup", async () => {
  wecomSdk.open.mockRejectedValue({ code: "WINDOW_BLOCKED" });
  await renderBoundWecom();
  await click("channels.newQr");
  expect(host.textContent).toContain("channels.wecomPopupBlocked");
  expect(host.textContent).toContain("channels.connected");
  wecomSdk.open.mockResolvedValue({
    botid: "retry-wecom",
    secret: "test-retry-secret",
  });
  await click("channels.newQr");
  expect(wecomSdk.open).toHaveBeenCalledTimes(2);
  expect(
    request.mock.calls.filter(([, path]) => path === "/wecom/bindings"),
  ).toHaveLength(1);
});

it.each(["feishu", "dingtalk"])(
  "discards %s pairing when switching away and back",
  async (provider) => {
    vi.useFakeTimers();
    await render();
    if (provider !== "feishu") await click(`channels.provider_${provider}`);
    await click("channels.bind");
    expect(host.querySelector(".runtime-channels-qr")).not.toBeNull();
    await click("channels.provider_wecom");
    request.mockClear();
    await click(`channels.provider_${provider}`);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(host.querySelector(".runtime-channels-qr")).toBeNull();
    expect(host.textContent).not.toContain("channels.pairingTitle");
    expect(
      request.mock.calls.some(([, path]) => path.includes("/bindings/")),
    ).toBe(false);
  },
);
it("ignores a legacy stored binding after remount or browser refresh", async () => {
  sessionStorage.setItem(
    "mpa-feishu-binding:cn-beijing:runtime-1",
    "old-binding",
  );
  await render();
  expect(
    request.mock.calls.some(([, path]) => path.includes("/bindings/")),
  ).toBe(false);
  expect(host.textContent).not.toContain("channels.pairingTitle");
  expect(
    sessionStorage.getItem("mpa-feishu-binding:cn-beijing:runtime-1"),
  ).toBeNull();
});
it("clears the pairing QR and stops polling on panel refresh", async () => {
  vi.useFakeTimers();
  await render();
  await click("channels.bind");
  request.mockClear();
  await click("channels.refresh");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(host.querySelector(".runtime-channels-qr")).toBeNull();
  expect(host.textContent).not.toContain("channels.pairingTitle");
  expect(
    request.mock.calls.some(([, path]) => path.includes("/bindings/")),
  ).toBe(false);
});

async function selectMethod(value: "quick" | "manual") {
  const radio = host.querySelector<HTMLInputElement>(
    `input[type="radio"][value="${value}"]`,
  );
  expect(radio).not.toBeNull();
  await act(async () => radio!.click());
}

it.each(["feishu", "wecom", "dingtalk"])(
  "defaults %s to quick setup and exclusively reveals manual fields",
  async (provider) => {
    await render();
    if (provider !== "feishu") await click(`channels.provider_${provider}`);
    expect(
      host.querySelector<HTMLInputElement>('input[value="quick"]')?.checked,
    ).toBe(true);
    expect(host.querySelector("form[data-channel-binding]")).toBeNull();
    expect(
      request.mock.calls.some(([, , init]) => init?.method === "POST"),
    ).toBe(false);
    await selectMethod("manual");
    expect(host.querySelector("form[data-channel-binding]")).not.toBeNull();
    expect(
      [...host.querySelectorAll("button")].some((b) =>
        ["channels.bind", "channels.newQr"].includes(b.textContent || ""),
      ),
    ).toBe(false);
    await selectMethod("quick");
    expect(host.querySelector("form[data-channel-binding]")).toBeNull();
  },
);

it("binds Feishu with normalized credentials, preserving failures and clearing success", async () => {
  await render();
  await selectMethod("manual");
  const submit = [...host.querySelectorAll("button")].find(
    (b) => b.textContent === "channels.bindCredentials",
  )!;
  expect(submit.disabled).toBe(true);
  await fillCredential("appId", " test-feishu ");
  await fillCredential("secret", " test-secret ");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')?.type,
  ).toBe("password");
  request.mockRejectedValueOnce(new ChannelApiError(502));
  await click("channels.bindCredentials");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')?.value,
  ).toBe(" test-secret ");
  expect(host.textContent).toContain("channels.requestFailed");
  await click("channels.bindCredentials");
  const calls = request.mock.calls.filter(
    ([, path]) => path === "/feishu/bindings/manual",
  );
  expect(calls).toHaveLength(2);
  expect(JSON.parse(calls[1][2]!.body as string)).toEqual({
    appId: "test-feishu",
    appSecret: "test-secret",
  });
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')?.value,
  ).toBe("");
  expect(localStorage.setItem).not.toHaveBeenCalled();
  expect(JSON.stringify(sessionStorage)).not.toContain("test-secret");
});

it.each(["feishu", "dingtalk"])(
  "gates %s manual binding without hiding quick setup on old images",
  async (provider) => {
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (ep, path, init) =>
      path === "/capabilities"
        ? {
            serverSideBinding: true,
            bindingReady: true,
            channels: ["feishu", "wecom", "dingtalk"],
          }
        : original(ep, path, init),
    );
    await render();
    if (provider !== "feishu") await click(`channels.provider_${provider}`);
    await selectMethod("manual");
    expect(host.textContent).toContain("channels.manualUpgrade");
    expect(host.querySelector("form[data-channel-binding]")).toBeNull();
    await selectMethod("quick");
    await click("channels.bind");
    expect(
      request.mock.calls.some(([, path]) => path === `/${provider}/bindings`),
    ).toBe(true);
  },
);

it.each(["feishu", "wecom", "dingtalk"])(
  "preserves configured %s during failed manual replacement",
  async (provider) => {
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (ep, path, init) =>
      path === `/${provider}/diagnostics`
        ? {
            configured: true,
            appId: "existing-bot",
            missingConfiguration: [],
            deliveryHealth: "not_observed",
          }
        : original(ep, path, init),
    );
    await render();
    if (provider !== "feishu") await click(`channels.provider_${provider}`);
    await selectMethod("manual");
    expect(host.textContent).toContain("channels.manualReplacement");
    await fillCredential(
      provider === "feishu"
        ? "appId"
        : provider === "wecom"
          ? "botId"
          : "clientId",
      "replacement-bot",
    );
    await fillCredential("secret", "test-secret");
    request.mockRejectedValueOnce(new ChannelApiError(502));
    await click("channels.bindCredentials");
    expect(host.textContent).toContain("channels.connected");
    expect(
      request.mock.calls.some(([, , init]) => init?.method === "DELETE"),
    ).toBe(false);
  },
);

it("stops a pending QR poll and ignores its late result when switching methods", async () => {
  vi.useFakeTimers();
  await render();
  await click("channels.bind");
  let signal: AbortSignal | undefined;
  let resolve!: (value: unknown) => void;
  request.mockImplementation((_ep, _path, init) => {
    signal = init?.signal as AbortSignal;
    return new Promise((done) => {
      resolve = done;
    });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  await selectMethod("manual");
  expect(signal?.aborted).toBe(true);
  const count = request.mock.calls.length;
  await act(async () => resolve({ ...pending, status: "BOUND" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(request.mock.calls).toHaveLength(count);
  expect(host.querySelector(".runtime-channels-qr")).toBeNull();
  expect(host.textContent).not.toContain("channels.status_BOUND");
});

it("cancels SDK waiting when switching to manual and ignores late credentials", async () => {
  let resolve!: (value: unknown) => void;
  wecomSdk.open.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await render();
  await click("channels.provider_wecom");
  await click("channels.bind");
  await selectMethod("manual");
  expect(wecomSdk.destroy).toHaveBeenCalled();
  await act(async () => resolve({ botid: "late-bot", secret: "late-secret" }));
  expect(
    request.mock.calls.some(([, path]) => path === "/wecom/bindings"),
  ).toBe(false);
  await fillCredential("botId", "new-bot");
  await fillCredential("secret", "new-secret");
  await click("channels.bindCredentials");
  expect(
    request.mock.calls.filter(([, path]) => path === "/wecom/bindings"),
  ).toHaveLength(1);
});

it("clears manual credentials and defaults after provider or Runtime changes", async () => {
  await render();
  await selectMethod("manual");
  await fillCredential("appId", "test-feishu");
  await fillCredential("secret", "test-secret");
  await selectMethod("quick");
  await selectMethod("manual");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')?.value,
  ).toBe("");
  await click("channels.provider_dingtalk");
  expect(
    host.querySelector<HTMLInputElement>('input[value="quick"]')?.checked,
  ).toBe(true);
  await selectMethod("manual");
  await act(async () =>
    root.render(<RuntimeChannels runtimeId="runtime-2" region="cn-beijing" />),
  );
  expect(
    host.querySelector<HTMLInputElement>('input[value="quick"]')?.checked,
  ).toBe(true);
});

it("blocks switching and duplicate/IME submissions while manual registration is running", async () => {
  await render();
  await selectMethod("manual");
  await fillCredential("appId", "test-feishu");
  await fillCredential("secret", "test-secret");
  const input = host.querySelector<HTMLInputElement>('input[name="appId"]')!;
  for (const options of [{ isComposing: true }, { keyCode: 229 }]) {
    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
      ...options,
    });
    await act(async () => input.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
  }
  request.mockImplementation(() => new Promise(() => {}));
  const form = host.querySelector("form[data-channel-binding]")!;
  await act(async () => {
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await selectMethod("quick");
  expect(
    host.querySelector<HTMLInputElement>('input[value="manual"]')?.checked,
  ).toBe(true);
  expect(
    request.mock.calls.filter(([, path]) => path === "/feishu/bindings/manual"),
  ).toHaveLength(1);
});

it("keeps uncertain registration blocked across method changes", async () => {
  await render();
  await selectMethod("manual");
  await fillCredential("appId", "test-feishu");
  await fillCredential("secret", "test-secret");
  request.mockRejectedValueOnce(new ChannelApiError(409));
  await click("channels.bindCredentials");
  await selectMethod("quick");
  const bind = [...host.querySelectorAll("button")].find(
    (b) => b.textContent === "channels.bind",
  )!;
  expect(bind.disabled).toBe(true);
  await selectMethod("manual");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')?.disabled,
  ).toBe(true);
});

it("preserves an uncertain QR registration after changing configuration methods", async () => {
  const original = request.getMockImplementation()!;
  request.mockImplementation(async (ep, path, init) =>
    path === "/feishu/bindings"
      ? {
          ...pending,
          status: "FAILED",
          lastErrorCode: "REGISTRATION_UNCERTAIN",
        }
      : original(ep, path, init),
  );
  await render();
  await click("channels.bind");
  await selectMethod("manual");
  expect(host.textContent).toContain("channels.uncertain");
  expect(
    host.querySelector<HTMLInputElement>('input[name="secret"]')?.disabled,
  ).toBe(true);
  await selectMethod("quick");
  expect(
    [...host.querySelectorAll("button")].find(
      (b) => b.textContent === "channels.bind",
    )?.disabled,
  ).toBe(true);
});

it.each(["feishu", "wecom", "dingtalk"])(
  "uses the common QR binding label for %s",
  async (provider) => {
    await render();
    if (provider !== "feishu") await click(`channels.provider_${provider}`);
    expect(
      [...host.querySelectorAll("button")].some(
        (b) => b.textContent === "channels.bind",
      ),
    ).toBe(true);
  },
);
