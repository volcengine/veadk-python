// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { MpaCreationFailure } from "../src/ui/mpa-create/MpaCreationFailure";
import type { MpaCreationTask } from "../src/adk/mpaCreation";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
let host: HTMLDivElement, root: Root;
const task: MpaCreationTask = {
  taskId: "task",
  requestId: "request",
  description: "",
  region: "cn-beijing",
  state: "failed",
  stage: "deploying",
  error: "creationFailed",
  latestDiagnostic: {
    stage: "deploying",
    operation: "create_skill_space",
    category: "provider_error",
    attempt: 1,
    outcome: "failed",
    errorCode: "ExceededQuota",
    requestId: "20261020123456ABCDEF0123456789ABCD",
  },
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
it.each(["cn-beijing", "ap-southeast-1"])(
  "shows actionable identifiers without suggestions in %s",
  async (region) => {
    await act(async () =>
      root.render(<MpaCreationFailure task={{ ...task, region }} />),
    );
    expect(host.textContent).toContain("reasons.quota");
    expect(host.textContent).toContain("create_skill_space");
    expect(host.textContent).toContain("ExceededQuota");
    expect(host.textContent).toContain(task.latestDiagnostic!.requestId);
    expect(host.querySelector("details")).not.toBeNull();
  },
);
it.each(["succeeded", "running", "cancelled"] as const)(
  "renders nothing for %s even with old diagnostic",
  async (state) => {
    await act(async () =>
      root.render(<MpaCreationFailure task={{ ...task, state }} />),
    );
    expect(host.textContent).toBe("");
  },
);
it("ignores diagnostics from another stage or retrying calls", async () => {
  for (const diagnostic of [
    { ...task.latestDiagnostic!, stage: "worker" },
    { ...task.latestDiagnostic!, outcome: "retrying" },
  ]) {
    await act(async () =>
      root.render(
        <MpaCreationFailure task={{ ...task, latestDiagnostic: diagnostic }} />,
      ),
    );
    expect(host.textContent).not.toContain("ExceededQuota");
    expect(host.textContent).toContain("reasons.unknown");
  }
});
it("copies only displayed safe details and reports clipboard failures", async () => {
  const writeText = vi
    .fn()
    .mockRejectedValueOnce(new Error("denied"))
    .mockResolvedValueOnce(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  await act(async () => root.render(<MpaCreationFailure task={task} />));
  const copy = host.querySelector("button")!;
  await act(async () => copy.click());
  expect(host.textContent).toContain("copyFailed");
  await act(async () => copy.click());
  expect(host.textContent).toContain("copied");
  expect(writeText.mock.calls[1][0]).toContain("ExceededQuota");
  expect(writeText.mock.calls[1][0]).not.toContain("request\n");
});

it.each([
  ["iamPermissionDenied", "permission"],
  ["iamTrustConflict", "iamTrustConflict"],
  ["iamPolicyConflict", "iamPolicyConflict"],
  ["iamOwnershipConflict", "ownership"],
  ["iamConfigurationConflict", "configuration_changed"],
  ["tosBucketUnavailable", "tosBucketUnavailable"],
  ["runtimeNameCheckFailed", "nameCheckUnavailable"],
  ["openvikingCreateUnknown", "creationUnconfirmed"],
  ["openvikingModelEndpointsInvalid", "modelEndpoints"],
])("preserves the specific legacy reason for %s", async (error, reason) => {
  await act(async () =>
    root.render(
      <MpaCreationFailure
        task={{ ...task, error, latestDiagnostic: undefined }}
      />,
    ),
  );
  expect(host.textContent).toContain(`reasons.${reason}`);
  expect(host.textContent).not.toContain("reasons.unknown");
});


it("shows and copies safe exception/HTTP details for a failed task", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  await act(async () => root.render(<MpaCreationFailure task={{ ...task, latestDiagnostic: { ...task.latestDiagnostic!, exceptionType: "ApiError -> HTTPError", httpStatus: 502, responseType: "text/html" } }} />));
  expect(host.textContent).toContain("ApiError -> HTTPError");
  expect(host.textContent).toContain("502");
  expect(host.textContent).toContain("text/html");
  await act(async () => host.querySelector("button")!.click());
  expect(writeText.mock.calls[0][0]).toContain("ApiError -> HTTPError");
  expect(writeText.mock.calls[0][0]).toContain("502");
});


it("omits untrusted diagnostic details", async () => {
  await act(async () => root.render(<MpaCreationFailure task={{ ...task, latestDiagnostic: { ...task.latestDiagnostic!, exceptionType: "privateCredential", httpStatus: 999, responseType: "text/html; private" } }} />));
  expect(host.textContent).not.toContain("private");
  expect(host.textContent).not.toContain("999");
});
