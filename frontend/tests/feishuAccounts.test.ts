import { afterEach, expect, it, vi } from "vitest";
import { channelRequest, ChannelApiError } from "../src/adk/client";
import { listFeishuAccounts } from "../src/adk/feishuAccounts";
vi.mock("../src/adk/client", () => ({
  channelRequest: vi.fn(),
  ChannelApiError: class extends Error {
    constructor(public status: number) {
      super(String(status));
    }
  },
}));
const request = vi.mocked(channelRequest);
const ep = { runtimeId: "runtime-a", region: "cn-beijing" };
afterEach(() => request.mockReset());
it("retains only public Feishu account summaries and ignores other providers", async () => {
  request.mockResolvedValue({
    channels: [
      { channel: "wecom", appId: "wecom" },
      {
        channel: "feishu",
        appId: "a",
        appName: "A",
        enabled: true,
        config: { secret: "private-fixture" },
      },
      { channel: "feishu", appId: "b", enabled: false },
    ],
  });
  const signal = new AbortController().signal;
  const result = await listFeishuAccounts(ep, signal);
  expect(result).toEqual([
    { channel: "feishu", appId: "a", appName: "A", enabled: true },
    { channel: "feishu", appId: "b", enabled: false },
  ]);
  expect(JSON.stringify(result)).not.toContain("private-fixture");
  expect(request).toHaveBeenCalledWith(ep, "", { signal });
});
it.each([
  null,
  {},
  { channels: null },
  { channels: [null] },
  { channels: [{}] },
  { channels: [{ channel: "feishu" }] },
  { channels: [{ channel: "feishu", appId: " ", enabled: true }] },
  { channels: [{ channel: "feishu", appId: "a" }] },
  { channels: [{ channel: "feishu", appId: "a", enabled: "yes" }] },
  {
    channels: [
      { channel: "feishu", appId: "a", enabled: true },
      { channel: "feishu", appId: "a", enabled: true },
    ],
  },
])("rejects a malformed or duplicate account response: %j", async (data) => {
  request.mockResolvedValue(data);
  await expect(
    listFeishuAccounts(ep, new AbortController().signal),
  ).rejects.toBeInstanceOf(ChannelApiError);
});
it("propagates request errors rather than returning an empty list", async () => {
  const failure = new ChannelApiError(403);
  request.mockRejectedValue(failure);
  await expect(
    listFeishuAccounts(ep, new AbortController().signal),
  ).rejects.toBe(failure);
});
