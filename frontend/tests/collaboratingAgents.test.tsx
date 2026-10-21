// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CollaboratorManager } from "../src/ui/collaborating-agents/CollaboratingAgents";
import { requestCollaborators } from "../src/adk/client";
vi.mock("../src/adk/client", () => ({ requestCollaborators: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
const request = vi.mocked(requestCollaborators);
let root: Root, host: HTMLDivElement;
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  request.mockReset();
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it("distinguishes unsupported from empty and retries", async () => {
  request
    .mockResolvedValueOnce(new Response("", { status: 404 }))
    .mockResolvedValueOnce(Response.json({ items: [] }));
  await act(async () =>
    root.render(<CollaboratorManager runtimeId="r-one" region="cn-beijing" />),
  );
  expect(host.textContent).toContain("unsupported");
  expect(host.textContent).not.toContain("empty");
  await act(async () =>
    Array.from(host.querySelectorAll("button"))
      .find((x) => x.textContent === "refresh")!
      .click(),
  );
  expect(host.textContent).toContain("empty");
});
it("does not apply a response after switching Runtime", async () => {
  let resolve!: (value: Response) => void;
  request.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await act(async () =>
    root.render(
      <CollaboratorManager key="one" runtimeId="r-one" region="cn-beijing" />,
    ),
  );
  const signal = request.mock.calls[0][3]?.signal;
  request.mockResolvedValueOnce(Response.json({ items: [] }));
  await act(async () =>
    root.render(
      <CollaboratorManager key="two" runtimeId="r-two" region="cn-beijing" />,
    ),
  );
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve(new Response("", { status: 403 })));
  expect(host.textContent).toContain("empty");
  expect(host.textContent).not.toContain("forbidden");
});
const registration = () => ({
  id: "agent-one",
  mpa_id: "mpa-one",
  revision: 1,
  name: "Research",
  description: "Facts",
  card_url: "https://agent.example/card",
  enabled: true,
  auth_type: "none",
  credential_configured: false,
  header_name: "",
  check: { status: "not_checked" },
});
function button(label: string) {
  return Array.from(host.querySelectorAll("button")).find(
    (x) => x.textContent === label,
  )!;
}
it("creates, checks, edits and removes with revision and explicit confirmation", async () => {
  request.mockResolvedValueOnce(Response.json({ items: [] }));
  await act(async () =>
    root.render(<CollaboratorManager runtimeId="r-one" region="cn-beijing" />),
  );
  await act(async () => button("add").click());
  const inputs = host.querySelectorAll("input");
  const set = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )!.set!;
  await act(async () => {
    set.call(inputs[0], "Research");
    inputs[0].dispatchEvent(new Event("input", { bubbles: true }));
  });
  const url = host.querySelector('input[type="url"]')!;
  await act(async () => {
    set.call(url, "https://agent.example/card");
    url.dispatchEvent(new Event("input", { bubbles: true }));
  });
  request.mockResolvedValueOnce(Response.json(registration()));
  await act(async () =>
    host
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(
    JSON.parse(request.mock.calls.at(-1)![3]!.body as string),
  ).toMatchObject({ name: "Research", card_url: "https://agent.example/card" });
  const checked = {
    ...registration(),
    revision: 2,
    check: {
      status: "verified",
      card: {
        name: "Research",
        description: "Facts",
        endpoint: "https://agent.example/a2a",
        protocol_version: "0.3.0",
        transport: "JSONRPC",
        skills: [],
      },
    },
  };
  request.mockResolvedValueOnce(Response.json(checked));
  await act(async () => button("check").click());
  expect(request.mock.calls.at(-1)![2]).toBe("/agent-one/check");
  expect(JSON.parse(request.mock.calls.at(-1)![3]!.body as string)).toEqual({
    revision: 1,
  });
  expect(host.textContent).toContain("discoveryOnly");
  await act(async () => button("edit").click());
  request.mockResolvedValueOnce(
    Response.json({ ...registration(), revision: 3, enabled: false }),
  );
  await act(async () =>
    host.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click(),
  );
  await act(async () =>
    host
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(
    JSON.parse(request.mock.calls.at(-1)![3]!.body as string),
  ).toMatchObject({ revision: 2, enabled: false });
  const count = request.mock.calls.length;
  await act(async () => button("remove").click());
  expect(request.mock.calls.length).toBe(count);
  request.mockResolvedValueOnce(new Response(null, { status: 204 }));
  await act(async () => button("confirmRemove").click());
  expect(request.mock.calls.at(-1)![2]).toBe("/agent-one?revision=3");
  expect(host.textContent).toContain("empty");
});
it("preserves form on conflict and prevents duplicate submission", async () => {
  request.mockResolvedValueOnce(Response.json({ items: [registration()] }));
  await act(async () =>
    root.render(<CollaboratorManager runtimeId="r-one" region="cn-beijing" />),
  );
  await act(async () => button("edit").click());
  let resolve!: (value: Response) => void;
  request.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const form = host.querySelector("form")!;
  await act(async () => {
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  expect(request).toHaveBeenCalledTimes(2);
  await act(async () => resolve(new Response("", { status: 409 })));
  expect(host.textContent).toContain("conflict");
  expect(host.querySelector("form")).not.toBeNull();
});

it("requires reconciliation after an uncertain write", async () => {
  request.mockResolvedValueOnce(Response.json({ items: [registration()] }));
  await act(async () =>
    root.render(<CollaboratorManager runtimeId="r-one" region="cn-beijing" />),
  );
  request.mockRejectedValueOnce(new Error("network interrupted"));
  await act(async () => button("check").click());
  expect(host.textContent).toContain("uncertain");
  expect(button("edit").disabled).toBe(true);
  request.mockResolvedValueOnce(Response.json({ items: [registration()] }));
  await act(async () => button("refresh").click());
  expect(button("edit").disabled).toBe(false);
});

it("masks direct credentials, toggles explicitly, and never pre-fills stored secrets", async () => {
  const saved = {
    ...registration(),
    auth_type: "bearer",
    credential_configured: true,
  };
  request.mockResolvedValueOnce(Response.json({ items: [saved] }));
  await act(async () =>
    root.render(<CollaboratorManager runtimeId="r-one" region="cn-beijing" />),
  );
  await act(async () => button("edit").click());
  const input = host.querySelector<HTMLInputElement>('input[type="password"]')!;
  expect(input).not.toBeNull();
  expect(input.value).toBe("");
  expect(input.required).toBe(false);
  const set = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )!.set!;
  await act(async () => {
    set.call(input, "new-credential");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => button("showSecret").click());
  expect(input.type).toBe("text");
  expect(input.value).toBe("new-credential");
  await act(async () => button("hideSecret").click());
  expect(input.type).toBe("password");
  request.mockResolvedValueOnce(Response.json({ ...saved, revision: 2 }));
  await act(async () =>
    host
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  const payload = JSON.parse(request.mock.calls.at(-1)![3]!.body as string);
  expect(payload.secret).toBe("new-credential");
  expect(payload).not.toHaveProperty("secret_env");
  expect(host.querySelector('input[type="password"]')).toBeNull();
  await act(async () => button("edit").click());
  expect(
    host.querySelector<HTMLInputElement>('input[type="password"]')!.value,
  ).toBe("");
  request.mockResolvedValueOnce(Response.json({ ...saved, revision: 3 }));
  await act(async () =>
    host
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(
    JSON.parse(request.mock.calls.at(-1)![3]!.body as string),
  ).not.toHaveProperty("secret");
});

it("clears credentials on authentication change and cancel", async () => {
  request.mockResolvedValueOnce(Response.json({ items: [] }));
  await act(async () =>
    root.render(<CollaboratorManager runtimeId="r-one" region="cn-beijing" />),
  );
  await act(async () => button("add").click());
  async function auth(value: string) {
    await act(async () => {
      const select = host.querySelector("select")!;
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }
  await auth("bearer");
  const input = host.querySelector<HTMLInputElement>('input[type="password"]')!;
  expect(input).not.toBeNull();
  expect(input.required).toBe(true);
  await act(async () => button("showSecret").click());
  await auth("api_key");
  expect(
    host.querySelector<HTMLInputElement>('input[type="password"]')!.value,
  ).toBe("");
  expect(host.textContent).toContain("enabledHelp");
  await act(async () => button("cancel").click());
  await act(async () => button("add").click());
  expect(host.querySelector('input[type="password"]')).toBeNull();
});
