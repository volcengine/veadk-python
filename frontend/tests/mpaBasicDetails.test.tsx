// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AgentWorkspace, type AgentWorkspaceProps } from "../src/ui/AgentWorkspace";
import * as api from "../src/adk/client";

vi.mock("../src/adk/client");
vi.mock("../src/create/AgentBuildCanvas", () => ({ AgentBuildCanvas: () => <div>execution-flow</div> }));
vi.mock("../src/ui/Markdown", () => ({ Markdown: () => null }));
const { t, i18n } = vi.hoisted(() => ({ t: (key: string) => key, i18n: { language: "en-US", resolvedLanguage: "en-US" } }));
vi.mock("react-i18next", async (importOriginal) => ({ ...(await importOriginal<typeof import("react-i18next")>()), useTranslation: () => ({ t, i18n }) }));
let host: HTMLDivElement, root: Root;
const agent = { id: "mpa-one", app: "default", label: "MPA one", remote: true, agentCategory: "mpa" as const, runtimeId: "r-one", mpaInstanceId: "mi-one" };
const info = { name: "MPA one", description: "Basic description", tools: [], subAgents: [], model: "test" };
const base: AgentWorkspaceProps = {
  agents: [agent], selectedAgentId: agent.id, focusedAgentId: agent.id,
  agentInfo: info, agentInfoAgentId: agent.id, loadingAgentInfo: false,
  canCreate: false, canUpdate: true, canViewUsage: true, detailOnly: true,
  onSelectAgent: vi.fn(), onCreateAgent: vi.fn(), onUpdateAgent: vi.fn(),
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.clearAllMocks();
  vi.mocked(api.getRuntimeAgentInfo).mockResolvedValue(info);
  vi.mocked(api.getRuntimeDetail).mockResolvedValue({ runtimeId: "r-one", status: "Ready", networkTypes: ["public"], envs: [] } as never);
  vi.mocked(api.getRuntimeUpdateCapability).mockResolvedValue({ canUpdate: false } as never);
  // Any accidental Profile read must be observable, without introducing retries.
  vi.mocked(api.getMpaAgentView).mockRejectedValue(new Error("Profile API must not be called"));
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); });
async function render(props: Partial<AgentWorkspaceProps> = {}) {
  await act(async () => root.render(<AgentWorkspace {...base} {...props} />));
}
const hidden = ["profileConfig", "sessionConfig", "usage", "diagnostics", "evaluations", "optimizations", "integrations", "versions"] as const;
it.each(["basic", ...hidden] as const)("keeps MPA %s focus on basic without Profile requests", async (focusedAgentSection) => {
  await render({ focusedAgentSection });
  expect(host.textContent).toContain("agentWorkspace.sections.basic");
  expect(host.textContent).toContain("execution-flow");
  for (const section of hidden) expect(host.textContent).not.toContain(`agentWorkspace.sections.${section}`);
  expect(host.textContent).not.toContain("agentWorkspace.profileConfig");
  expect(host.textContent).not.toContain("agentWorkspace.mpaControlPlane");
  expect(api.getMpaAgentView).not.toHaveBeenCalled();
  expect(api.getMpaProfileStatus).not.toHaveBeenCalled();
  expect(api.startMpaAgentOperation).not.toHaveBeenCalled();
  expect(api.getMpaSessionExecutionConfig).not.toHaveBeenCalled();
});
it("preserves general navigation and suppresses stale sections when switching to MPA", async () => {
  const general = { ...agent, id: "general", agentCategory: "general" as const };
  await render({ agents: [general], selectedAgentId: general.id, focusedAgentId: general.id, agentInfoAgentId: general.id });
  expect(host.textContent).toContain("agentWorkspace.sections.integrations");
  expect(host.textContent).toContain("agentWorkspace.sections.versions");
  await render({ focusedAgentSection: "sessionConfig" });
  expect(host.textContent).toContain("execution-flow");
  expect(host.textContent).not.toContain("agentWorkspace.sections.integrations");
  expect(api.getMpaAgentView).not.toHaveBeenCalled();
  expect(api.getMpaProfileStatus).not.toHaveBeenCalled();
});
