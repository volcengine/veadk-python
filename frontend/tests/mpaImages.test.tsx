// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { MpaImageUpdates } from "../src/ui/mpa-images/MpaImageUpdates";
import * as api from "../src/adk/client";
import { validImageReference } from "../src/adk/mpaImages";
import "../src/i18n";
import { i18n } from "../src/i18n/runtime";

vi.mock("../src/adk/client", () => ({ requestMpaImage: vi.fn() }));
const repo = (component: string) => `registry.example/mpa/${component}`;
let host: HTMLDivElement, root: Root;
function detail(component: string, extra = {}) {
  return {
    component,
    resourceId: component === "runtime" ? "r-one" : "t-one",
    repository: repo(component),
    currentImage: repo(component) + ":old",
    status: "Ready",
    revision: "revision",
    canUpdate: true,
    reason: "",
    operation: null,
    ...extra,
  };
}
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}
beforeEach(async () => {
  vi.stubGlobal("React", React);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  await i18n.changeLanguage("en-US");
  vi.mocked(api.requestMpaImage)
    .mockReset()
    .mockImplementation(async (_id, _region, component, suffix, init) => {
      if (init?.method === "POST")
        return response(
          detail(component, {
            canUpdate: false,
            operation: { phase: "submitted", target: repo(component) + ":new" },
          }),
        );
      if (suffix?.startsWith("/versions"))
        return response({
          repository: repo(component),
          tags: ["new", "old"],
          nextCursor: "",
        });
      return response(detail(component));
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
async function render(id = "r-one") {
  await act(async () =>
    root.render(
      <MpaImageUpdates key={id} runtimeId={id} region="cn-beijing" />,
    ),
  );
}
const button = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent === text)!;
async function choose(component: string, tag = "new") {
  const select = host.querySelector<HTMLSelectElement>(
    `[data-component="${component}"] select`,
  )!;
  await act(async () => {
    select.value = tag;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
it.each(["runtime", "worker"] as const)(
  "updates only %s after confirmation",
  async (component) => {
    await render();
    await choose(component);
    const card = host.querySelector(`[data-component="${component}"]`)!;
    await act(async () =>
      [...card.querySelectorAll("button")]
        .find((b) => b.textContent === "Update image")!
        .click(),
    );
    expect(api.requestMpaImage).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.anything(),
      expect.anything(),
      expect.objectContaining({ method: "POST" }),
    );
    expect(document.body.textContent).toContain(repo(component) + ":new");
    await act(async () => button("Confirm update").click());
    const writes = vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(writes[0][2]).toBe(component);
    expect(JSON.parse(writes[0][4]!.body as string)).toEqual({
      tag: "new",
      revision: "revision",
    });
    expect(host.textContent).toContain("Submitted");
    expect(host.textContent).toContain(
      "Existing sandbox sessions may keep their current Worker image",
    );
  },
);
it("keeps catalog failure separate and supports retry", async () => {
  vi.mocked(api.requestMpaImage)
    .mockImplementationOnce(async () => response(detail("runtime")))
    .mockImplementationOnce(async () =>
      response({ detail: { reason: "catalog_failed" } }, 502),
    );
  await render();
  expect(host.textContent).toContain("Unable to load public image versions");
  expect(host.textContent).toContain(repo("runtime") + ":old");
  await act(async () => button("Refresh versions").click());
  expect(host.textContent).not.toContain(
    "Unable to load public image versions",
  );
});
it("shows successful empty catalogs alongside the manual alternative", async () => {
  vi.mocked(api.requestMpaImage).mockImplementation(
    async (_id, _reg, comp, suffix) =>
      response(
        suffix?.startsWith("/versions")
          ? { repository: repo(comp), tags: [], nextCursor: "" }
          : detail(comp),
      ),
  );
  await render();
  expect(host.textContent).toContain("No public versions found");
  expect(host.textContent).toContain("Image address (manual)");
});
it("blocks unknown writes until explicit status reconciliation and never retries", async () => {
  const original = vi.mocked(api.requestMpaImage).getMockImplementation()!;
  vi.mocked(api.requestMpaImage).mockImplementation((...args) =>
    args[4]?.method === "POST"
      ? Promise.resolve(
          response({ detail: { reason: "outcome_unknown" } }, 502),
        )
      : original(...args),
  );
  await render();
  await choose("runtime");
  await act(async () => button("Update image").click());
  await act(async () => button("Confirm update").click());
  expect(document.body.textContent).toContain("could not be confirmed");
  expect(button("Confirm update").disabled).toBe(true);
  await act(async () =>
    document
      .querySelector<HTMLButtonElement>('button[aria-label="Close"]')!
      .click(),
  );
  expect(
    vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST"),
  ).toHaveLength(1);
});
it("aborts reads when switching Agent and ignores late responses", async () => {
  const pending: {
    resolve: (value: Response) => void;
    signal?: AbortSignal | null;
  }[] = [];
  vi.mocked(api.requestMpaImage).mockImplementation(
    (_id, _region, component, _suffix, init) =>
      new Promise((resolve) => pending.push({ resolve, signal: init?.signal })),
  );
  await render();
  const old = [...pending];
  await render("r-two");
  expect(old.every((p) => p.signal?.aborted)).toBe(true);
  await act(async () =>
    old.forEach((p) =>
      p.resolve(response(detail("runtime", { currentImage: "stale-image" }))),
    ),
  );
  expect(host.textContent).not.toContain("stale-image");
});
it("does not allow a disabled shared Worker update", async () => {
  const original = vi.mocked(api.requestMpaImage).getMockImplementation()!;
  vi.mocked(api.requestMpaImage).mockImplementation((...args) =>
    !args[3] && args[2] === "worker"
      ? Promise.resolve(
          response(detail("worker", { canUpdate: false, reason: "ownership" })),
        )
      : original(...args),
  );
  await render();
  await choose("worker");
  const card = host.querySelector('[data-component="worker"]')!;
  expect(
    [...card.querySelectorAll("button")].find(
      (b) => b.textContent === "Update image",
    )!.disabled,
  ).toBe(true);
  expect(card.textContent).toContain("exclusively owned");
});

it("closing a pending submission marks it uncertain and ignores a late acknowledgement", async () => {
  const original = vi.mocked(api.requestMpaImage).getMockImplementation()!;
  let finish: (response: Response) => void = () => {};
  let signal: AbortSignal | null | undefined;
  vi.mocked(api.requestMpaImage).mockImplementation((...args) => {
    if (args[4]?.method !== "POST") return original(...args);
    signal = args[4].signal;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  await render();
  await choose("runtime");
  await act(async () => button("Update image").click());
  await act(async () => button("Confirm update").click());
  expect(document.body.textContent).toContain("Submitting…");
  await act(async () =>
    document
      .querySelector<HTMLButtonElement>('button[aria-label="Close"]')!
      .click(),
  );
  expect(signal?.aborted).toBe(true);
  await act(async () =>
    finish(response(detail("runtime", { currentImage: "late-image" }))),
  );
  expect(host.textContent).not.toContain("late-image");
  expect(host.textContent).toContain("could not be confirmed");
  const runtimeCard = host.querySelector('[data-component="runtime"]')!;
  expect(
    [...runtimeCard.querySelectorAll("button")].find(
      (b) => b.textContent === "Update image",
    )!.disabled,
  ).toBe(true);
});

it("manual input and IME Enter never submit an image update", async () => {
  await render();
  const input = host.querySelector<HTMLInputElement>('input[type="text"]')!;
  await act(async () => {
    input.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    );
    input.dispatchEvent(
      new KeyboardEvent("keydown", {
        bubbles: true,
        key: "Enter",
        isComposing: true,
        keyCode: 229,
      }),
    );
    input.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    );
    input.dispatchEvent(
      new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }),
    );
  });
  expect(
    vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST"),
  ).toHaveLength(0);
});

async function enterImage(component: string, image: string) {
  const input = host.querySelector<HTMLInputElement>(
    `[data-component="${component}"] input[type="text"]`,
  )!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, image);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
it("clears the other source in both directions without affecting the other component", async () => {
  await render();
  await choose("runtime");
  await choose("worker");
  await enterImage("runtime", "registry.example/team/image:v1");
  expect(
    host.querySelector<HTMLSelectElement>('[data-component="runtime"] select')!
      .value,
  ).toBe("");
  expect(
    host.querySelector<HTMLSelectElement>('[data-component="worker"] select')!
      .value,
  ).toBe("new");
  await choose("runtime");
  expect(
    host.querySelector<HTMLInputElement>('[data-component="runtime"] input')!
      .value,
  ).toBe("");
});
it.each(["runtime", "worker"] as const)(
  "submits a manual %s image after explicit confirmation",
  async (component) => {
    await render();
    const image = "registry.example/team/image:Release_1";
    await enterImage(component, image);
    const card = host.querySelector(`[data-component="${component}"]`)!;
    await act(async () =>
      [...card.querySelectorAll("button")]
        .find((b) => b.textContent === "Update image")!
        .click(),
    );
    expect(document.querySelector('[role="dialog"]')!.textContent).toContain(
      image,
    );
    await act(async () => button("Confirm update").click());
    const writes = vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(writes[0][2]).toBe(component);
    expect(JSON.parse(writes[0][4]!.body as string)).toEqual({
      image,
      revision: "revision",
    });
  },
);
it("valid manual addresses stay available during catalog loading and failure", async () => {
  const original = vi.mocked(api.requestMpaImage).getMockImplementation()!;
  let rejectCatalog: (response: Response) => void = () => {};
  vi.mocked(api.requestMpaImage).mockImplementation((...args) =>
    args[2] === "runtime" && args[3]?.startsWith("/versions")
      ? new Promise((resolve) => {
          rejectCatalog = resolve;
        })
      : original(...args),
  );
  await render();
  await enterImage("runtime", "registry.example/team/image:v1");
  const card = host.querySelector('[data-component="runtime"]')!;
  const update = [...card.querySelectorAll("button")].find(
    (b) => b.textContent === "Update image",
  )!;
  expect(update.disabled).toBe(false);
  await act(async () =>
    rejectCatalog(response({ detail: { reason: "catalog_failed" } }, 502)),
  );
  expect(update.disabled).toBe(false);
  await act(async () =>
    [...card.querySelectorAll("button")]
      .find((b) => b.textContent === "Refresh versions")!
      .click(),
  );
  expect(card.querySelector<HTMLInputElement>("input")!.value).toBe(
    "registry.example/team/image:v1",
  );
});
it("invalid manual addresses disable submission and expose a format error on blur", async () => {
  await render();
  await enterImage(
    "runtime",
    "https://registry.example/team/image:v1?token=secret",
  );
  const card = host.querySelector('[data-component="runtime"]')!;
  await act(async () =>
    card
      .querySelector("input")!
      .dispatchEvent(new FocusEvent("focusout", { bubbles: true })),
  );
  expect(
    [...card.querySelectorAll("button")].find(
      (b) => b.textContent === "Update image",
    )!.disabled,
  ).toBe(true);
  expect(card.textContent).toContain("Enter a complete image address");
  expect(
    vi
      .mocked(api.requestMpaImage)
      .mock.calls.some((c) => c[4]?.method === "POST"),
  ).toBe(false);
});

it.each([
  ["registry.example/team/image:v1", true],
  ["registry.example:5000/team/image:Release_1", true],
  ["ghcr.io/org/team/image:1.2.3", true],
  ["localhost:5000/team/image:latest", true],
  ["https://registry.example/team/image:v1", false],
  ["registry.example/team/image", false],
  ["user:password@registry.example/team/image:v1", false],
  ["registry.example/team/image:v1?token=secret", false],
  ["registry.example/team/image:v1#fragment", false],
  ["registry.example/team/image:v1\n", false],
  ["registry.example:65536/team/image:v1", false],
  ["registry.example:0/team/image:v1", false],
  ["registry.example/Team/image:v1", false],
  ["registry.example/team/image@sha256:" + "a".repeat(64), false],
  ["registry.example/team/../image:v1", false],
  ["x".repeat(2049), false],
] as const)("validates manual reference %s as %s", (image, expected) => {
  expect(validImageReference(image)).toBe(expected);
});

function enableLatest(
  preview?: (
    component: string,
    signal?: AbortSignal | null,
  ) => Promise<Response>,
) {
  const original = vi.mocked(api.requestMpaImage).getMockImplementation()!;
  vi.mocked(api.requestMpaImage).mockImplementation((...args) => {
    const component = args[2];
    if (args[3]?.startsWith("/versions"))
      return Promise.resolve(
        response({
          repository: repo(component),
          tags: ["latest", "new"],
          nextCursor: "",
        }),
      );
    if (args[3]?.startsWith("/latest-preview"))
      return preview
        ? preview(component, args[4]?.signal)
        : Promise.resolve(
            response({
              component,
              revision: "revision",
              requestedImage: repo(component) + ":latest",
              image: repo(component) + ":resolved-version",
              digest: "sha256:" + "a".repeat(64),
            }),
          );
    return original(...args);
  });
}
async function openLatest(component = "runtime") {
  await choose(component, "latest");
  const card = host.querySelector(`[data-component="${component}"]`)!;
  await act(async () =>
    [...card.querySelectorAll("button")]
      .find((b) => b.textContent === "Update image")!
      .click(),
  );
}
it.each(["runtime", "worker"])(
  "previews latest before confirming only %s with its saved digest",
  async (component) => {
    enableLatest();
    await render();
    await openLatest(component);
    expect(document.body.textContent).toContain(
      repo(component) + ":resolved-version",
    );
    expect(document.body.textContent).toContain("sha256:" + "a".repeat(64));
    expect(
      vi
        .mocked(api.requestMpaImage)
        .mock.calls.filter((c) => c[4]?.method === "POST"),
    ).toHaveLength(0);
    await act(async () => button("Confirm update").click());
    const writes = vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST");
    expect(writes).toHaveLength(1);
    expect(writes[0][2]).toBe(component);
    expect(JSON.parse(writes[0][4]!.body as string)).toEqual({
      tag: "latest",
      revision: "revision",
      selection: {
        image: repo(component) + ":resolved-version",
        digest: "sha256:" + "a".repeat(64),
      },
    });
  },
);
it("blocks confirmation during discovery, cancels reads and ignores late results", async () => {
  let finish!: (value: Response) => void;
  let signal: AbortSignal | null | undefined;
  enableLatest((_component, readSignal) => {
    signal = readSignal;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  await render();
  await openLatest();
  expect(button("Confirm update").disabled).toBe(true);
  expect(document.body.textContent).toContain("Resolving latest");
  await act(async () => button("Cancel").click());
  expect(signal?.aborted).toBe(true);
  await act(async () =>
    finish(
      response({
        component: "runtime",
        revision: "revision",
        requestedImage: repo("runtime") + ":latest",
        image: repo("runtime") + ":late-result",
        digest: "sha256:" + "a".repeat(64),
      }),
    ),
  );
  expect(document.body.textContent).not.toContain("late-result");
  expect(
    vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST"),
  ).toHaveLength(0);
});
it("retries failed discovery read-only and resolves anew after reopening", async () => {
  let attempts = 0;
  enableLatest(async (component) =>
    ++attempts === 1
      ? response({ detail: { reason: "latest_resolution_failed" } }, 502)
      : response({
          component,
          revision: "revision",
          requestedImage: repo(component) + ":latest",
          image: repo(component) + ":resolved-version",
          digest: "sha256:" + "a".repeat(64),
        }),
  );
  await render();
  await openLatest();
  expect(button("Confirm update").disabled).toBe(true);
  expect(document.body.textContent).toContain(
    "Unable to resolve or verify latest",
  );
  await act(async () => button("Retry resolution").click());
  expect(button("Confirm update").disabled).toBe(false);
  await act(async () => button("Cancel").click());
  await openLatest();
  expect(attempts).toBe(3);
  expect(
    vi
      .mocked(api.requestMpaImage)
      .mock.calls.filter((c) => c[4]?.method === "POST"),
  ).toHaveLength(0);
});
it("shows unchanged resolved content and never confirms it", async () => {
  enableLatest(async (component) =>
    response({
      component,
      revision: "revision",
      requestedImage: repo(component) + ":latest",
      image: repo(component) + ":old",
      digest: "sha256:" + "a".repeat(64),
    }),
  );
  await render();
  await openLatest();
  expect(button("Confirm update").disabled).toBe(true);
  expect(document.body.textContent).toContain("already configured");
});

it("allows latest preview when the current literal image is latest", async () => {
  const original = vi.mocked(api.requestMpaImage).getMockImplementation()!;
  vi.mocked(api.requestMpaImage).mockImplementation((...args) =>
    !args[3] && !args[4]?.method
      ? Promise.resolve(
          response(
            detail(args[2], { currentImage: repo(args[2]) + ":latest" }),
          ),
        )
      : original(...args),
  );
  enableLatest();
  await render();
  await openLatest();
  expect(document.body.textContent).toContain(":resolved-version");
  expect(button("Confirm update").disabled).toBe(false);
});
it.each(["component", "revision", "repository", "digest"])(
  "rejects a mismatched latest preview %s",
  async (mode) => {
    enableLatest(async (component) =>
      response({
        component: mode === "component" ? "worker" : component,
        revision: mode === "revision" ? "stale" : "revision",
        requestedImage: repo(component) + ":latest",
        image:
          mode === "repository"
            ? "other.example/repo/image:tag"
            : repo(component) + ":resolved",
        digest: mode === "digest" ? "invalid" : "sha256:" + "a".repeat(64),
      }),
    );
    await render();
    await openLatest();
    expect(button("Confirm update").disabled).toBe(true);
    expect(document.body.textContent).toContain(
      "Unable to resolve or verify latest",
    );
  },
);
it("does not resolve a manual latest address", async () => {
  enableLatest();
  await render();
  const input = host.querySelector<HTMLInputElement>(
    '[data-component="runtime"] input',
  )!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, "other.example/team/image:latest");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => button("Update image").click());
  expect(
    vi
      .mocked(api.requestMpaImage)
      .mock.calls.some((c) => c[3]?.includes("latest-preview")),
  ).toBe(false);
  expect(button("Confirm update").disabled).toBe(false);
  await act(async () => button("Confirm update").click());
  const write = vi
    .mocked(api.requestMpaImage)
    .mock.calls.find((c) => c[4]?.method === "POST")!;
  expect(JSON.parse(write[4]!.body as string)).toEqual({
    image: "other.example/team/image:latest",
    revision: "revision",
  });
});
