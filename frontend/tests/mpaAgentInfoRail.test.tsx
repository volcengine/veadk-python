// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AgentInfo } from "../src/adk/client";
import { MpaAgentInfoRail } from "../src/ui/mpa-agent-info/MpaAgentInfoRail";
import { listSkillsInSpacePage } from "../src/create/skills/skillspace";
import { SkillManagementApiError } from "../src/adk/skills";

vi.mock("../src/create/skills/skillspace", () => ({
  listSkillsInSpacePage: vi.fn(),
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../src/create/SkillSpacePicker", () => ({
  SkillSpacePicker: () => null,
}));
vi.mock("../src/ui/SessionEnvironmentPicker", () => ({
  SessionEnvironmentPicker: () => null,
}));
const list = vi.mocked(listSkillsInSpacePage);
const info = (): AgentInfo => ({
  name: "MPA",
  description: "Agent description",
  model: "model",
  tools: [],
  skills: [{ name: "wrong generic skill", description: "" }],
  skillsPreviewSupported: true,
  subAgents: [],
  agentCategory: "mpa",
  mpa: {
    agentsMd: "# Real AGENTS.md\nUse the bound skills.",
    agentsMdStatus: "ready",
    skillSpacesStatus: "ready",
    skillSpaces: [{ id: "space-1", region: "cn-shanghai" }],
  },
});
const skill = (id: string) => ({
  skillId: id,
  skillName: id,
  skillDescription: `Description ${id}`,
  version: "1",
  skillStatus: "Ready",
});
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  list.mockReset();
  list.mockResolvedValue({
    items: [skill("bound")],
    totalCount: 1,
    page: 1,
    pageSize: 100,
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
async function render(value: AgentInfo, key = "runtime-a") {
  await act(async () =>
    root.render(
      <MpaAgentInfoRail
        key={key}
        info={value}
        loading={false}
        selectedSessionSkills={[
          {
            source: "skillspace",
            name: "temporary",
            folder: "temporary",
            skillSpaceId: "temp",
            skillId: "temp",
          },
        ]}
      />,
    ),
  );
}

it("uses real AGENTS.md and shows only bound skills", async () => {
  await render(info());
  expect(host.textContent).toContain("# Real AGENTS.md");
  expect(host.textContent).toContain("Description bound");
  expect(host.textContent).not.toContain("wrong generic skill");
  expect(host.textContent).not.toContain("temporary");
  expect(host.querySelector(".topo-capability-add-slot")).toBeNull();
  expect(
    host.querySelector(".topo-skills-card .topo-section-count")?.textContent,
  ).toBe("1");
  expect(list).toHaveBeenCalledWith(
    "space-1",
    expect.objectContaining({
      region: "cn-shanghai",
      signal: expect.any(AbortSignal),
    }),
  );
});
it.each(["general", undefined] as const)(
  "hides non-MPA/unknown rails and does not fetch skills (%s)",
  async (category) => {
    await render({ ...info(), agentCategory: category });
    expect(host.querySelector("aside")).toBeNull();
    expect(list).not.toHaveBeenCalled();
  },
);
it("loads every page and distinguishes an empty bound space", async () => {
  list
    .mockResolvedValueOnce({
      items: Array.from({ length: 100 }, (_, i) => skill(`skill-${i}`)),
      totalCount: 101,
      page: 1,
      pageSize: 100,
    })
    .mockResolvedValueOnce({
      items: [skill("last")],
      totalCount: 101,
      page: 2,
      pageSize: 100,
    });
  await render(info());
  expect(list).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain("Description last");
  expect(
    host.querySelector(".topo-skills-card .topo-section-count")?.textContent,
  ).toBe("101");
  await render(
    { ...info(), mpa: { ...info().mpa!, skillSpaces: [] } },
    "empty",
  );
  expect(host.textContent).toContain("agentTopology.noBoundSpace");
});
it("retains partial skills when later pages fail and retries", async () => {
  list
    .mockResolvedValueOnce({
      items: [skill("first")],
      totalCount: 2,
      page: 1,
      pageSize: 1,
    })
    .mockRejectedValueOnce(new Error("private raw server error"));
  await render(info());
  expect(host.textContent).toContain("Description first");
  expect(host.textContent).toContain("agentTopology.loadFailed");
  expect(host.textContent).not.toContain("private raw");
  const retry = host.querySelector<HTMLButtonElement>(".topo-refresh")!;
  await act(async () => retry.click());
  expect(host.textContent).toContain("Description bound");
  expect(host.textContent).not.toContain("agentTopology.loadFailed");
});
it("clears revoked data and distinguishes permission failures", async () => {
  await render(info());
  expect(host.textContent).toContain("Description bound");
  list.mockRejectedValueOnce(new SkillManagementApiError("private", 403));
  await act(async () =>
    host.querySelector<HTMLButtonElement>(".topo-refresh")!.click(),
  );
  expect(host.textContent).toContain("agentTopology.accessDenied");
  expect(host.textContent).not.toContain("Description bound");
  expect(
    host.querySelector(".topo-skills-card .topo-section-count"),
  ).toBeNull();
});
it("does not substitute document failures with generic instructions", async () => {
  await render({
    ...info(),
    mpa: { ...info().mpa!, agentsMd: null, agentsMdStatus: "unsupported" },
  });
  expect(host.textContent).toContain("agentTopology.documentUnsupported");
  expect(host.textContent).not.toContain("# Real AGENTS.md");
});
it("aborts and ignores late skills after changing Runtime", async () => {
  let finish!: (
    value: Awaited<ReturnType<typeof listSkillsInSpacePage>>,
  ) => void;
  list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await render(info());
  const signal = list.mock.calls[0][1].signal!;
  await render({ ...info(), name: "Second Runtime" }, "runtime-b");
  expect(signal.aborted).toBe(true);
  await act(async () =>
    finish({ items: [skill("stale")], totalCount: 1, page: 1, pageSize: 100 }),
  );
  expect(host.textContent).not.toContain("Description stale");
  expect(host.textContent).toContain("Second Runtime");
});
it("shows degraded listings as incomplete data", async () => {
  list.mockResolvedValueOnce({
    items: [skill("partial")],
    totalCount: 1,
    page: 1,
    pageSize: 100,
    degraded: true,
  });
  await render(info());
  expect(host.textContent).toContain("agentTopology.skillsDegraded");
});

it("renders document markup as literal text with whitespace preserved", async () => {
  const document = "# AGENTS.md\n\n<script>untrusted()</script>\n";
  await render({ ...info(), mpa: { ...info().mpa!, agentsMd: document } });
  expect(host.querySelector(".topo-agents-md-content")?.textContent).toBe(
    document,
  );
  expect(host.querySelector("script")).toBeNull();
});

it("reports a non-progressing page as failure rather than an empty list", async () => {
  list.mockResolvedValueOnce({
    items: [],
    totalCount: 5,
    page: 1,
    pageSize: 100,
  });
  await render(info());
  expect(host.textContent).toContain("agentTopology.loadFailed");
  expect(host.textContent).not.toContain("agentTopology.noBoundSkills");
});
