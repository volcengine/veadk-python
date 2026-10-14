// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  ProjectPreview,
  type ProjectPreviewProps,
  type DeploymentTaskUpdate,
} from "../src/ui/ProjectPreview";
import { emptyDraft } from "../src/create/types";
import * as api from "../src/adk/client";

vi.mock("../src/adk/client");
vi.mock("../src/create/AgentBuildCanvas", () => ({
  AgentBuildCanvas: () => null,
}));
vi.mock("../src/ui/CodeBrowserDialog", () => ({
  ProjectCodeBrowser: () => null,
}));
const { t, i18n } = vi.hoisted(() => ({
  t: (key: string) => key,
  i18n: { language: "en-US", resolvedLanguage: "en-US" },
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t, i18n }),
}));
let host: HTMLDivElement, root: Root;
const draft = { ...emptyDraft(), name: "general-test" };
const onDeploy = vi.fn();
const tasks: DeploymentTaskUpdate[] = [];
const base: ProjectPreviewProps = {
  project: { name: "general-test", files: [] },
  agentDraft: draft,
  onDeploy,
  showGitSync: false,
  showMessageChannels: false,
  showEvaluationSets: false,
  onDeploymentTaskChange: (task) => tasks.push(task),
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.clearAllMocks();
  tasks.length = 0;
  vi.mocked(api.checkRuntimeNameAvailability).mockResolvedValue({
    available: true,
  } as never);
  vi.mocked(api.listIdentityUserPools).mockResolvedValue([]);
  vi.mocked(api.applyMpaProfileAfterDeployment).mockRejectedValue(
    new Error("unexpected MPA request"),
  );
  onDeploy.mockResolvedValue({
    runtimeId: "r-general",
    region: "cn-beijing",
    url: "https://example.invalid",
    apiKey: "",
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
async function render(props: Partial<ProjectPreviewProps> = {}) {
  await act(async () => root.render(<ProjectPreview {...base} {...props} />));
}
async function click(label: string) {
  const button = [...document.querySelectorAll("button")].find(
    (node) => node.textContent?.trim() === label,
  );
  expect(button, label).toBeTruthy();
  await act(async () => button!.click());
}
async function deploy() {
  await click("projectPreview.deploy");
  await click("projectPreview.confirm.deploy");
}
it("generic structured creation never applies MPA Profile, including after failure and retry", async () => {
  onDeploy.mockRejectedValueOnce(new Error("build failed"));
  await render();
  await deploy();
  expect(host.textContent).toContain("build failed");
  expect(tasks.at(-1)?.status).toBe("error");
  expect(tasks.every((task) => !task.mpaProfile && !task.mpaSmoke)).toBe(true);
  await act(async () => tasks.at(-1)!.retry!());
  await click("projectPreview.confirm.deploy");
  expect(api.applyMpaProfileAfterDeployment).not.toHaveBeenCalled();
  expect(onDeploy).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.any(Function),
    expect.objectContaining({ agentCategory: "general" }),
  );
  expect(tasks.at(-1)?.status, JSON.stringify(tasks.at(-1))).toBe("success");
  expect(host.textContent).not.toContain(
    "projectPreview.steps.applyMpaProfile",
  );
  expect(host.textContent).not.toContain(
    "projectPreview.steps.verifyMpaRuntime",
  );
});
it("explicit MPA still calls Profile and displays its failure without declaring success", async () => {
  await render({ agentCategory: "mpa" });
  await deploy();
  expect(api.applyMpaProfileAfterDeployment).toHaveBeenCalledTimes(1);
  expect(onDeploy).toHaveBeenCalledWith(
    expect.anything(),
    expect.any(Function),
    expect.objectContaining({ agentCategory: "mpa" }),
  );
  expect(host.textContent).toContain("projectPreview.steps.applyMpaProfile");
  expect(tasks.at(-1)?.mpaProfile).toBe(true);
  expect(tasks.at(-1)?.status).toBe("error");
});

it("keeps generic updates out of MPA even when they have a legacy instance identifier", async () => {
  await render({
    deploymentRuntimeId: "r-general",
    deploymentMpaInstanceId: "mi-legacy",
  });
  await click("projectPreview.deploy");
  await click("projectPreview.confirm.update");
  expect(api.applyMpaProfileAfterDeployment).not.toHaveBeenCalled();
  expect(tasks.at(-1)?.status).toBe("success");
});
it.each([
  [new DOMException("cancelled", "AbortError"), "cancelled"],
  [new Error("Polling build status failed"), "running"],
])(
  "does not add MPA phases on cancellation or unconfirmed completion",
  async (error, status) => {
    onDeploy.mockRejectedValueOnce(error);
    await render();
    await deploy();
    expect(tasks.at(-1)?.status).toBe(status);
    expect(tasks.every((task) => !task.mpaProfile && !task.mpaSmoke)).toBe(
      true,
    );
    expect(api.applyMpaProfileAfterDeployment).not.toHaveBeenCalled();
  },
);
