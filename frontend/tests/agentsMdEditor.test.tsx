// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AgentsMdEditor } from "../src/ui/mpa-agent-info/AgentsMdEditor";
import { AgentsMdError, requestAgentsMdDocument } from "../src/adk/agentsMd";
vi.mock("../src/adk/agentsMd", async (original) => ({
  ...(await original<typeof import("../src/adk/agentsMd")>()),
  requestAgentsMdDocument: vi.fn(),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
const request = vi.mocked(requestAgentsMdDocument);
const target = { runtimeId: "runtime-a", region: "cn-beijing" };
let root: Root, host: HTMLDivElement;
const close = vi.fn(),
  saved = vi.fn();
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  request.mockReset();
  request.mockResolvedValue({ content: "original", revision: 2 });
  close.mockClear();
  saved.mockClear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
async function render() {
  await act(async () =>
    root.render(
      <AgentsMdEditor target={target} onClose={close} onSaved={saved} />,
    ),
  );
}
function button(key: string) {
  const node = Array.from(document.querySelectorAll("button")).find(
    (el) => el.textContent === `agentTopology.${key}`,
  );
  if (!node) throw new Error(key);
  return node;
}
async function click(key: string) {
  await act(async () => button(key).click());
}
async function edit(value: string) {
  const input = document.querySelector("textarea")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
it("loads persisted text and saves its revision, not other settings", async () => {
  await render();
  expect(document.querySelector("textarea")?.value).toBe("original");
  await edit("中文 instructions");
  await click("saveAgentsMd");
  expect(request).toHaveBeenLastCalledWith(target, expect.any(AbortSignal), {
    content: "中文 instructions",
    revision: 2,
  });
  expect(saved).toHaveBeenCalledOnce();
  expect(close).toHaveBeenCalledOnce();
});
it("retains draft on conflict and offers explicit reload", async () => {
  await render();
  await edit("draft");
  request.mockRejectedValueOnce(new AgentsMdError(409));
  await click("saveAgentsMd");
  expect(document.querySelector("textarea")?.value).toBe("draft");
  expect(document.body.textContent).toContain("agentTopology.agentsMdConflict");
  expect(close).not.toHaveBeenCalled();
  await click("refresh");
  expect(document.body.textContent).toContain("agentTopology.discardDocument");
});
it("requires confirmation to save an empty document", async () => {
  await render();
  await edit("");
  await click("saveAgentsMd");
  expect(request).toHaveBeenCalledTimes(1);
  expect(document.body.textContent).toContain(
    "agentTopology.agentsMdClearConfirm",
  );
  await click("confirmDocument");
  expect(request).toHaveBeenLastCalledWith(target, expect.any(AbortSignal), {
    content: "",
    revision: 2,
  });
});
it("cancels dirty edits without writing", async () => {
  await render();
  await edit("unsaved");
  await click("close");
  expect(close).not.toHaveBeenCalled();
  await click("confirmDocument");
  expect(close).toHaveBeenCalledOnce();
  expect(request).toHaveBeenCalledTimes(1);
});
it("reports unsupported runtimes and retries load failures", async () => {
  request.mockRejectedValueOnce(new AgentsMdError(404));
  await render();
  expect(document.body.textContent).toContain(
    "agentTopology.agentsMdEditUnsupported",
  );
  await click("refresh");
  expect(document.querySelector("textarea")?.value).toBe("original");
});
it("deduplicates saves and blocks submission during composition", async () => {
  await render();
  await edit("updated");
  const input = document.querySelector("textarea")!;
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    ),
  );
  await click("saveAgentsMd");
  expect(request).toHaveBeenCalledTimes(1);
  await act(async () =>
    input.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    ),
  );
  let finish: (value: { content: string; revision: number }) => void = () => {};
  request.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await act(async () => {
    button("saveAgentsMd").click();
    button("saveAgentsMd").click();
  });
  expect(request).toHaveBeenCalledTimes(2);
  await act(async () => finish({ content: "updated", revision: 3 }));
  expect(saved).toHaveBeenCalledOnce();
});
it("aborts pending reads on unmount without applying late results", async () => {
  let signal: AbortSignal | undefined;
  request.mockImplementationOnce((_target, s) => {
    signal = s;
    return new Promise(() => {});
  });
  await render();
  await act(async () => root.render(null));
  expect(signal?.aborted).toBe(true);
  expect(saved).not.toHaveBeenCalled();
});
