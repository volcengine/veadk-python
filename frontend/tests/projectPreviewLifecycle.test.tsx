// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ProjectPreview, type ProjectPreviewProps } from "../src/ui/ProjectPreview";
import { emptyDraft } from "../src/create/types";
import * as api from "../src/adk/client";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  const t = (key: string) => key;
  return { ...actual, useTranslation: () => ({ t }) };
});
vi.mock("../src/adk/client", () => ({
  applyMpaProfileAfterDeployment: vi.fn(),
  retryMpaAgentOperation: vi.fn(),
  checkRuntimeNameAvailability: vi.fn(),
  listIdentityUserPools: vi.fn(),
  revealModelApiKey: vi.fn(),
  bindGithubCicdRuntime: vi.fn(),
  initializeGithubDeliveryMain: vi.fn(),
  syncGithubCicdRuntime: vi.fn(),
  RuntimeProbeError: class extends Error {},
}));
vi.mock("../src/telemetry", () => ({
  beginAgentDeploy: () => ({ succeed: vi.fn(), fail: vi.fn() }),
  beginAgentSourceDownload: vi.fn(),
  classifyTelemetryError: () => ({}),
  safeTelemetryErrorMessage: (error: Error) => error.message,
}));
vi.mock("../src/create/AgentBuildCanvas", () => ({ AgentBuildCanvas: () => null }));
vi.mock("../src/ui/CodeBrowserDialog", () => ({ ProjectCodeBrowser: () => null }));
vi.mock("../src/ui/GithubCicdPanel", () => ({ GithubCicdPanel: () => null }));

let host: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.resetAllMocks();
  vi.mocked(api.checkRuntimeNameAvailability).mockResolvedValue({ available: true });
  vi.mocked(api.applyMpaProfileAfterDeployment).mockResolvedValue({
    operationId: "fixture-profile", status: "succeeded", stage: "runnable",
  } as Awaited<ReturnType<typeof api.applyMpaProfileAfterDeployment>>);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});
function button(text: string) {
  const element = [...document.querySelectorAll("button")].find((node) => node.textContent?.trim() === text);
  expect(element, text).toBeDefined();
  return element!;
}
async function deploy(overrides: Partial<ProjectPreviewProps> = {}) {
  const onDeploy = vi.fn().mockResolvedValue({ runtimeId: "fixture-runtime", region: "cn-beijing" });
  const onDeploymentTaskChange = vi.fn();
  const onDeploymentComplete = vi.fn();
  const props = {
    project: { name: "fixture-agent", files: [{ path: "agent.py", content: "# fixture" }] },
    agentDraft: { ...emptyDraft(), name: "fixture-agent" },
    deploymentRuntimeId: "fixture-runtime",
    showGitSync: false, showMessageChannels: false, showEvaluationSets: false,
    onDeploy, onDeploymentTaskChange, onDeploymentComplete,
    ...overrides,
  };
  await act(async () => root.render(<ProjectPreview {...props} />));
  await act(async () => button("projectPreview.deploy").click());
  await act(async () => button(props.deploymentRuntimeId ? "projectPreview.confirm.update" : "projectPreview.confirm.deploy").click());
  return { onDeploy, onDeploymentComplete, tasks: onDeploymentTaskChange.mock.calls.map(([task]) => task) };
}
it("completes a source-preserving update once without Profile calls, stages or retries", async () => {
  vi.mocked(api.applyMpaProfileAfterDeployment).mockRejectedValue(new Error("mpa_operation_service_unavailable"));
  const { onDeploy, onDeploymentComplete, tasks } = await deploy({ deploymentEditMode: "source-preserving" });
  expect(onDeploy).toHaveBeenCalledTimes(1);
  expect(api.applyMpaProfileAfterDeployment).not.toHaveBeenCalled();
  expect(api.retryMpaAgentOperation).not.toHaveBeenCalled();
  expect(onDeploymentComplete).toHaveBeenCalledTimes(1);
  expect(tasks.at(-1)).toMatchObject({ status: "success", phase: "complete", mpaProfile: false, mpaSmoke: false });
  expect(tasks.every((task) => !task.mpaProfile && !task.mpaSmoke && !task.retry && !["profile_applying", "smoke_running", "runnable"].includes(task.phase))).toBe(true);
});
it("retains Profile application for regenerate updates", async () => {
  const { tasks } = await deploy({ deploymentEditMode: "regenerate", deploymentRuntimeRevision: "revision-fixture" });
  expect(api.applyMpaProfileAfterDeployment).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ operationKind: "update", runtimeId: "fixture-runtime", runtimeRevision: "revision-fixture" }));
  expect(tasks.at(-1)).toMatchObject({ status: "success", mpaProfile: true, mpaSmoke: false });
});
it("does not hide a real MPA Profile failure or complete the failed operation", async () => {
  vi.mocked(api.applyMpaProfileAfterDeployment).mockRejectedValue(new Error("mpa_operation_service_unavailable"));
  const { tasks, onDeploymentComplete } = await deploy({ deploymentEditMode: "regenerate" });
  expect(api.applyMpaProfileAfterDeployment).toHaveBeenCalledTimes(1);
  expect(tasks.at(-1)).toMatchObject({ status: "error", phase: "profile_applying" });
  expect(tasks.some((task) => task.status === "success")).toBe(false);
  expect(onDeploymentComplete).not.toHaveBeenCalled();
});
it("retains create Profile and smoke stages for a new MPA deployment", async () => {
  const { tasks } = await deploy({ deploymentRuntimeId: undefined });
  expect(api.applyMpaProfileAfterDeployment).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ operationKind: "create" }));
  expect(tasks.at(-1)).toMatchObject({ status: "success", phase: "runnable", mpaProfile: true, mpaSmoke: true });
});
it("does not add MPA lifecycle to a code package without a draft", async () => {
  const { tasks } = await deploy({ agentDraft: undefined });
  expect(api.applyMpaProfileAfterDeployment).not.toHaveBeenCalled();
  expect(tasks.at(-1)).toMatchObject({ status: "success", phase: "complete", mpaProfile: false });
});
