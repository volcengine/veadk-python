import { afterEach, expect, it, vi } from "vitest";
import { channelRequest } from "./client";

afterEach(() => vi.unstubAllGlobals());

it("routes channel CRUD through the Runtime proxy without browser credentials", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetcher);
  await channelRequest({ runtimeId: "runtime-test", region: "cn-beijing" }, "/chat-permissions?channel=feishu&chat_id=group", { method: "DELETE" });
  const [url, init] = fetcher.mock.calls[0];
  expect(String(url)).toContain("/web/runtime-proxy/runtime-test/api/v1/channels/chat-permissions");
  expect(String(url)).toContain("_method=DELETE");
  expect(init.method).toBe("POST");
  expect(new Headers(init.headers).has("X-MPA-Channel-Key")).toBe(false);
});
