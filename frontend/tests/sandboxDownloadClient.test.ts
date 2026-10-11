import { afterEach, expect, it, vi } from "vitest";
import { fetchSessionFile, registerRemoteApp } from "../src/adk/client";
import { setLocalUser } from "../src/adk/identity";
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); });
it("routes binary data through the selected Runtime proxy and existing user identity", async () => {
  registerRemoteApp("download-test", { app: "default", runtimeId: "r-test", region: "cn-beijing" });
  setLocalUser("test-user");
  const fetch = vi.fn().mockResolvedValue(new Response("binary")); vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  const blob = await fetchSessionFile("download-test", "session/one", "/data/workspace/分析 结果.xlsx", signal);
  const text = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsText(blob);
  });
  expect(text).toBe("binary");
  expect(fetch.mock.calls[0][0]).toBe("/web/runtime-proxy/r-test/api/v1/sessions/session%2Fone/files/download?path=%2Fdata%2Fworkspace%2F%E5%88%86%E6%9E%90%20%E7%BB%93%E6%9E%9C.xlsx&_runtime_region=cn-beijing");
  expect(fetch.mock.calls[0][1].headers.get("X-VeADK-Local-User")).toBe("test-user");
  expect(fetch.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
});
it.each([403, 404, 503])("rejects HTTP %s without leaking its response body", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private", { status })));
  await expect(fetchSessionFile("default", "session", "/data/output/file", new AbortController().signal)).rejects.toThrow(`SESSION_FILE_HTTP_${status}`);
});
