// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CustomCreate } from "../src/create/CustomCreate";
import type { NewAgentWorkbenchProps } from "../src/create/NewAgentWorkbench";
import { emptyDraft } from "../src/create/types";
import type { DeploymentTaskUpdate } from "../src/ui/ProjectPreview";
import * as api from "../src/adk/client";

vi.mock("../src/adk/client");
vi.mock("../src/create/NewAgentWorkbench", () => ({
  NewAgentWorkbench: (props: NewAgentWorkbenchProps) => (
    <>
      <div>{props.deployError}</div>
      <button
        onClick={() =>
          props.onDeploy({
            sessionBackend: "local",
            sessionStorage: "in-memory",
            minInstance: 1,
            maxInstance: 1,
            authentication: { type: "api_key" },
            createEvaluationSets: false,
            resources: {
              tos: { mode: "auto" },
              cr: { mode: "auto" },
              codePipeline: { mode: "auto" },
            },
          })
        }
      >
        deploy
      </button>
    </>
  ),
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
const tasks: DeploymentTaskUpdate[] = [];
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.clearAllMocks();
  tasks.length = 0;
  vi.mocked(api.checkRuntimeNameAvailability).mockResolvedValue({
    available: true,
  });
  vi.mocked(api.generateAgentProject).mockResolvedValue({
    name: "quick-test",
    files: [],
  });
  vi.mocked(api.deployAgentkitProject).mockResolvedValue({
    runtimeId: "r-quick",
    region: "cn-beijing",
    url: "https://example.invalid",
    apiKey: "",
  });
  vi.mocked(api.listModelOptions).mockResolvedValue([]);
  vi.mocked(api.listModelApiKeys).mockResolvedValue([]);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it("quick creation remains general through build, failure and retry", async () => {
  const draft = {
    ...emptyDraft(),
    name: "quick_test",
    instruction: "Help users",
    deployment: { feishuEnabled: false, modelApiKeyId: "test-key-reference" },
  };
  vi.mocked(api.deployAgentkitProject).mockRejectedValueOnce(
    new Error("build failed"),
  );
  await act(async () =>
    root.render(
      <CustomCreate
        initialDraft={draft}
        freshCreationSurface="vulcan"
        onBack={() => {}}
        onCreate={() => {}}
        onDeploymentTaskChange={(task) => tasks.push(task)}
      />,
    ),
  );
  await act(async () => host.querySelector("button")!.click());
  expect(api.deployAgentkitProject, host.textContent || "").toHaveBeenCalled();
  expect(tasks.at(-1)?.status).toBe("error");
  await act(async () => tasks.at(-1)!.retry!());
  expect(api.deployAgentkitProject).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.anything(),
    expect.anything(),
    expect.objectContaining({ agentCategory: "general" }),
  );
  expect(api.applyMpaProfileAfterDeployment).not.toHaveBeenCalled();
  expect(tasks.at(-1)?.status).toBe("success");
  expect(tasks.every((task) => !task.mpaProfile && !task.mpaSmoke)).toBe(true);
});
