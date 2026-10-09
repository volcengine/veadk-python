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
vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  const t = (key: string) => key;
  return { ...actual, useTranslation: () => ({ t }) };
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
async function mount(fillName = true) {
  await act(async () =>
    root.render(
      <MpaCreateDialog
        region="cn-beijing"
        onClose={() => {}}
        onCreated={() => {}}
      />,
    ),
  );
  if (
    fillName &&
    field("name") &&
    !field("name").disabled &&
    !field("name").value
  ) {
    await edit("name", "test-agent");
  }
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
  expect(button("previousStep")).toBeDefined();
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
  const originalId = field("name").value;
  await goToFinal();
  await act(async () => submitButton().click());
  expect(button("previousStep")).toBeDefined();
  await act(async () => button("previousStep").click());
  expect(field("pgHost").disabled).toBe(false);
  expect(field("pgHost").value).toBe("db.example");
  await act(async () => button("previousStep").click());
  expect(field("name").value).toBe(originalId);
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
it("edits the Runtime name and navigates the three creation steps", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  await mount();
  expect(field("name").value).toBe("test-agent");
  expect(field("name").disabled).toBe(false);
  expect(document.querySelector('input[name="agentId"]')).toBeNull();
  expect(field("runtimeImage")).not.toBeNull();
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
it("restores an unsubmitted name and request after reopening", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    pgHost: "db.example",
    pgPort: "5432",
  });
  await mount();
  await edit("name", "draft-agent");
  const requestId = JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!)
    .input.requestId;
  await act(async () => button("next").click());
  await edit("pgHost", "db.changed.example");
  await act(async () => root.render(null));
  await mount();
  expect(field("pgHost").value).toBe("db.changed.example");
  await act(async () => button("previousStep").click());
  expect(field("name").value).toBe("draft-agent");
  expect(field("name").disabled).toBe(false);
  expect(
    JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!).input
      .requestId,
  ).toBe(requestId);
});
it("removes browser-owned IDs but preserves editable image choices from unsubmitted drafts", async () => {
  const requestId = "12345678-90ab-4cde-8f01-23456789abcd";
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        requestId,
        agentId: "mi-1234567890ab",
        runtimeImage: "registry.example/old:v1",
        workerImage: "registry.example/old-worker:v1",
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
  expect(field("name").value).toBe("");
  const draft = JSON.parse(
    sessionStorage.getItem("mpa-create:cn-beijing")!,
  ).input;
  expect(draft.agentId).toBeUndefined();
  expect(draft.runtimeImage).toBe("registry.example/old:v1");
  expect(draft.workerImage).toBe("registry.example/old-worker:v1");
  expect(draft.requestId).toBe(requestId);
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
  expect(button("previousStep")).toBeDefined();
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
    expect(field("name").value).toBe("");
    expect(document.querySelector('input[name="agentId"]')).toBeNull();
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
    expect(stored.input.agentId).toBeUndefined();
    expect(stored.input.name).toBe("test-agent");
    expect(stored.input.requestId).not.toBe(oldInput.requestId);
    expect(stored.taskId).toBeUndefined();
    expect(JSON.stringify(stored)).not.toContain("private-test-key");
    await act(async () => root.render(null));
    await mount();
    await act(async () => button("previousStep").click());
    await act(async () => button("previousStep").click());
    expect(field("name").value).toBe("test-agent");
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
      name: "test-agent",
      requestId: stored.input.requestId,
    });
  },
);

it.each(["uncertain", "running", "cancelling", "unavailable"] as const)(
  "opens an editable new request from a %s task only on explicit action",
  async (state) => {
    const input = {
      region: "cn-beijing",
      requestId: "12345678-90ab-4cde-8f01-23456789abcd",
      agentId: "mi-1234567890ab4cde8f012345",
      description: "Old agent",
    };
    vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
      configured: true,
      region: "cn-beijing",
      runtimeImage: "registry.example/runtime:v2",
      workerImage: "registry.example/worker:v2",
      postgresMode: "auto",
    });
    sessionStorage.setItem(
      "mpa-create:cn-beijing",
      JSON.stringify({
        input,
        submitted: true,
        taskId: state === "uncertain" ? undefined : "old-task",
        step: 2,
      }),
    );
    if (state === "unavailable") {
      vi.mocked(api.getMpaCreation).mockRejectedValue(
        new Error("Task unavailable"),
      );
    } else if (state !== "uncertain") {
      vi.mocked(api.getMpaCreation).mockResolvedValue({
        ...input,
        taskId: "old-task",
        state,
        stage: "deploying",
      });
    }
    await mount();
    expect(field("tosBucket").disabled).toBe(true);
    expect(document.body.textContent).toContain(
      "myAgents.mpaCreate.newAgentDescription",
    );
    expect(
      JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!).input,
    ).toEqual(input);
    await act(async () => button("newAgent").click());
    expect(field("name").value).toBe("");
    expect(field("name").disabled).toBe(false);
    const stored = JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!);
    expect(stored.input.requestId).not.toBe(input.requestId);
    expect(stored.submitted).toBeUndefined();
    expect(stored.taskId).toBeUndefined();
    await edit("name", "new-agent");
    await goToFinal();
    expect(field("openvikingUrl").disabled).toBe(false);
    expect(field("tosAccessKey").disabled).toBe(false);
    expect(field("tosSecretKey").disabled).toBe(false);
    expect(field("tosBucket").disabled).toBe(false);
    await edit("tosBucket", "fresh-bucket");
    expect(field("tosBucket").value).toBe("fresh-bucket");
    expect(api.startMpaCreation).not.toHaveBeenCalled();
    expect(api.cancelMpaCreation).not.toHaveBeenCalled();
  },
);

it("ignores late old-task results after starting a new request", async () => {
  let resolve!: (task: api.MpaCreationTask) => void;
  vi.mocked(api.getMpaCreation).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  const input = {
    region: "cn-beijing",
    requestId: "old-request",
    agentId: "mi-old",
    description: "",
  };
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({ input, submitted: true, taskId: "old-task" }),
  );
  await mount();
  await act(async () => button("newAgent").click());
  const freshId = JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!)
    .input.requestId;
  await act(async () =>
    resolve({
      ...input,
      taskId: "old-task",
      state: "succeeded",
      stage: "verifying",
    }),
  );
  expect(field("name").value).toBe("");
  expect(field("name").disabled).toBe(false);
  expect(sessionStorage.getItem("mpa-create:cn-beijing")).toContain(freshId);
});

it("disables a new request while configuration is loading", async () => {
  vi.mocked(api.getMpaCreationConfig).mockReturnValue(new Promise(() => {}));
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        requestId: "old-request",
        agentId: "mi-old",
      },
      submitted: true,
    }),
  );
  await mount();
  expect(button("newAgent").disabled).toBe(true);
  await act(async () => button("newAgent").click());
  expect(
    JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!).input
      .requestId,
  ).toBe("old-request");
});

it("navigates restored submitted settings without unlocking or changing identity", async () => {
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        region: "cn-beijing",
        requestId: "saved-request",
        agentId: "mi-saved",
        runtimeImage: "registry.example/runtime:v1",
        workerImage: "registry.example/worker:v1",
        pgHost: "db.example",
        pgPort: "5432",
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
  await mount();
  const steps = () => [
    ...document.querySelectorAll<HTMLButtonElement>(".mpa-create-steps button"),
  ];
  expect(steps()).toHaveLength(3);
  await act(async () => steps()[0].click());
  expect(field("name").value).toBe("mi-saved");
  expect(field("name").disabled).toBe(true);
  expect(field("runtimeImage").disabled).toBe(true);
  await act(async () => steps()[1].click());
  expect(field("pgHost").disabled).toBe(true);
  await act(async () => steps()[2].click());
  expect(field("openvikingUrl")).toBeDefined();
  expect(api.startMpaCreation).not.toHaveBeenCalled();
  expect(
    JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!).input
      .requestId,
  ).toBe("saved-request");
});

it("validates forward step clicks and disables navigation during submission", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    pgHost: "db.example",
    pgPort: "5432",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  const steps = () => [
    ...document.querySelectorAll<HTMLButtonElement>(".mpa-create-steps button"),
  ];
  await edit("name", "invalid name");
  expect(steps()[1].disabled).toBe(true);
  expect(steps()[2].disabled).toBe(true);
  await edit("name", "valid-name");
  await act(async () => steps()[1].click());
  await edit("pgPort", "invalid");
  expect(steps()[0].disabled).toBe(false);
  expect(steps()[2].disabled).toBe(true);
  await edit("pgPort", "5432");
  await act(async () => steps()[2].click());
  await act(async () => submitButton().click());
  expect(steps().every((step) => step.disabled)).toBe(true);
  expect(button("previousStep").disabled).toBe(true);
  expect(button("newAgent").disabled).toBe(true);
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
it("passes complete TOS settings without saving credentials in session storage", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount();
  await goToFinal();
  await edit("tosAccessKey", "sensitive-ak");
  expect(submitButton().disabled).toBe(true);
  await edit("tosSecretKey", "sensitive-sk");
  await edit("tosBucket", "session-output");
  expect(submitButton().disabled).toBe(false);
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[0][0]).toMatchObject({
    tosAccessKey: "sensitive-ak",
    tosSecretKey: "sensitive-sk",
    tosBucket: "session-output",
  });
  const saved = sessionStorage.getItem("mpa-create:cn-beijing")!;
  expect(saved).not.toContain("sensitive-ak");
  expect(saved).not.toContain("sensitive-sk");
  expect(saved).toContain("session-output");
});
function submitButton() {
  return button("submit");
}
async function goToFinal() {
  if (field("name") && !field("name").value) await edit("name", "test-agent");
  await act(async () => button("next").click());
  await act(async () => button("next").click());
}
it.each(["abc", "a".repeat(65), "bad name", "中文名称", ""])(
  "blocks invalid Runtime name %s before forward navigation",
  async (name) => {
    vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
      configured: true,
      region: "cn-beijing",
    });
    await mount();
    await edit("name", name);
    expect(button("next").disabled).toBe(true);
    expect(field("name").getAttribute("aria-invalid")).toBe("true");
    expect(api.startMpaCreation).not.toHaveBeenCalled();
  },
);
it("retains submitted legacy image selections on lost-response retry", async () => {
  const input = {
    requestId: "old-request",
    agentId: "mi-existing",
    region: "cn-beijing",
    description: "",
    runtimeImage: "",
    workerImage: "registry.example/worker:custom",
  };
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({ input, submitted: true }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    runtimeImage: "registry.example/new:latest",
  });
  vi.mocked(api.startMpaCreation).mockRejectedValue(new Error("Response lost"));
  await mount();
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[0][0]).toEqual({
    ...input,
    openvikingApiKey: "",
  });
  await act(async () => root.render(null));
  await mount();
  await act(async () => submitButton().click());
  expect(vi.mocked(api.startMpaCreation).mock.calls[1][0]).toEqual({
    ...input,
    openvikingApiKey: "",
  });
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

it("requires a Runtime name and keeps server-generated IDs with selectable images", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
    runtimeImage: "registry.example/old:v1",
  });
  vi.mocked(api.startMpaCreation).mockReturnValue(new Promise(() => {}));
  await mount(false);
  expect(field("name").value).toBe("");
  expect(button("next").disabled).toBe(true);
  for (const removed of ["agentId"]) {
    expect(document.querySelector(`input[name="${removed}"]`)).toBeNull();
  }
  await edit("name", "  support-agent  ");
  await goToFinal();
  await act(async () => submitButton().click());
  const request = vi.mocked(api.startMpaCreation).mock.calls[0][0];
  expect(request.name).toBe("support-agent");
  expect(request.agentId).toBeUndefined();
  expect(request.runtimeImage).toBe("registry.example/old:v1");
  expect(request.workerImage).toBe("");
});

it("keeps composition and multiline description input from submitting the wizard", async () => {
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  await mount();
  const description = document.querySelector("textarea")!;
  await act(async () => {
    description.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    );
    Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )!.set!.call(description, "中文说明\n第二行");
    description.dispatchEvent(new Event("input", { bubbles: true }));
    description.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        isComposing: true,
        bubbles: true,
      }),
    );
    description.dispatchEvent(
      new CompositionEvent("compositionend", {
        bubbles: true,
        data: "中文说明",
      }),
    );
  });
  expect(description.value).toBe("中文说明\n第二行");
  expect(api.startMpaCreation).not.toHaveBeenCalled();
  expect(field("name")).not.toBeNull();
});

it("visibly disables Next for a Chinese name and restores it after correction", async () => {
  const { readFileSync } = await import("node:fs");
  const css = document.createElement("style");
  css.textContent = readFileSync(
    "src/components/primitives/Button/Button.css",
    "utf8",
  );
  document.head.append(css);
  try {
    vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
      configured: true,
      region: "cn-beijing",
    });
    await mount();
    await edit("name", "czh的测试agent");
    expect(button("next").disabled).toBe(true);
    expect(getComputedStyle(button("next")).opacity).toBe("0.45");
    expect(getComputedStyle(button("next")).cursor).toBe("not-allowed");
    expect(document.getElementById("mpa-name-help")?.getAttribute("role")).toBe(
      "alert",
    );
    await edit("name", "czh-test-agent");
    expect(button("next").disabled).toBe(false);
    expect(Number(getComputedStyle(button("next")).opacity || 1)).toBe(1);
    expect(
      document.getElementById("mpa-name-help")?.getAttribute("role"),
    ).toBeNull();
    await act(async () => button("next").click());
    expect(field("name")).toBeNull();
  } finally {
    css.remove();
  }
});

it("keeps disabled and loading appearance consistent across shared Button variants", async () => {
  const { readFileSync } = await import("node:fs");
  const { Button } = await import("../src/components/primitives/Button");
  const css = document.createElement("style");
  css.textContent = readFileSync(
    "src/components/primitives/Button/Button.css",
    "utf8",
  );
  document.head.append(css);
  try {
    const variants = [
      "primary",
      "secondary",
      "outline",
      "ghost",
      "link",
      "pill",
    ] as const;
    await act(async () =>
      root.render(
        <>
          {variants.map((variant) => (
            <Button key={variant} variant={variant} disabled>
              {variant}
            </Button>
          ))}
          <Button loading>Loading</Button>
        </>,
      ),
    );
    const buttons = [...host.querySelectorAll("button")];
    for (const control of buttons.slice(0, variants.length)) {
      expect(control.disabled).toBe(true);
      expect(getComputedStyle(control).opacity).toBe("0.45");
      expect(getComputedStyle(control).cursor).toBe("not-allowed");
    }
    expect(getComputedStyle(buttons.at(-1)!).opacity).toBe("0.65");
  } finally {
    css.remove();
  }
});

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
  expect(button("previousStep")).toBeDefined();
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

it("preserves the runtime role stage and actionable IAM error for retry", async () => {
  const input = {
    region: "cn-beijing",
    requestId: "12345678-90ab-4cde-8f01-23456789abcd",
    agentId: "mi-1234567890ab4cde8f012345",
    description: "",
  };
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({ input, submitted: true, step: 2, taskId: "iam-task" }),
  );
  vi.mocked(api.getMpaCreationConfig).mockResolvedValue({
    configured: true,
    region: "cn-beijing",
  });
  vi.mocked(api.getMpaCreation).mockResolvedValue({
    ...input,
    taskId: "iam-task",
    state: "failed",
    stage: "iam_role",
    error: "iamPermissionDenied",
  });
  await mount();
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.stages.iam_role",
  );
  expect(document.body.textContent).toContain(
    "myAgents.mpaCreate.iamPermissionDenied",
  );
  expect(button("retry").disabled).toBe(false);
  expect(
    JSON.parse(sessionStorage.getItem("mpa-create:cn-beijing")!).input.agentId,
  ).toBe(input.agentId);
});

it("passes the recovering request identity to config inspection", async () => {
  const requestId = "11111111-1111-4111-8111-111111111111";
  sessionStorage.setItem(
    "mpa-create:cn-beijing",
    JSON.stringify({
      input: {
        requestId,
        agentId: "mi-test",
        region: "cn-beijing",
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
  await mount();
  expect(api.getMpaCreationConfig).toHaveBeenCalledWith(
    "cn-beijing",
    expect.any(AbortSignal),
    requestId,
  );
});
