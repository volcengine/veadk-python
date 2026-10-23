// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { A2AAliasEditor } from "../src/ui/collaborating-agents/A2AAliasEditor";
import { useTranslation } from "react-i18next";
import zh from "../src/i18n/resources/zh-CN/collaboratingAgents.json";
import en from "../src/i18n/resources/en-US/collaboratingAgents.json";
import { requestCollaborators } from "../src/adk/client";
vi.mock("../src/adk/client", () => ({ requestCollaborators: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: vi.fn(() => ({ t: (key: string) => key })),
}));
let host: HTMLDivElement, root: Root;
const saved = vi.fn(),
  refresh = vi.fn();
function button(label: string) {
  const el = [...host.querySelectorAll("button")].find(
    (x) => x.textContent === label,
  );
  if (!el) throw Error(label);
  return el;
}
async function render(available = true) {
  await act(async () =>
    root.render(
      <A2AAliasEditor
        runtimeId="r-one"
        region="cn-beijing"
        spaceId="as-one"
        agentId="a-one"
        alias={null}
        revision={0}
        available={available}
        disabled={false}
        onBusy={() => {}}
        onSaved={saved}
        onRefresh={refresh}
      />,
    ),
  );
}
async function edit(value: string) {
  await act(async () => button("alias.edit").click());
  const input = host.querySelector("input");
  if (!input) throw Error("input");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  return input;
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
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  vi.mocked(requestCollaborators).mockReset();
  vi.mocked(useTranslation).mockReturnValue({
    t: (key: string) => key,
  } as ReturnType<typeof useTranslation>);
  saved.mockReset();
  refresh.mockReset();
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it("saves a registered Agent alias with its revision and supports clearing", async () => {
  await render();
  await edit("代码助手");
  vi.mocked(requestCollaborators).mockResolvedValue(
    Response.json({ alias: "代码助手", revision: 1 }),
  );
  await submit();
  expect(requestCollaborators).toHaveBeenCalledWith(
    "r-one",
    "cn-beijing",
    "/registry/aliases/a-one",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        space_id: "as-one",
        alias: "代码助手",
        revision: 0,
      }),
    }),
  );
  expect(saved).toHaveBeenCalledWith({ alias: "代码助手", revision: 1 });
  await edit("");
  vi.mocked(requestCollaborators).mockResolvedValue(
    Response.json({ alias: null, revision: 2 }),
  );
  await submit();
  expect(saved).toHaveBeenLastCalledWith({ alias: null, revision: 2 });
});
it("retains input on conflict and requires refresh", async () => {
  await render();
  await edit("代码助手");
  vi.mocked(requestCollaborators).mockResolvedValue(
    Response.json({ detail: "revision_conflict" }, { status: 409 }),
  );
  await submit();
  expect(host.textContent).toContain("alias.revisionConflict");
  expect(host.querySelector("input")?.value).toBe("代码助手");
  await act(async () => button("refresh").click());
  expect(refresh).toHaveBeenCalledOnce();
});
it("does not submit while composing or when the Runtime does not support aliases", async () => {
  await render();
  const input = await edit("代码助手");
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    ),
  );
  await submit();
  expect(requestCollaborators).not.toHaveBeenCalled();
  await act(async () => button("cancel").click());
  await render(false);
  expect(button("alias.edit").disabled).toBe(true);
  expect(host.textContent).toContain("alias.unavailable");
});
it("ignores a response after unmount and aborts its request", async () => {
  let resolve!: (r: Response) => void;
  vi.mocked(requestCollaborators).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  await render();
  await edit("助手");
  await submit();
  await submit();
  expect(requestCollaborators).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(requestCollaborators).mock.calls[0][3]?.signal;
  await act(async () => root.render(null));
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve(Response.json({ alias: "助手", revision: 1 })));
  expect(saved).not.toHaveBeenCalled();
});

it("cancels an in-flight save without treating it as confirmed", async () => {
  let resolve!: (value: Response) => void;
  vi.mocked(requestCollaborators).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  await render();
  await edit("助手");
  await submit();
  const signal = vi.mocked(requestCollaborators).mock.calls[0][3]?.signal;
  await act(async () => button("cancel").click());
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve(Response.json({ alias: "助手", revision: 1 })));
  expect(saved).not.toHaveBeenCalled();
  await act(async () => button("alias.edit").click());
  expect(button("save").disabled).toBe(true);
  expect(host.textContent).toContain("alias.failed");
});

it.each([zh, en])(
  "labels a registered member as an Agent alias without shared-account setup",
  async (resources) => {
    vi.mocked(useTranslation).mockReturnValue({
      t: (key: string) =>
        key.startsWith("alias.")
          ? resources.alias[key.slice(6) as keyof typeof resources.alias]
          : key,
    } as ReturnType<typeof useTranslation>);
    await render(false);
    expect(host.textContent).toContain(
      resources === zh ? "Agent 别名" : "Agent alias",
    );
    expect(host.textContent).not.toMatch(
      /共享管理库|共享别名|shared management database|Shared aliases/,
    );
    expect(button(resources.alias.edit).disabled).toBe(true);
  },
);
