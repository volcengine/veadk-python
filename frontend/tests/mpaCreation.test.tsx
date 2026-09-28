// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { MpaCreateDialog } from "../src/ui/mpa-create/MpaCreateDialog";
import * as api from "../src/adk/mpaCreation";

vi.mock("../src/adk/mpaCreation", () => ({
  MpaCreationRequestError: class extends Error {
    constructor(
      readonly status: number,
      message: string,
    ) {
      super(message);
    }
  },
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
it("explains the separate management workspace only for configured split layouts", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    postgresLayout: "split-workspaces",
    adminWorkspaceName: "mpa_admin_workspace",
    adminDatabaseName: "mpa_admin_db",
  });
  await mount();
  await act(async () => button("next").click());
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.pgSplitDescription",
  );
  expect(document.body.textContent).not.toContain(
    "myAgents.mpaCreate.pgDescription",
  );
});
it("blocks creation when prerequisites are not configured", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: false,
    region: "cn-beijing",
    error: "Missing server profile",
  });
  await mount();
  expect(document.body.textContent).toContain("Missing server profile");
  await act(async () => button("next").click());
  await act(async () => button("next").click());
  expect(button("submit").disabled).toBe(true);
});
it("persists identity before submission and prevents repeated clicks", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  await goToFinal();
  const submit = button("submit");
  await act(async () => {
    submit.click();
    submit.click();
  });
  expect(api.startMpaCreation).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem("mpa-create:cn-beijing")).toContain(
    "requestId",
  );
});

it("ignores late configuration after unmount", async () => {
  let resolve!: (value: api.MpaCreationConfig) => void;
  vi.mocked(api.getMpaCreationConfig).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  await mount();
  await act(async () => root.render(null));
  await act(async () => resolve({ configured: true, region: "cn-beijing" }));
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(api.startMpaCreation).not.toHaveBeenCalled();
});

it("keeps submitted identity fixed when the POST response is lost", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  vi.mocked(api.startMpaCreation).mockRejectedValue(new Error("Response lost"));
  await mount();
  await goToFinal();
  const submit = button("submit");
  await act(async () => submit.click());
  const original = vi.mocked(api.startMpaCreation).mock.calls[0][0];
  expect(button("previousStep")).toBeUndefined();
  await act(async () => submit.click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[1][0]).toEqual(original);
});

it("unlocks the form after a definite validation rejection", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    pgHost: "db.example",
    pgPort: "5432",
  });
  vi.mocked(api.startMpaCreation).mockRejectedValue(
    new api.MpaCreationRequestError(400, "PG target does not match"),
  );
  await mount();
  const originalId = field("agentId").value;
  await goToFinal();
  await act(async () => submitButton().click());
  expect(button("previousStep")).toBeDefined();
  await act(async () => button("previousStep").click());
  expect(field("pgHost").disabled).toBe(false);
  expect(field("pgHost").value).toBe("db.example");
  await act(async () => button("previousStep").click());
  expect(field("agentId").value).toBe(originalId);
});

it("can omit the shared modal footer without overriding component styles", async () => {
  const { ModalLayout } = await import("../src/components/layouts/ModalLayout");
  await act(async () =>
    root.render(
      <ModalLayout title="Test" footer={null}>
        Body
      </ModalLayout>,
    ),
  );
  expect(host.querySelector("footer")).toBeNull();
  await act(async () =>
    root.render(<ModalLayout title="Test">Body</ModalLayout>),
  );
  expect(host.querySelector("footer")?.textContent).toContain("Confirm");
});

function field(name: string) {
  return document.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
}
async function edit(name: string, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(field(name), value);
    field(name).dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function button(label: string) {
  return [...document.querySelectorAll("button")].find(
    (candidate) => candidate.textContent === `myAgents.mpaCreate.${label}`,
  )!;
}
it("keeps the generated ID read only and navigates the three creation steps", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  await mount();
  const id = document.querySelector<HTMLInputElement>('input[name="agentId"]')!;
  expect(id.value).toMatch(/^mi-[0-9a-f]{24}$/);
  expect(id.readOnly).toBe(true);
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.runtimeImage",
  );
  await act(async () => button("next").click());
  expect(document.body.textContent).toContain("myAgents.mpaCreate.pgHost");
  expect(
    document.querySelector<HTMLAnchorElement>(
      "a[href='https://console.volcengine.com/aidap/region:aidap+cn-beijing/']",
    )?.target,
  ).toBe("_blank");
  await act(async () => button("next").click());
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.openvikingUrl",
  );
  expect(
    document.querySelector<HTMLAnchorElement>(
      "a[href^='https://console.volcengine.com/vikingdb/']",
    )?.target,
  ).toBe("_blank");
  expect(button("submit")).toBeDefined();
  await act(async () => button("previousStep").click());
  expect(document.body.textContent).toContain("myAgents.mpaCreate.pgHost");
  expect(api.startMpaCreation).not.toHaveBeenCalled();
});
it("restores an unsubmitted draft and its generated ID after reopening", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    pgHost: "db.example",
    pgPort: "5432",
  });
  await mount();
  const generatedId = field("agentId").value;
  await act(async () => button("next").click());
  await edit("pgHost", "db.changed.example");
  await act(async () => root.render(null));
  await mount();
  expect(field("pgHost").value).toBe("db.changed.example");
  await act(async () => button("previousStep").click());
  expect(field("agentId").value).toBe(generatedId);
  expect(field("agentId").readOnly).toBe(true);
});
it("restores the original ID length in unsubmitted short-ID drafts", async () => {
  const requestId = "12345678-90ab-4cde-8f01-23456789abcd";
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        requestId,
        agentId: "mi-1234567890ab",
        description: "Draft",
      },
      step: 1,
    }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  await mount();
  await act(async () => button("previousStep").click());
  expect(field("agentId").value).toBe("mi-1234567890ab4cde8f012345");
});
it("keeps a submitted short ID unchanged for task retry", async () => {
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        requestId: "12345678-90ab-4cde-8f01-23456789abcd",
        agentId: "mi-1234567890ab",
        description: "",
      },
      submitted: true,
      step: 2,
    }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  vi.mocked(api.startMpaCreation).mockRejectedValue(new Error("Response lost"));
  await mount();
  expect(button("previousStep")).toBeUndefined();
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[0][0].agentId).toBe(
    "mi-1234567890ab",
  );
});

it.each(["failed", "cancelled"] as const)(
  "starts a different agent after a %s task without changing the old task",
  async (state) => {
    const oldInput = {
      region: "cn-beijing",
      requestId: "12345678-90ab-4cde-8f01-23456789abcd",
      agentId: "mi-1234567890ab4cde8f012345",
      description: "Old agent",
    };
    sessionStorage.setItem(
      "mpa-create:cn-beijing",
      JSON.stringify({
        input: oldInput,
        taskId: "old-task",
        submitted: true,
        step: 2,
      }),
    );
    vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
      configured: true,
      region: "cn-beijing",
      runtimeImage: "registry.example/mpa:v1",
      workerImage: "registry.example/worker:v1",
    });
    vi.mocked(api.getMpaCreation).mockResolvedValue({
      ...oldInput,
      taskId: "old-task",
      state,
      stage: "network",
      error: "creationFailed",
    });
    await mount();
    await edit("openvikingApiKey", "private-test-key");
    expect(button("retry")).toBeDefined();
    await act(async () => button("newAgent").click());
    const freshId = field("agentId").value;
    expect(freshId).toMatch(/^mi-[0-9a-f]{24}$/);
    expect(freshId).not.toBe(oldInput.agentId);
    expect(field("runtimeImage").value).toBe("registry.example/mpa:v1");
    expect(field("workerImage").value).toBe("registry.example/worker:v1");
    await goToFinal();
    expect(field("openvikingApiKey").value).toBe("");
    expect(field("openvikingUrl").value).toBe("");
    expect(field("openvikingResourceId").value).toBe("");
    expect(document.body.textContent).not.toContain(
      "myAgents.mpaCreate.states.failed",
    );
    expect(document.body.textContent).not.toContain(
      "myAgents.mpaCreate.states.cancelled",
    );
    expect(api.startMpaCreation).not.toHaveBeenCalled();
    expect(api.cancelMpaCreation).not.toHaveBeenCalled();
    const stored = JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!);
    expect(stored.input.agentId).toBe(freshId);
    expect(stored.input.requestId).not.toBe(oldInput.requestId);
    expect(stored.taskId).toBeUndefined();
    expect(JSON.stringify(stored)).not.toContain("private-test-key");
    await act(async () => root.render(null));
    await mount();
    await act(async () => button("previousStep").click());
    await act(async () => button("previousStep").click());
    expect(field("agentId").value).toBe(freshId);
    expect(api.getMpaCreation).toHaveBeenCalledTimes(1);
    vi.mocked(api.startMpaCreation).mockImplementation(async (request) => ({
      ...request,
      taskId: "new-task",
      state: "running",
      stage: "network",
    }));
    await goToFinal();
    await act(async () => submitButton().click());
    expect(vi.mocked(api.startMpaCreation).mock.calls[0][0]).toMatchObject({
      agentId: freshId,
      requestId: stored.input.requestId,
    });
  },
);

it("does not offer a new identity for a running or uncertain task", async () => {
  const input = {
    region: "cn-beijing",
    requestId: "12345678-90ab-4cde-8f01-23456789abcd",
    agentId: "mi-1234567890ab4cde8f012345",
    description: "Old agent",
  };
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({ input, submitted: true, step: 2 }),
  );
  await mount();
  expect(button("newAgent")).toBeUndefined();
  await act(async () => root.render(null));
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({ input, taskId: "running-task", submitted: true, step: 2 }),
  );
  vi.mocked(api.getMpaCreation).mockResolvedValue({
    ...input,
    taskId: "running-task",
    state: "running",
    stage: "deploying",
  });
  await mount();
  expect(button("newAgent")).toBeUndefined();
});
it("passes PG and OpenViking selections to creation and keeps secrets out of session storage", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    pgHost: "db.example",
    pgPort: "5432",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  await act(async () => button("next").click());
  expect(field("pgHost").value).toBe("db.example");
  await edit("pgPort", "5433");
  await act(async () => button("next").click());
  await edit("openvikingUrl", "https://api.example.test/openviking");
  await edit("openvikingResourceId", "ov-test");
  await edit("openvikingApiKey", "private-ov-key-for-test");
  expect(field("openvikingApiKey").type).toBe("password");
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[0][0]).toMatchObject({
    pgHost: "db.example",
    pgPort: "5433",
    openvikingUrl: "https://api.example.test/openviking",
    openvikingResourceId: "ov-test",
    openvikingApiKey: "private-ov-key-for-test",
  });
  const saved = sessionStorage.getItem("mpa-create:cn-beijing")!;
  expect(saved).not.toContain("private-ov-key-for-test");
  expect(saved).not.toContain("apiKey");
  expect(saved).not.toContain("password");
});
it("blocks malformed OpenViking settings before submission", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  await mount();
  await goToFinal();
  expect(submitButton().disabled).toBe(false);
  await edit("openvikingApiKey", "test-key");
  expect(submitButton().disabled).toBe(true);
  await edit("openvikingApiKey", "");
  await edit("openvikingUrl", "http://insecure.example.test");
  expect(submitButton().disabled).toBe(true);
  await edit("openvikingUrl", "https://api.example.test:443/openviking");
  expect(submitButton().disabled).toBe(true);
  await edit("openvikingUrl", "https://api.example.test/openviking");
  expect(submitButton().disabled).toBe(true);
  await edit("openvikingResourceId", "ov-test");
  expect(submitButton().disabled).toBe(true);
  await edit("openvikingApiKey", "test-ov-key");
  expect(submitButton().disabled).toBe(false);
});
function submitButton() {
  return button("submit");
}
async function goToFinal() {
  await act(async () => button("next").click());
  await act(async () => button("next").click());
}
it("prefills both images and submits edits or an intentionally cleared default", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    runtimeImage: "registry.example/mpa:v1",
    workerImage: "registry.example/worker:v1",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  expect(field("runtimeImage").value).toBe("registry.example/mpa:v1");
  expect(field("workerImage").value).toBe("registry.example/worker:v1");
  await edit("runtimeImage", "registry.example/mpa:custom");
  await edit("workerImage", "");
  await goToFinal();
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[0][0]).toMatchObject({
    runtimeImage: "registry.example/mpa:custom",
    workerImage: "",
  });
  expect(button("previousStep")).toBeUndefined();
});
it("blocks malformed image references but allows empty values", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  await mount();
  await edit("runtimeImage", "https://repo?token=private");
  expect(button("next").disabled).toBe(true);
  expect(field("runtimeImage").getAttribute("aria-invalid")).toBe("true");
  await edit("runtimeImage", "");
  await goToFinal();
  expect(submitButton().disabled).toBe(false);
});
it("does not replace saved or cleared image choices when config reloads after a lost response", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    runtimeImage: "registry.example/mpa:v1",
    workerImage: "registry.example/worker:v1",
  });
  vi.mocked(api.startMpaCreation).mockRejectedValue(new Error("Response lost"));
  await mount();
  await edit("runtimeImage", "");
  await edit("workerImage", "registry.example/worker:custom");
  await goToFinal();
  await act(async () => submitButton().click());
  const original = vi.mocked(api.startMpaCreation).mock.calls[0][0];
  await act(async () => root.render(null));
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    runtimeImage: "registry.example/mpa:v2",
  });
  await mount();
  const saved = JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!);
  expect(saved.input.runtimeImage).toBe("");
  expect(saved.input.workerImage).toBe("registry.example/worker:custom");
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[1][0]).toEqual(original);
});

it("automatically prepares PG without reusing an unsubmitted PG draft", async () => {
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        agentId: "mi-test",
        requestId: "request-test",
        pgHost: "old.example",
        pgPort: "5432",
      },
      step: 0,
    }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    postgresMode: "auto",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  await act(async () => button("next").click());
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.pgAutoDescription",
  );
  expect(document.querySelector('input[name="pgHost"]')).toBeNull();
  await act(async () => button("next").click());
  await act(async () => button("submit").click());
  expect(api.startMpaCreation).toHaveBeenCalledTimes(1);
  const input = vi.mocked(api.startMpaCreation).mock.calls[0][0];
  expect(input.pgHost).toBe("");
  expect(input.pgPort).toBe("");
});

it("preserves submitted PG inputs and blocks retry after switching to automatic mode", async () => {
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        agentId: "mi-test",
        requestId: "request-test",
        pgHost: "old.example",
        pgPort: "5432",
      },
      submitted: true,
      step: 2,
    }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    postgresMode: "auto",
  });
  await mount();
  expect(button("submit").disabled).toBe(true);
  expect(sessionStorage.getItem("mpa-create:cn-beijing")).toContain(
    "old.example",
  );
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.pgModeChanged",
  );
  expect(api.startMpaCreation).not.toHaveBeenCalled();
});

it("shows the registry migration prerequisite without asking for PG inputs", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: false,
    region: "cn-beijing",
    postgresMode: "auto",
    postgresMigrationRequired: true,
  });
  await mount();
  await act(async () => button("next").click());
  expect(document.querySelector('input[name="pgHost"]')).toBeNull();
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.pgMigrationRequired",
  );
  await act(async () => button("next").click());
  expect(button("submit").disabled).toBe(true);
});
