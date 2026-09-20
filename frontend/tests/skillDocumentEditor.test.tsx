// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SkillDocumentEditor } from "../src/ui/mpa-agent-info/SkillDocumentEditor";
import { getSkillDocument, saveSkillDocument } from "../src/adk/skillDocuments";
vi.mock("../src/adk/skillDocuments", () => ({
  getSkillDocument: vi.fn(),
  saveSkillDocument: vi.fn(),
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
const load = vi.mocked(getSkillDocument),
  save = vi.mocked(saveSkillDocument);
const target = {
  spaceId: "bound-space",
  skillId: "skill",
  region: "cn-beijing",
  name: "Example",
};
let root: Root, host: HTMLDivElement;
const close = vi.fn(),
  changed = vi.fn();
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  load.mockReset();
  save.mockReset();
  close.mockReset();
  changed.mockReset();
  load.mockResolvedValue({
    content: "Original",
    baseVersion: "v1",
    canUpdate: true,
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
async function render() {
  await act(async () =>
    root.render(
      <SkillDocumentEditor target={target} onClose={close} onSaved={changed} />,
    ),
  );
}
function button(key: string) {
  return Array.from(document.querySelectorAll("button")).find(
    (b) => b.textContent === `agentTopology.${key}`,
  )!;
}
async function edit() {
  const area = document.querySelector("textarea")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )!.set!.call(area, "Changed");
    area.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
it("respects read-only permissions", async () => {
  load.mockResolvedValueOnce({
    content: "Read only",
    baseVersion: "v1",
    canUpdate: false,
  });
  await render();
  expect(document.querySelector("textarea")!.readOnly).toBe(true);
  expect(button("saveDocument")).toBeUndefined();
});
it("retains edits after save failure and retries the same version", async () => {
  await render();
  await edit();
  save.mockRejectedValueOnce(new Error("private error"));
  await act(async () => button("saveDocument").click());
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({
      ...target,
      content: "Changed",
      baseVersion: "v1",
    }),
  );
  expect(document.querySelector("textarea")!.value).toBe("Changed");
  expect(document.body.textContent).toContain(
    "agentTopology.documentSaveFailed",
  );
  expect(document.body.textContent).not.toContain("private error");
  save.mockResolvedValueOnce({ version: "v2" });
  await act(async () => button("saveDocument").click());
  expect(changed).toHaveBeenCalledOnce();
  expect(close).toHaveBeenCalledOnce();
});
it("cancels the read request on unmount", async () => {
  load.mockImplementationOnce(() => new Promise(() => {}));
  await render();
  const signal = load.mock.calls[0][0].signal!;
  await act(async () => root.render(null));
  expect(signal.aborted).toBe(true);
});

it("keeps unsaved text on Escape and does not interrupt IME composition", async () => {
  await render();
  await edit();
  await act(async () =>
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", isComposing: true }),
    ),
  );
  expect(close).not.toHaveBeenCalled();
  expect(button("discardChanges")).toBeUndefined();
  await act(async () =>
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })),
  );
  expect(button("discardChanges")).toBeDefined();
  await act(async () => button("keepEditing").click());
  expect(document.querySelector("textarea")!.value).toBe("Changed");
  expect(close).not.toHaveBeenCalled();
});

it("locks duplicate saves and closing until the write finishes", async () => {
  let finish!: (value: { version: string }) => void;
  save.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await render();
  await edit();
  await act(async () => {
    button("saveDocument").click();
    button("saveDocument").click();
  });
  expect(save).toHaveBeenCalledOnce();
  expect(document.querySelector("textarea")!.disabled).toBe(true);
  await act(async () =>
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })),
  );
  expect(close).not.toHaveBeenCalled();
  await act(async () => finish({ version: "v2" }));
  expect(close).toHaveBeenCalledOnce();
});

it("retries failed document reads", async () => {
  load.mockRejectedValueOnce(new Error("private diagnostic"));
  await render();
  expect(document.body.textContent).toContain(
    "agentTopology.documentLoadFailed",
  );
  expect(document.body.textContent).not.toContain("private diagnostic");
  await act(async () => button("refresh").click());
  expect(document.querySelector("textarea")!.value).toBe("Original");
});
