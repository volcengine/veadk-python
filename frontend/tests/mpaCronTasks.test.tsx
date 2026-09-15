import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchMpaCronTasks, type MpaCronTaskPage } from "../src/adk/mpaCronTasks";
import { MpaCronTasks } from "../src/cronjobs/MpaCronTasks";

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../src/adk/client", () => ({ listMpaCronTasks: list }));
vi.mock("../src/ui/text-shimmer/TextShimmer", () => ({ TextShimmer: ({children}: {children: React.ReactNode}) => <span>{children}</span> }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string, args?: {status?: number}) => key + (args?.status ?? "") }) }));
const runtime = { runtimeId: "r-one", region: "cn-beijing", name: "One" };
const task = { id: "t1", name: "Report", enabled: true, schedule: { type: "cron", timezone: "Asia/Shanghai", cronExpression: "0 9 * * *" }, nextRunAt: "2026-09-16T01:00:00Z", lastRunStatus: "success" };
const page: MpaCronTaskPage = { items: [task], total: 21, hasMore: true, nextOffset: 20 };
describe("MPA HTTP contract", () => {
  it("uses the server credential route with selected Runtime and encoded search", async () => {
    const nextPage = {...page, nextOffset: 40};
    const request = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(nextPage))));
    const signal = new AbortController().signal;
    expect(await fetchMpaCronTasks(request, runtime, 20, "a b", signal)).toEqual(nextPage);
    expect(request).toHaveBeenCalledWith("/web/mpa-cron/r-one?region=cn-beijing&offset=20&query=a%20b", { signal }, {});
    await fetchMpaCronTasks(request, runtime, 0, "", signal);
    expect(request.mock.calls[1][1].headers).toBeUndefined();
  });
  it.each([401, 403, 404, 500])("reports HTTP %s", async status => {
    await expect(fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response("private server response", {status})), runtime, 0, "")).rejects.toThrow(`MPA_HTTP_${status}`);
  });
  it.each(["bad json", "null", '{}', '{"items":null}', JSON.stringify({...page, total:-1}), JSON.stringify({...page, hasMore:"yes"}), JSON.stringify({...page, nextOffset:null}), JSON.stringify({...page, nextOffset:0}), JSON.stringify({...page, items:[null]}), JSON.stringify({...page, items:[{...task, id:3}]}), JSON.stringify({...page, items:[{...task, name:3}]}), JSON.stringify({...page, items:[{...task, enabled:"yes"}]}), JSON.stringify({...page, items:[{...task, schedule:null}]}), JSON.stringify({...page, items:[{...task, schedule:{}}]})])("rejects malformed responses %s", async body => {
    await expect(fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(body)), runtime, 0, "")).rejects.toThrow("MPA_INVALID_RESPONSE");
  });
  it("accepts a final empty page and propagates cancellation", async () => {
    const last = {items:[],total:0,hasMore:false,nextOffset:null};
    expect(await fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify(last))), runtime, 0, "")).toEqual(last);
    const error = new DOMException("aborted", "AbortError");
    await expect(fetchMpaCronTasks(vi.fn().mockRejectedValue(error), runtime, 0, "")).rejects.toBe(error);
  });
});
let host: HTMLDivElement; let root: Root;
async function mount(target: typeof runtime | undefined = runtime) {
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  await act(async () => root.render(<MpaCronTasks runtime={target} />));
}
async function click(text: string) { await act(async () => { Array.from(host.querySelectorAll("button")).find(b => b.textContent === text)!.click(); }); }
afterEach(async () => { if (root) await act(async () => root.unmount()); host?.remove(); vi.clearAllMocks(); });
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
it("does not request without a cloud Runtime", async () => {
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  await act(async () => root.render(<MpaCronTasks />));
  expect(host.textContent).toContain("mpa.selectRuntime"); expect(list).not.toHaveBeenCalled();
});
it("shows data, pages, refreshes and searches without JWT input", async () => {
  list.mockResolvedValue(page); await mount();
  expect(host.textContent).toContain("Report"); expect(host.textContent).toContain("r-one");
  expect(host.querySelector('input')!.type).toBe("search");
  await click("mpa.next"); expect(list.mock.calls.at(-1)![1]).toBe(20);
  await click("mpa.previous"); expect(list.mock.calls.at(-1)![1]).toBe(0);
  await click("mpa.refresh");
  await act(async () => { const input=host.querySelector('input')!; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'report'); input.dispatchEvent(new Event('input',{bubbles:true})); });
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(list.mock.calls.at(-1)![2]).toBe('report');
  expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  list.mockResolvedValue({items:[{...task,enabled:false,nextRunAt:null,lastRunStatus:null}],total:1,hasMore:false,nextOffset:null});
  await click("mpa.refresh"); expect(host.textContent).toContain('status.paused');
});
it.each([['MPA_HTTP_401','mpa.authRequired'],['MPA_HTTP_403','mpa.forbidden'],['MPA_HTTP_404','mpa.unsupported'],['MPA_HTTP_500','mpa.loadFailed'],['MPA_INVALID_RESPONSE','mpa.invalidResponse'],['network','mpa.loadFailed']])("shows %s without exposing credentials and retries", async (error,key) => {
  list.mockRejectedValue(new Error(error)); await mount(); expect(host.textContent).toContain(key);
  expect(host.querySelector('[role="alert"]')).not.toBeNull();
  list.mockResolvedValue({items:[],total:0,hasMore:false,nextOffset:null}); await click('mpa.refresh'); expect(host.textContent).toContain('mpa.empty');
});
it("aborts stale responses on selection changes and clears search", async () => {
  let resolve!: (value: MpaCronTaskPage) => void;
  list.mockImplementationOnce(() => new Promise(r => {resolve=r;})); await mount();
  expect(host.textContent).toContain('mpa.loading'); const signal = list.mock.calls[0][3] as AbortSignal;
  list.mockResolvedValue({items:[],total:0,hasMore:false,nextOffset:null});
  await act(async () => root.render(<MpaCronTasks runtime={{...runtime,runtimeId:'r-two'}} />));
  expect(signal.aborted).toBe(true);
  await act(async () => resolve(page)); expect(host.textContent).not.toContain('Report'); expect(host.querySelector('input')!.value).toBe('');
});
it("ignores late errors after unmount", async () => {
  let reject!: (reason: Error) => void;
  list.mockImplementationOnce(() => new Promise((_,r) => {reject=r;})); await mount();
  await act(async () => root.unmount()); await act(async () => reject(new Error('late')));
});

it("handles non-Error failures", async () => { list.mockRejectedValue("offline"); await mount(); expect(host.textContent).toContain("mpa.loadFailed"); });

it.each([{nextRunAt: {}}, {lastRunStatus: {} }])("rejects invalid optional task fields", async patch => {
 await expect(fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify({...page,items:[{...task,...patch}]}))),runtime,0,"")).rejects.toThrow("MPA_INVALID_RESPONSE");
});
it("accepts null optional task fields", async () => {
 const data={...page,items:[{...task,nextRunAt:null,lastRunStatus:null}]};
 expect(await fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify(data))),runtime,0,"")).toEqual(data);
});

it.each(["mpa_identity_required", "mpa_runtime_config_required", "mpa_runtime_mismatch", "mpa_top_failed"])("handles safe server code %s", async code => {
 await expect(fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:code}),{status:409})),runtime,0,"")).rejects.toThrow(code);
 list.mockRejectedValue(new Error(code)); await mount(); expect(host.textContent).toContain(`mpa.errors.${code}`);
});
it("does not echo unknown server error bodies", async () => {
 await expect(fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:"secret"}),{status:502})),runtime,0,"")).rejects.toThrow("MPA_HTTP_502");
});
it("shows reference overview metrics and prompt details", async () => {
 const data={...page,overview:{executionCount:4,successRate:0.75},items:[{...task,prompt:"Summarize news"}]};
 expect(await fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify(data))),runtime,0,"")).toEqual(data);
 list.mockResolvedValue(data); await mount(); expect(host.textContent).toContain("75.0%"); expect(host.textContent).toContain("Summarize news");
});
it.each([{overview:{executionCount:"4",successRate:1}},{overview:{executionCount:4,successRate:"1"}},{items:[{...task,prompt:{}}]}])("validates overview and prompt",async patch=>{
 await expect(fetchMpaCronTasks(vi.fn().mockResolvedValue(new Response(JSON.stringify({...page,...patch}))),runtime,0,"")).rejects.toThrow("MPA_INVALID_RESPONSE");
});
