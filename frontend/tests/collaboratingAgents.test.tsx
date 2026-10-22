// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CollaboratorManager } from "../src/ui/collaborating-agents/CollaboratingAgents";
import {
  requestCollaborators,
  createA2aCenterAgent,
  createA2aSpace,
  requestA2aCenterAgent,
  deleteA2aCenterSpace,
  getRuntimes,
  requestA2aRuntimeEndpoints,
} from "../src/adk/client";
vi.mock("../src/adk/client", () => ({
  requestCollaborators: vi.fn(),
  createA2aCenterAgent: vi.fn(),
  createA2aSpace: vi.fn(),
  requestA2aCenterAgent: vi.fn(),
  deleteA2aCenterSpace: vi.fn(),
  getRuntimes: vi.fn(),
  requestA2aRuntimeEndpoints: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
const request = vi.mocked(requestCollaborators),
  create = vi.mocked(createA2aCenterAgent);
let root: Root, host: HTMLDivElement;
const page = (items: unknown[]) =>
  Response.json({ items, total: items.length, page: 1, page_size: 50 });
function button(text: string) {
  const found = Array.from(host.querySelectorAll("button")).find(
    (x) => x.textContent === text,
  );
  if (!found) throw new Error("Missing button " + text);
  return found;
}
function field(label: string) {
  const node = host.querySelector<
    | HTMLInputElement
    | HTMLSelectElement
    | HTMLTextAreaElement
    | HTMLButtonElement
  >(`[aria-label="${label}"]`);
  if (!node) throw new Error("Missing field " + label);
  return node;
}
async function change(label: string, value: string) {
  const node = field(label);
  if (node instanceof HTMLButtonElement) {
    const native = node.parentElement?.querySelector("select");
    if (!native) throw new Error("No select");
    const option = Array.from(native.options).find(
      (item) => item.value === value,
    );
    if (!option) throw new Error("No option");
    await act(async () => node.click());
    const visible = Array.from(
      document.querySelectorAll<HTMLElement>('[role="option"]'),
    ).find((item) => item.getAttribute("aria-label") === option.label);
    if (!visible) throw new Error("No visible option");
    await act(async () => visible.click());
    return;
  }
  const proto =
    node instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (!setter) throw new Error("No setter");
  await act(async () => {
    setter.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function render(id = "r-one") {
  await act(async () =>
    root.render(<CollaboratorManager runtimeId={id} region="cn-beijing" />),
  );
}
async function submit() {
  await act(async () =>
    host
      .querySelector("form")
      ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
}
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  request.mockReset();
  create.mockReset();
  vi.mocked(requestA2aCenterAgent).mockReset();
  vi.mocked(deleteA2aCenterSpace).mockReset();
  vi.mocked(createA2aSpace).mockReset();
  vi.mocked(getRuntimes).mockReset();
  vi.mocked(getRuntimes).mockResolvedValue({
    runtimes: ["r-source", "r-old", "r-new"].map((runtimeId) => ({
      runtimeId,
      name: runtimeId,
      region: "cn-beijing",
      status: "Ready",
      author: "fixture",
      isMine: true,
      canDelete: false,
    })),
    nextToken: "",
  });
  vi.mocked(requestA2aRuntimeEndpoints).mockReset();
  vi.mocked(requestA2aRuntimeEndpoints).mockImplementation(
    async (_target, _region, source) =>
      Response.json({
        runtimeId: source,
        endpoints: [
          { networkType: "public", url: "https://public.example/runtime" },
        ],
      }),
  );
  request.mockImplementation(async (_r, _region, path, init) =>
    path === "/registry/binding"
      ? Response.json({
          space_id: init?.method === "PUT" ? "as-one" : null,
          space_name: null,
          region: "cn-beijing",
          revision: init?.method === "PUT" ? 1 : 0,
        })
      : path.startsWith("/registry/spaces")
        ? page([{ Id: "as-one", Name: "Default" }])
        : page([{ Id: "a-one", Name: "Demo", Status: "running" }]),
  );
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it("opens Center directly and only persists the space binding", async () => {
  await render();
  expect(host.textContent).toContain("Demo");
  expect(host.textContent).not.toContain("center.manual");
  await act(async () => button("center.connect").click());
  const call = request.mock.calls.find((x) => x[3]?.method === "PUT");
  expect(JSON.parse(String(call?.[3]?.body))).toEqual({
    space_id: "as-one",
    revision: 0,
  });
  expect(request.mock.calls.every((x) => x[2].startsWith("/registry/"))).toBe(
    true,
  );
});
it("distinguishes denied/unsupported from empty and can retry", async () => {
  request.mockResolvedValue(new Response("", { status: 403 }));
  await render();
  expect(host.textContent).toContain("center.forbidden");
  expect(host.textContent).not.toContain("center.noSpaces");
  request.mockResolvedValue(new Response("", { status: 404 }));
  await act(async () => button("refresh").click());
  expect(host.textContent).toContain("unsupported");
});
it("registers Runtime source once and refreshes actual center members", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  let resolve!: (value: Response) => void;
  create.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await submit();
  await submit();
  expect(create).toHaveBeenCalledTimes(1);
  expect(create.mock.calls[0][1]).toEqual({
    targetRuntimeId: "r-one",
    spaceId: "as-one",
    projectName: "default",
    source: "Runtime",
    runtimeId: "r-source",
    networkType: "public",
  });
  await act(async () => resolve(Response.json({ id: "a-created" })));
  expect(host.textContent).toContain("registration.created");
  expect(host.querySelector("form")).toBeNull();
  expect(
    request.mock.calls.filter((x) => x[2].startsWith("/registry/agents"))
      .length,
  ).toBe(2);
});
it("supports Standard JSON and URL and clears source-specific values", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.source", "Standard");
  await change(
    "registration.cardJson",
    JSON.stringify({
      name: "Demo",
      url: "https://agent.example",
      version: "1",
    }),
  );
  create.mockResolvedValue(Response.json({ id: "a-created" }));
  await submit();
  expect(create.mock.calls[0][1]).toMatchObject({
    source: "Standard",
    importType: "json",
    agentCard: { name: "Demo" },
  });
  await act(async () => button("registration.open").click());
  await change("registration.source", "Standard");
  expect(field("registration.cardJson").value).toBe("");
  await change("registration.importType", "url");
  await change("registration.cardUrl", "https://agent.example/card");
  await submit();
  expect(create.mock.calls[1][1]).toMatchObject({
    source: "Standard",
    importType: "url",
    cardUrl: "https://agent.example/card",
  });
});
it("rejects invalid JSON locally and does not submit during IME", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.source", "Standard");
  await change("registration.cardJson", "{");
  await submit();
  expect(host.textContent).toContain("registration.invalidCard");
  expect(create).not.toHaveBeenCalled();
  await change(
    "registration.cardJson",
    JSON.stringify({
      name: "Demo",
      url: "https://agent.example",
      version: "1",
    }),
  );
  await act(async () => {
    field("registration.cardJson").dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    );
  });
  await submit();
  expect(create).not.toHaveBeenCalled();
});
it("does not blindly retry unknown writes and aborts stale responses on Runtime switch", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  create.mockResolvedValue(new Response("", { status: 502 }));
  await submit();
  expect(host.textContent).toContain("registration.uncertain");
  expect(button("registration.submit").disabled).toBe(true);
  await submit();
  expect(create).toHaveBeenCalledTimes(1);
  await act(async () => button("cancel").click());
  await act(async () => button("refresh").click());
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  let resolve!: (r: Response) => void;
  create.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await submit();
  const signal = create.mock.calls.at(-1)?.[2];
  await render("r-two");
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve(Response.json({ id: "a-stale" })));
  expect(host.textContent).not.toContain("registration.created");
});

it("closes a Select menu on Escape without losing the form, then restores focus on cancel", async () => {
  await render();
  await act(async () => button("registration.open").click());
  const source = field("registration.source");
  await act(async () =>
    source.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "ArrowDown",
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  expect(document.querySelector('[role="listbox"]')).not.toBeNull();
  await act(async () =>
    source.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  expect(host.querySelector("form")).not.toBeNull();
  await act(async () =>
    field("registration.knownRuntime").dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  expect(host.querySelector("form")).toBeNull();
  expect(document.activeElement).toBe(button("registration.open"));
});

it("keeps accepted creation separate from a failed membership refresh", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  create.mockResolvedValue(Response.json({ id: "a-created" }));
  request.mockResolvedValueOnce(new Response("", { status: 503 }));
  await submit();
  expect(host.textContent).toContain("registration.created");
  expect(host.textContent).toContain("center.failed");
  expect(host.textContent).not.toContain("registration.uncertain");
  expect(create).toHaveBeenCalledTimes(1);
});

it("masks Card data by default and clears it when switching import method", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.source", "Standard");
  expect(field("registration.cardJson").getAttribute("type")).toBe("password");
  await change("registration.cardJson", "private-card-value");
  await act(async () => button("showSecret").click());
  expect(field("registration.cardJson").tagName).toBe("TEXTAREA");
  await change("registration.importType", "url");
  await change("registration.importType", "json");
  expect(field("registration.cardJson").getAttribute("type")).toBe("password");
  expect(field("registration.cardJson").value).toBe("");
});

it("separates binding from member registration and identifies the destination", async () => {
  await render();
  const binding = host.querySelector('[aria-label="center.bindingTitle"]');
  const members = host.querySelector('[aria-label="center.membersTitle"]');
  expect(binding?.contains(button("center.connect"))).toBe(true);
  expect(binding?.contains(button("spaceCreation.open"))).toBe(true);
  expect(members?.contains(button("registration.open"))).toBe(true);
  expect(binding?.contains(button("registration.open"))).toBe(false);
  await act(async () => button("registration.open").click());
  expect(host.querySelector("form")?.textContent).toContain("Default");
});
it("creates and selects an unlisted space without changing the binding", async () => {
  await render();
  await act(async () => button("spaceCreation.open").click());
  expect(document.activeElement).toBe(field("spaceCreation.name"));
  await change("spaceCreation.name", "Team");
  vi.mocked(createA2aSpace).mockResolvedValue(Response.json({ id: "as-new" }));
  await submit();
  expect(createA2aSpace).toHaveBeenCalledTimes(1);
  expect(vi.mocked(createA2aSpace).mock.calls[0][1]).toEqual({
    targetRuntimeId: "r-one",
    name: "Team",
    projectName: "default",
    intentEnabled: false,
  });
  expect(host.textContent).toContain("spaceCreation.created");
  expect(host.textContent).toContain("Team");
  expect(request.mock.calls.some((x) => x[2].includes("space_id=as-new"))).toBe(
    true,
  );
  expect(request.mock.calls.some((x) => x[3]?.method === "PUT")).toBe(false);
  expect(button("center.connect").disabled).toBe(false);
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  create.mockResolvedValue(Response.json({ id: "a-created" }));
  await submit();
  expect(create.mock.calls[0][1].spaceId).toBe("as-new");
});
it("permits space creation when the account has no spaces", async () => {
  request.mockImplementation(async (_r, _region, path) =>
    path === "/registry/binding"
      ? Response.json({
          space_id: null,
          space_name: null,
          region: "cn-beijing",
          revision: 0,
        })
      : page([]),
  );
  await render();
  expect(button("spaceCreation.open").disabled).toBe(false);
  await act(async () => button("spaceCreation.open").click());
  expect(field("spaceCreation.name")).toBeTruthy();
  await change("spaceCreation.name", "First space");
  vi.mocked(createA2aSpace).mockResolvedValue(
    Response.json({ id: "as-first" }),
  );
  await submit();
  expect(host.textContent).toContain("First space");
  expect(button("center.connect").disabled).toBe(false);
});
it("prevents duplicate space creates, blocks writes after cancellation, and ignores stale responses", async () => {
  await render();
  await act(async () => button("spaceCreation.open").click());
  await change("spaceCreation.name", "Team");
  let resolve!: (response: Response) => void;
  vi.mocked(createA2aSpace).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await submit();
  await submit();
  expect(createA2aSpace).toHaveBeenCalledTimes(1);
  expect(button("registration.open").disabled).toBe(true);
  await act(async () => button("cancel").click());
  expect(button("spaceCreation.open").disabled).toBe(true);
  expect(host.textContent).toContain("spaceCreation.uncertain");
  await render("r-two");
  await act(async () => resolve(Response.json({ id: "as-stale" })));
  expect(host.textContent).not.toContain("as-stale");
  expect(button("spaceCreation.open").disabled).toBe(false);
});
it("retains confirmed creation success when the subsequent refresh fails", async () => {
  await render();
  await act(async () => button("spaceCreation.open").click());
  await change("spaceCreation.name", "Team");
  vi.mocked(createA2aSpace).mockResolvedValue(Response.json({ id: "as-new" }));
  request.mockResolvedValue(new Response("", { status: 503 }));
  await submit();
  expect(host.textContent).toContain("spaceCreation.created");
  expect(host.textContent).toContain("center.failed");
  expect(host.textContent).toContain("Team");
  expect(createA2aSpace).toHaveBeenCalledTimes(1);
});
it("requires refresh for unknown space creation and preserves IME and cancel focus", async () => {
  await render();
  const trigger = button("spaceCreation.open");
  await act(async () => trigger.click());
  await change("spaceCreation.name", "Team");
  await act(async () =>
    field("spaceCreation.name").dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    ),
  );
  await submit();
  expect(createA2aSpace).not.toHaveBeenCalled();
  await act(async () =>
    field("spaceCreation.name").dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    ),
  );
  vi.mocked(createA2aSpace).mockResolvedValue(
    new Response("", { status: 502 }),
  );
  await submit();
  await submit();
  expect(createA2aSpace).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain("spaceCreation.uncertain");
  await act(async () => button("cancel").click());
  expect(document.activeElement).toBe(button("refresh"));
  await act(async () => button("refresh").click());
  await act(async () => button("spaceCreation.open").click());
  await act(async () => button("cancel").click());
  expect(document.activeElement).toBe(trigger);
});

it("forwards the explicit project and semantic search choice", async () => {
  await render();
  await act(async () => button("spaceCreation.open").click());
  await change("spaceCreation.name", " Team ");
  await change("spaceCreation.project", " research ");
  const checkbox = host.querySelector<HTMLInputElement>(
    'input[type="checkbox"]',
  );
  await act(async () => checkbox?.click());
  vi.mocked(createA2aSpace).mockResolvedValue(
    Response.json({ id: "as-project" }),
  );
  await submit();
  expect(vi.mocked(createA2aSpace).mock.calls[0][1]).toMatchObject({
    name: "Team",
    projectName: "research",
    intentEnabled: true,
  });
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  create.mockResolvedValue(Response.json({ id: "a-created" }));
  await submit();
  expect(create.mock.calls[0][1].projectName).toBe("research");
});
it("validates space names locally and allows correction after an explicit denial", async () => {
  await render();
  await act(async () => button("spaceCreation.open").click());
  await change("spaceCreation.name", "   ");
  await submit();
  expect(createA2aSpace).not.toHaveBeenCalled();
  expect(host.textContent).toContain("spaceCreation.invalid");
  await change("spaceCreation.name", "Team");
  vi.mocked(createA2aSpace).mockResolvedValue(
    new Response("", { status: 403 }),
  );
  await submit();
  expect(host.textContent).toContain("spaceCreation.forbidden");
  expect(document.activeElement?.getAttribute("role")).toBe("alert");
  expect(button("spaceCreation.submit").disabled).toBe(false);
  vi.mocked(createA2aSpace).mockResolvedValue(
    Response.json({ id: "as-allowed" }),
  );
  await submit();
  expect(createA2aSpace).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain("spaceCreation.created");
});

it.each(["Default", null])(
  "shows space names without IDs, including binding and registration (%s)",
  async (spaceName) => {
    request.mockImplementation(async (_r, _region, path) =>
      path === "/registry/binding"
        ? Response.json({
            space_id: "as-one",
            space_name: spaceName,
            region: "cn-beijing",
            revision: 1,
          })
        : path.startsWith("/registry/spaces")
          ? page([{ Id: "as-one", Name: "Default" }])
          : page([]),
    );
    await render();
    const status = Array.from(host.querySelectorAll('[role="status"]')).find(
      (node) => node.textContent?.includes("center.current"),
    );
    expect(status?.textContent).toContain("Default");
    expect(host.textContent).not.toContain("as-one");
    await act(async () => button("registration.open").click());
    expect(host.querySelector("form")?.textContent).toContain("Default");
    expect(host.textContent).not.toContain("as-one");
  },
);

it("only unbinds the selected bound space and clears confirmation when switching", async () => {
  request.mockImplementation(async (_r, _region, path, init) =>
    path === "/registry/binding"
      ? Response.json({
          space_id: init?.method === "PUT" ? null : "as-one",
          space_name: "Default",
          region: "cn-beijing",
          revision: init?.method === "PUT" ? 2 : 1,
        })
      : path.startsWith("/registry/spaces")
        ? page([
            { Id: "as-one", Name: "Default" },
            { Id: "as-two", Name: "Other" },
          ])
        : page([]),
  );
  await render();
  await act(async () => button("center.disconnect").click());
  expect(
    host.querySelector('[role="group"][aria-label="center.disconnectConfirm"]'),
  ).not.toBeNull();
  await change("center.space", "as-two");
  expect(
    Array.from(host.querySelectorAll("button")).filter(
      (item) => item.textContent === "center.disconnect",
    ),
  ).toHaveLength(0);
  expect(
    host.querySelector('[role="group"][aria-label="center.disconnectConfirm"]'),
  ).toBeNull();
  expect(request.mock.calls.some((call) => call[3]?.method === "PUT")).toBe(
    false,
  );
  await change("center.space", "as-one");
  expect(
    host.querySelector('[role="group"][aria-label="center.disconnectConfirm"]'),
  ).toBeNull();
  await act(async () => button("center.disconnect").click());
  await act(async () =>
    host
      .querySelector<HTMLButtonElement>(
        '[role="group"][aria-label="center.disconnectConfirm"] button',
      )
      ?.click(),
  );
  const writes = request.mock.calls.filter((call) => call[3]?.method === "PUT");
  expect(writes).toHaveLength(1);
  expect(JSON.parse(String(writes[0][3]?.body))).toEqual({
    space_id: null,
    revision: 1,
  });
});

it("opens a scoped member detail dialog and keeps raw Cards out of the UI", async () => {
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    Response.json({
      id: "a-one",
      name: "Demo",
      status: "running",
      source: "Runtime",
      defaultVersion: "1",
      runtimeId: "r-source",
    }),
  );
  await render();
  await act(async () => button("member.view").click());
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    "r-source",
  );
  expect(vi.mocked(requestA2aCenterAgent).mock.calls[0].slice(0, 4)).toEqual([
    "r-one",
    "cn-beijing",
    "as-one",
    "a-one",
  ]);
  expect(request.mock.calls.some((call) => call[3]?.method === "PUT")).toBe(
    false,
  );
});
it("requires confirmation to deregister and refreshes only after success", async () => {
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    Response.json({ deleted: true }),
  );
  await render();
  await act(async () => button("member.unregister").click());
  expect(requestA2aCenterAgent).not.toHaveBeenCalled();
  const confirm = Array.from(
    document.querySelectorAll<HTMLButtonElement>("button"),
  ).find((node) => node.textContent === "member.confirmUnregister");
  await act(async () => confirm?.click());
  expect(requestA2aCenterAgent).toHaveBeenCalledTimes(1);
  expect(vi.mocked(requestA2aCenterAgent).mock.calls[0][4]?.method).toBe(
    "DELETE",
  );
  await act(async () => confirm?.click());
  expect(requestA2aCenterAgent).toHaveBeenCalledTimes(1);
  expect(
    request.mock.calls.filter((call) => call[2].startsWith("/registry/agents")),
  ).toHaveLength(2);
});
it("blocks nonempty space deletion and allows a confirmed empty space deletion", async () => {
  await render();
  expect(button("spaceDeletion.open").disabled).toBe(true);
  request.mockImplementation(async (_r, _region, path) =>
    path === "/registry/binding"
      ? Response.json({
          space_id: null,
          space_name: null,
          region: "cn-beijing",
          revision: 0,
        })
      : path.startsWith("/registry/spaces")
        ? page([{ Id: "as-one", Name: "Default" }])
        : page([]),
  );
  await act(async () => button("refresh").click());
  vi.mocked(deleteA2aCenterSpace).mockResolvedValue(
    Response.json({ deleted: true }),
  );
  await act(async () => button("spaceDeletion.open").click());
  expect(deleteA2aCenterSpace).not.toHaveBeenCalled();
  const confirm = Array.from(
    document.querySelectorAll<HTMLButtonElement>("button"),
  ).find((node) => node.textContent === "spaceDeletion.confirm");
  await act(async () => confirm?.click());
  expect(deleteA2aCenterSpace).toHaveBeenCalledTimes(1);
});
it("shows duplicate Runtime refusal without locking registration as unknown", async () => {
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  create.mockResolvedValue(
    Response.json(
      { detail: { reason: "runtime_already_registered" } },
      { status: 409 },
    ),
  );
  await submit();
  expect(host.textContent).toContain("registration.runtimeExists");
  expect(host.textContent).not.toContain("registration.uncertain");
  expect(button("registration.submit").disabled).toBe(false);
});

it("does not retry an unconfirmed deregistration and ignores a late success after closing", async () => {
  let resolve!: (response: Response) => void;
  vi.mocked(requestA2aCenterAgent).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await render();
  await act(async () => button("member.unregister").click());
  const confirm = Array.from(
    document.querySelectorAll<HTMLButtonElement>("button"),
  ).find((node) => node.textContent === "member.confirmUnregister");
  await act(async () => {
    confirm?.click();
    confirm?.click();
  });
  expect(requestA2aCenterAgent).toHaveBeenCalledTimes(1);
  await act(async () =>
    document
      .querySelector<HTMLButtonElement>(
        '[role="dialog"] button[aria-label="close"]',
      )
      ?.click(),
  );
  expect(host.textContent).toContain("center.refreshRequired");
  await act(async () => resolve(Response.json({ deleted: true })));
  expect(host.textContent).not.toContain("member.unregistered");
  expect(
    request.mock.calls.filter((call) => call[2].startsWith("/registry/agents")),
  ).toHaveLength(1);
});
it("keeps successful deregistration visible if refreshing the list fails", async () => {
  await render();
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    Response.json({ deleted: true }),
  );
  await act(async () => button("member.unregister").click());
  request.mockResolvedValue(new Response("", { status: 503 }));
  const confirm = Array.from(
    document.querySelectorAll<HTMLButtonElement>("button"),
  ).find((node) => node.textContent === "member.confirmUnregister");
  await act(async () => confirm?.click());
  expect(host.textContent).toContain("member.unregistered");
  expect(host.textContent).toContain("center.failed");
  expect(host.textContent).not.toContain("actions.uncertain");
});
it("retries a detail read error without treating it as empty or mutation uncertainty", async () => {
  await render();
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    new Response("", { status: 403 }),
  );
  await act(async () => button("member.view").click());
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    "member.loadFailed",
  );
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    Response.json({
      id: "a-one",
      name: "Demo",
      status: "running",
      source: "Runtime",
    }),
  );
  const retry = Array.from(
    document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
  ).find((node) => node.textContent === "refresh");
  await act(async () => retry?.click());
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    "member.registered",
  );
  expect(requestA2aCenterAgent).toHaveBeenCalledTimes(2);
});

it("keeps a rejected read preflight separate from an uncertain deletion", async () => {
  await render();
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    Response.json({ detail: { reason: "read_failed" } }, { status: 502 }),
  );
  await act(async () => button("member.unregister").click());
  const confirm = Array.from(
    document.querySelectorAll<HTMLButtonElement>("button"),
  ).find((node) => node.textContent === "member.confirmUnregister");
  await act(async () => confirm?.click());
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    "actions.preflightFailed",
  );
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain(
    "actions.uncertain",
  );
  expect(confirm?.disabled).toBe(false);
});

it.each([401, 403])(
  "distinguishes Runtime preflight auth failure from cloud permissions (%s)",
  async (status) => {
    request.mockImplementation(async (_r, _region, path) =>
      path === "/registry/binding"
        ? Response.json({
            space_id: null,
            space_name: null,
            region: "cn-beijing",
            revision: 0,
          })
        : path.startsWith("/registry/spaces")
          ? page([{ Id: "as-one", Name: "Default" }])
          : page([]),
    );
    vi.mocked(deleteA2aCenterSpace).mockResolvedValue(
      Response.json({ detail: { reason: "runtime_auth_failed" } }, { status }),
    );
    await render();
    await act(async () => button("spaceDeletion.open").click());
    const confirm = Array.from(
      document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
    ).find((node) => node.textContent === "spaceDeletion.confirm");
    await act(async () => confirm?.click());
    expect(document.querySelector('[role="alert"]')?.textContent).toBe(
      "actions.runtimeAuthFailed",
    );
    expect(confirm?.disabled).toBe(false);
    expect(host.textContent).not.toContain("center.refreshRequired");
    vi.mocked(deleteA2aCenterSpace).mockResolvedValue(
      Response.json({ detail: { reason: "forbidden" } }, { status: 403 }),
    );
    await act(async () => confirm?.click());
    expect(document.querySelector('[role="alert"]')?.textContent).toBe(
      "actions.forbidden",
    );
  },
);
it.each(["public", "private"])(
  "offers only the configured %s endpoint and displays the address",
  async (networkType) => {
    vi.mocked(requestA2aRuntimeEndpoints).mockImplementation(
      async (_target, _region, source) =>
        Response.json({
          runtimeId: source,
          endpoints: [
            { networkType, url: `https://${networkType}.example/runtime` },
          ],
        }),
    );
    await render();
    await act(async () => button("registration.open").click());
    await change("registration.knownRuntime", "r-source");
    const network = field("registration.network").parentElement?.querySelector(
      "select",
    );
    expect(network?.options).toHaveLength(1);
    expect(network?.value).toBe(networkType);
    expect(host.textContent).toContain(
      `https://${networkType}.example/runtime`,
    );
    create.mockResolvedValue(Response.json({ id: "a-created" }));
    await submit();
    expect(create.mock.calls[0][1]).toMatchObject({ networkType });
  },
);
it("blocks registration during endpoint reads, discards stale endpoints, and retries read errors", async () => {
  let resolve!: (response: Response) => void;
  vi.mocked(requestA2aRuntimeEndpoints).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-old");
  expect(button("registration.submit").disabled).toBe(true);
  await submit();
  expect(create).not.toHaveBeenCalled();
  vi.mocked(requestA2aRuntimeEndpoints).mockResolvedValue(
    new Response("", { status: 403 }),
  );
  await change("registration.knownRuntime", "r-new");
  expect(host.textContent).toContain("registration.endpointsFailed");
  await act(async () =>
    resolve(
      Response.json({
        runtimeId: "r-old",
        endpoints: [{ networkType: "public", url: "https://stale.example" }],
      }),
    ),
  );
  expect(host.textContent).not.toContain("stale.example");
  vi.mocked(requestA2aRuntimeEndpoints).mockResolvedValue(
    Response.json({ runtimeId: "r-new", endpoints: [] }),
  );
  await act(async () =>
    host
      .querySelector<HTMLButtonElement>('form [role="alert"] button')
      ?.click(),
  );
  expect(host.textContent).toContain("registration.noEndpoints");
  expect(button("registration.submit").disabled).toBe(true);
});
it("shows service address and skill descriptions, tags and examples as plain text", async () => {
  vi.mocked(requestA2aCenterAgent).mockResolvedValue(
    Response.json({
      id: "a-one",
      name: "Demo",
      status: "running",
      source: "Runtime",
      serviceAddress: "https://agent.example/a2a",
      skills: [
        {
          id: "weather",
          name: "Weather",
          description: "<b>Forecast</b>",
          tags: ["outdoors"],
          examples: ["Hangzhou today"],
        },
      ],
      skillsTruncated: false,
    }),
  );
  await render();
  await act(async () => button("member.view").click());
  const dialog = document.querySelector('[role="dialog"]');
  for (const text of [
    "https://agent.example/a2a",
    "Weather",
    "<b>Forecast</b>",
    "outdoors",
    "Hangzhou today",
  ])
    expect(dialog?.textContent).toContain(text);
  expect(dialog?.querySelector("b")).toBeNull();
});
it.each([null, []])(
  "distinguishes unavailable skill data from a confirmed empty list: %s",
  async (skills) => {
    vi.mocked(requestA2aCenterAgent).mockResolvedValue(
      Response.json({
        id: "a-one",
        name: "Demo",
        status: "running",
        source: "Standard",
        serviceAddress: null,
        skills,
        skillsTruncated: false,
      }),
    );
    await render();
    await act(async () => button("member.view").click());
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
      skills === null ? "member.skillsUnavailable" : "member.noSkills",
    );
  },
);

it("uses one required Runtime picker and never renders a manual ID input", async () => {
  await render();
  await act(async () => button("registration.open").click());
  expect(
    host.querySelector('input[aria-label="registration.runtimeId"]'),
  ).toBeNull();
  expect(field("registration.knownRuntime").getAttribute("aria-required")).toBe(
    "true",
  );
  expect(button("registration.submit").disabled).toBe(true);
  await submit();
  expect(create).not.toHaveBeenCalled();
  await change("registration.knownRuntime", "r-source");
  expect(button("registration.submit").disabled).toBe(false);
});
it("distinguishes initial Runtime list loading and an empty list, then retries", async () => {
  let resolve!: (value: Awaited<ReturnType<typeof getRuntimes>>) => void;
  vi.mocked(getRuntimes).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await render();
  await act(async () => button("registration.open").click());
  expect(field("registration.knownRuntime").disabled).toBe(true);
  expect(host.textContent).not.toContain("registration.noRuntimes");
  await act(async () => resolve({ runtimes: [], nextToken: "" }));
  expect(host.textContent).toContain("registration.noRuntimes");
  expect(host.textContent).not.toContain("registration.runtimeListFailed");
  expect(button("registration.submit").disabled).toBe(true);
  await act(async () =>
    host
      .querySelector<HTMLButtonElement>('form [role="status"] button')
      ?.click(),
  );
  await change("registration.knownRuntime", "r-source");
  expect(host.textContent).not.toContain("registration.noRuntimes");
  expect(button("registration.submit").disabled).toBe(false);
});
it("retries a Runtime list error without offering manual entry or showing an empty state", async () => {
  vi.mocked(getRuntimes).mockRejectedValueOnce(
    new Error("fixture read failure"),
  );
  await render();
  await act(async () => button("registration.open").click());
  expect(host.textContent).toContain("registration.runtimeListFailed");
  expect(host.textContent).not.toContain("registration.noRuntimes");
  expect(
    host.querySelector('input[aria-label="registration.runtimeId"]'),
  ).toBeNull();
  expect(button("registration.submit").disabled).toBe(true);
  await act(async () =>
    host
      .querySelector<HTMLButtonElement>('form [role="alert"] button')
      ?.click(),
  );
  await change("registration.knownRuntime", "r-source");
  expect(button("registration.submit").disabled).toBe(false);
});
it("keeps the selected Runtime across append pagination and invalidates a removed selection on replacement", async () => {
  const source = {
    runtimeId: "r-source",
    name: "Source",
    region: "cn-beijing",
    status: "Ready",
    author: "fixture",
    isMine: true,
    canDelete: false,
  };
  const other = { ...source, runtimeId: "r-new", name: "New" };
  vi.mocked(getRuntimes)
    .mockResolvedValueOnce({ runtimes: [source], nextToken: "page2" })
    .mockResolvedValueOnce({ runtimes: [source, other], nextToken: "page3" })
    .mockRejectedValueOnce(new Error("fixture pagination failure"))
    .mockResolvedValueOnce({ runtimes: [other], nextToken: "" });
  await render();
  await act(async () => button("registration.open").click());
  await change("registration.knownRuntime", "r-source");
  await act(async () => button("center.next").click());
  expect(
    field("registration.knownRuntime").parentElement?.querySelector("select")
      ?.options,
  ).toHaveLength(3);
  expect(button("registration.submit").disabled).toBe(false);
  await act(async () => button("center.next").click());
  await act(async () =>
    host
      .querySelector<HTMLButtonElement>('form [role="alert"] button')
      ?.click(),
  );
  expect(button("registration.submit").disabled).toBe(true);
  expect(host.textContent).not.toContain("https://public.example/runtime");
  await submit();
  expect(create).not.toHaveBeenCalled();
});
