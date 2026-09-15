import { describe, expect, it, vi } from "vitest";
import {
  fetchMpaCronTasks,
  type MpaCronTaskPage,
} from "../src/adk/mpaCronTasks";
const runtime = { runtimeId: "r-one", region: "cn-beijing", name: "One" };
const task = {
  id: "t1",
  name: "Report",
  enabled: true,
  schedule: {
    type: "cron",
    timezone: "Asia/Shanghai",
    cronExpression: "0 9 * * *",
  },
  nextRunAt: "2026-09-16T01:00:00Z",
  lastRunStatus: "success",
};
const page: MpaCronTaskPage = {
  items: [task],
  total: 21,
  hasMore: true,
  nextOffset: 20,
};
describe("MPA HTTP contract", () => {
  it("uses the server credential route with selected Runtime and encoded search", async () => {
    const nextPage = { ...page, nextOffset: 40 };
    const request = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify(nextPage))),
      );
    const signal = new AbortController().signal;
    expect(
      await fetchMpaCronTasks(request, runtime, 20, "a b", signal),
    ).toEqual(nextPage);
    expect(request).toHaveBeenCalledWith(
      "/web/mpa-cron/r-one?region=cn-beijing&offset=20&query=a%20b",
      { signal },
      {},
    );
    await fetchMpaCronTasks(request, runtime, 0, "", signal);
    expect(request.mock.calls[1][1].headers).toBeUndefined();
  });
  it.each([401, 403, 404, 500])("reports HTTP %s", async (status) => {
    await expect(
      fetchMpaCronTasks(
        vi
          .fn()
          .mockResolvedValue(
            new Response("private server response", { status }),
          ),
        runtime,
        0,
        "",
      ),
    ).rejects.toThrow(`MPA_HTTP_${status}`);
  });
  it.each([
    "bad json",
    "null",
    "{}",
    '{"items":null}',
    JSON.stringify({ ...page, total: -1 }),
    JSON.stringify({ ...page, hasMore: "yes" }),
    JSON.stringify({ ...page, nextOffset: null }),
    JSON.stringify({ ...page, nextOffset: 0 }),
    JSON.stringify({ ...page, items: [null] }),
    JSON.stringify({ ...page, items: [{ ...task, id: 3 }] }),
    JSON.stringify({ ...page, items: [{ ...task, name: 3 }] }),
    JSON.stringify({ ...page, items: [{ ...task, enabled: "yes" }] }),
    JSON.stringify({ ...page, items: [{ ...task, schedule: null }] }),
    JSON.stringify({ ...page, items: [{ ...task, schedule: {} }] }),
  ])("rejects malformed responses %s", async (body) => {
    await expect(
      fetchMpaCronTasks(
        vi.fn().mockResolvedValue(new Response(body)),
        runtime,
        0,
        "",
      ),
    ).rejects.toThrow("MPA_INVALID_RESPONSE");
  });
  it("accepts a final empty page and propagates cancellation", async () => {
    const last = { items: [], total: 0, hasMore: false, nextOffset: null };
    expect(
      await fetchMpaCronTasks(
        vi.fn().mockResolvedValue(new Response(JSON.stringify(last))),
        runtime,
        0,
        "",
      ),
    ).toEqual(last);
    const error = new DOMException("aborted", "AbortError");
    await expect(
      fetchMpaCronTasks(vi.fn().mockRejectedValue(error), runtime, 0, ""),
    ).rejects.toBe(error);
  });
});
