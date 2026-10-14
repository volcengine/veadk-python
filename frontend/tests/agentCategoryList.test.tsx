// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  MyAgents,
  invalidateRuntimeAgentCache,
  type MyAgentsProps,
} from "../src/ui/MyAgents";
import { emptyDraft } from "../src/create/types";
import * as api from "../src/adk/client";

vi.mock("../src/adk/client");
const { t, i18n } = vi.hoisted(() => ({
  t: (key: string) => key,
  i18n: { language: "en-US", resolvedLanguage: "en-US" },
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t, i18n }),
}));
let host: HTMLDivElement, root: Root;
const base: MyAgentsProps = {
  cloudProvider: "volcengine",
  studioRegion: "cn-beijing",
  canCreateRuntimeAgents: true,
  canCreatePersonalAgents: false,
  canUpdate: false,
  runtimeScope: "all",
  activeType: "general",
  onCreateAgent: vi.fn(),
  onUseAgent: vi.fn(),
  onViewAgentDetails: vi.fn(),
  onCreateSandboxAgent: vi.fn(),
  onUseSandboxAgent: vi.fn(),
  onViewSandboxAgentDetails: vi.fn(),
  onActiveTypeChange: vi.fn(),
  drafts: [
    {
      id: "general",
      draft: { ...emptyDraft(), name: "generic-draft" },
      updatedAt: 1,
    },
    {
      id: "mpa",
      draft: { ...emptyDraft(), name: "mpa-draft" },
      updatedAt: 1,
      deploymentTarget: {
        runtimeId: "r-test",
        name: "MPA",
        region: "cn-beijing",
        agentCategory: "mpa",
      },
    },
    {
      id: "legacy",
      draft: { ...emptyDraft(), name: "legacy-profile-draft" },
      updatedAt: 1,
      deploymentTarget: {
        runtimeId: "r-old",
        name: "old",
        region: "cn-beijing",
        mpaProfileOnly: true,
      },
    },
  ],
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.clearAllMocks();
  invalidateRuntimeAgentCache();
  vi.mocked(api.getRuntimes).mockResolvedValue({ runtimes: [], nextToken: "" });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it("filters drafts when switching categories and retains the generic creation entry", async () => {
  await act(async () => root.render(<MyAgents {...base} />));
  expect(host.textContent).toContain("generic-draft");
  expect(host.textContent).not.toContain("mpa-draft");
  const create = [...host.querySelectorAll("button")].find((node) =>
    node.textContent?.includes("myAgents.createAgent"),
  );
  expect(create).toBeTruthy();
  await act(async () => create!.click());
  expect(base.onCreateAgent).toHaveBeenCalledWith("cn-beijing", "general");
  await act(async () => root.render(<MyAgents {...base} activeType="mpa" />));
  expect(host.textContent).not.toContain("generic-draft");
  expect(host.textContent).toContain("mpa-draft");
  expect(host.textContent).toContain("legacy-profile-draft");
  await act(async () => root.render(<MyAgents {...base} />));
  expect(host.textContent).toContain("generic-draft");
  expect(host.textContent).not.toContain("legacy-profile-draft");
});
