import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { clearRemoteApps, registerRemoteApp, runSSE } from "./client";

beforeEach(() => {
  vi.stubGlobal("window", { location: { search: "", origin: "https://studio.example" } });
  vi.stubGlobal("sessionStorage", { getItem: () => null });
  vi.stubGlobal("localStorage", { getItem: () => null });
});

afterEach(() => {
  clearRemoteApps();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const run = () => runSSE({
  appName: "remote-mpa",
  userId: "studio-user",
  sessionId: "session-1",
  text: "hello",
});

it("prewarms an MPA Runtime before sending a web-chat run", async () => {
  registerRemoteApp("remote-mpa", {
    app: "mpa-agent",
    runtimeId: "runtime-1",
    region: "cn-beijing",
    agentCategory: "mpa",
  });
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }))
    .mockResolvedValueOnce(new Response('{"invocationId":"inv-1"}', { status: 200 }))
    .mockResolvedValueOnce(new Response('data: {"author":"agent"}\n\nevent: done\ndata: {}\n\n', { status: 200 }));
  vi.stubGlobal("fetch", fetcher);

  const events = [];
  for await (const event of run()) events.push(event);

  expect(events).toHaveLength(1);
  expect(String(fetcher.mock.calls[0][0])).toContain("/web/mpa/identity-prewarm/runtime-1?region=cn-beijing");
  expect(fetcher.mock.calls[0][1].method).toBe("POST");
  expect(new Headers(fetcher.mock.calls[0][1].headers).get("X-Requested-With")).toBe("XMLHttpRequest");
  expect(String(fetcher.mock.calls[1][0])).toContain("/web/runtime-proxy/runtime-1/api/v1/sessions/session-1/run");
  expect(JSON.stringify(fetcher.mock.calls)).not.toContain("idToken");
});

it("keeps MPA chat available when identity prewarm fails", async () => {
  registerRemoteApp("remote-mpa", {
    app: "mpa-agent", runtimeId: "runtime-1", agentCategory: "mpa",
  });
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response(
      '{"detail":"studio_oauth_session_required"}',
      { status: 409, headers: { "Content-Type": "application/json" } },
    ))
    .mockResolvedValueOnce(new Response('{"invocationId":"inv-1"}', { status: 200 }))
    .mockResolvedValueOnce(new Response('data: {"author":"agent"}\n\nevent: done\ndata: {}\n\n', { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});

  const events = [];
  for await (const event of run()) events.push(event);

  expect(events).toHaveLength(1);
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(String(fetcher.mock.calls[1][0])).toContain("/run");
  expect(warning).toHaveBeenCalledWith("[mpa] identity prewarm unavailable", 409);
  warning.mockRestore();
});

it("keeps MPA chat available when the prewarm request has a network error", async () => {
  registerRemoteApp("remote-mpa", {
    app: "mpa-agent", runtimeId: "runtime-1", agentCategory: "mpa",
  });
  const fetcher = vi.fn()
    .mockRejectedValueOnce(new Error("network unavailable"))
    .mockResolvedValueOnce(new Response('{"invocationId":"inv-1"}', { status: 200 }))
    .mockResolvedValueOnce(new Response('data: {"author":"agent"}\n\nevent: done\ndata: {}\n\n', { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});

  const events = [];
  for await (const event of run()) events.push(event);

  expect(events).toHaveLength(1);
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(warning).toHaveBeenCalledWith("[mpa] identity prewarm unavailable");
  warning.mockRestore();
});

it("does not start a run when chat is cancelled during prewarm", async () => {
  registerRemoteApp("remote-mpa", {
    app: "mpa-agent", runtimeId: "runtime-1", agentCategory: "mpa",
  });
  const controller = new AbortController();
  const fetcher = vi.fn().mockImplementation(async () => {
    controller.abort();
    throw new DOMException("Aborted", "AbortError");
  });
  vi.stubGlobal("fetch", fetcher);

  await expect(runSSE({
    appName: "remote-mpa", userId: "studio-user", sessionId: "session-1",
    text: "hello", signal: controller.signal,
  }).next()).rejects.toThrow();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
