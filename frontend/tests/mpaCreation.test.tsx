// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { MpaCreateDialog } from "../src/ui/mpa-create/MpaCreateDialog";
import * as api from "../src/adk/mpaCreation";

vi.mock("../src/adk/mpaCreation", () => ({
  getMpaCreationConfig: vi.fn(),
  startMpaCreation: vi.fn(),
  getMpaCreation: vi.fn(),
  cancelMpaCreation: vi.fn(),
}));
vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});
let host: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
beforeEach(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  vi.clearAllMocks();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});
async function mount() {
  await act(async () =>
    root.render(
      <MpaCreateDialog
        region="cn-beijing"
        onClose={() => {}}
        onCreated={() => {}}
      />,
    ),
  );
}
it("blocks creation when prerequisites are not configured", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: false,
    region: "cn-beijing",
    error: "Missing server profile",
  });
  await mount();
  expect(document.body.textContent).toContain("Missing server profile");
  const button = [...document.querySelectorAll("button")].find(
    (b) => b.textContent === "myAgents.mpaCreate.submit",
  );
  expect(button?.disabled).toBe(true);
});
it("persists identity before submission and prevents repeated clicks", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  const button = [...document.querySelectorAll("button")].find(
    (b) => b.textContent === "myAgents.mpaCreate.submit",
  )!;
  await act(async () => {
    button.click();
    button.click();
  });
  expect(api.startMpaCreation).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem("mpa-create:cn-beijing")).toContain(
    "requestId",
  );
});

it("ignores late configuration after unmount", async () => {
  let resolve!: (value: api.MpaCreationConfig) => void;
  vi.mocked(api.getMpaCreationConfig).mockReturnValue(new Promise(r => { resolve = r; }));
  await mount();
  await act(async () => root.render(null));
  await act(async () => resolve({ configured: true, region: "cn-beijing" }));
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(api.startMpaCreation).not.toHaveBeenCalled();
});

it("keeps submitted identity fixed when the POST response is lost", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({ configured: true, region: "cn-beijing" });
  vi.mocked(api.startMpaCreation).mockRejectedValue(new Error("Response lost"));
  await mount();
  const button = [...document.querySelectorAll("button")].find(b => b.textContent === "myAgents.mpaCreate.submit")!;
  await act(async () => button.click());
  const original = vi.mocked(api.startMpaCreation).mock.calls[0][0];
  expect(document.querySelector<HTMLInputElement>('input')?.disabled).toBe(true);
  await act(async () => button.click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[1][0]).toEqual(original);
});

it("can omit the shared modal footer without overriding component styles", async () => {
  const { ModalLayout } = await import("../src/components/layouts/ModalLayout");
  await act(async () => root.render(<ModalLayout title="Test" footer={null}>Body</ModalLayout>));
  expect(host.querySelector("footer")).toBeNull();
  await act(async () => root.render(<ModalLayout title="Test">Body</ModalLayout>));
  expect(host.querySelector("footer")?.textContent).toContain("Confirm");
});
