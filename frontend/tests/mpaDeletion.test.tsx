// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { AgentWorkspace, type AgentWorkspaceProps } from "../src/ui/AgentWorkspace";
import * as api from "../src/adk/client";
vi.mock("../src/adk/client");
vi.mock("../src/create/AgentBuildCanvas", () => ({ AgentBuildCanvas: () => <div /> }));
vi.mock("../src/ui/Markdown", () => ({ Markdown: () => null }));
const { t, i18n } = vi.hoisted(() => ({ t: (key: string) => key, i18n: { language: "en-US", resolvedLanguage: "en-US" } }));
vi.mock("react-i18next", async (load) => ({ ...(await load<typeof import("react-i18next")>()), useTranslation: () => ({t,i18n}) }));
let host: HTMLDivElement, root: Root;
const agent = { id:"one", app:"default", label:"MPA one", remote:true, runtimeId:"r-one", mpaInstanceId:"mi-one", region:"cn-beijing", canDelete:true, agentCategory:"mpa" as const };
const info = {name:"MPA one",tools:[],subAgents:[],description:"test"};
const remove = vi.fn();
const base: AgentWorkspaceProps = { agents:[agent], selectedAgentId:agent.id, focusedAgentId:agent.id, agentInfo:info, agentInfoAgentId:agent.id, loadingAgentInfo:false, canCreate:false, canUpdate:false, detailOnly:true, onSelectAgent:vi.fn(), onCreateAgent:vi.fn(), onDeleteAgents:remove };
const preview = {canDelete:true, blockers:[], sessionCounts:{total:0,active:0,idle:0,debug:0}, cleanupPlan:[{stage:"worker_template",resourceId:"t-one",description:"worker",count:1},{stage:"skill_space",resourceId:"ss-one",description:"skills",count:1}], retainedResources:[{stage:"skill_space",resourceId:"ss-shared",reason:"shared"}]} as api.MpaAgentDeletePreview;
beforeEach(() => {
 vi.stubGlobal("React",React); vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT",true); vi.resetAllMocks();
 vi.mocked(api.getRuntimeAgentInfo).mockResolvedValue(info);
 vi.mocked(api.getRuntimeDetail).mockResolvedValue({runtimeId:"r-one",status:"Ready",networkTypes:[],envs:[]} as never);
 vi.mocked(api.getRuntimeUpdateCapability).mockResolvedValue({canUpdate:false} as never);
 host=document.createElement("div");document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();});
async function render(props:Partial<AgentWorkspaceProps>={}) {await act(async()=>root.render(<AgentWorkspace {...base} {...props}/>));}
async function click(label:string) {const button=Array.from((document.querySelector('[role="alertdialog"]') ?? document).querySelectorAll<HTMLButtonElement>('button')).find(b=>b.textContent?.trim()===label); expect(button).toBeDefined();await act(async()=>button!.click());}
it("opens loading confirmation, exposes preview error, and retries without deleting",async()=>{
 let reject!: (error:Error)=>void;
 vi.mocked(api.getMpaAgentDeletePreview).mockImplementationOnce(()=>new Promise((_,r)=>{reject=r;})).mockResolvedValueOnce(preview);
 await render();await click("agentWorkspace.deleteAgent");
 expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("agentWorkspace.mpaDeleteChecking");
 await act(async()=>reject(new Error("session API unavailable")));
 expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("session API unavailable");
 await click("agentWorkspace.mpaDeleteRetryPreview");
 expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("t-one");
 expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("ss-shared");
 expect(remove).not.toHaveBeenCalled();
});
it("cancels a pending preview and ignores its late completion",async()=>{
 let resolve!:(value:api.MpaAgentDeletePreview)=>void;
 vi.mocked(api.getMpaAgentDeletePreview).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 await render();await click("agentWorkspace.deleteAgent");
 const signal=vi.mocked(api.getMpaAgentDeletePreview).mock.calls[0][0].signal;
 await click("confirm.cancel");expect(signal?.aborted).toBe(true);
 await act(async()=>resolve(preview));expect(document.querySelector('[role="alertdialog"]')).toBeNull();
 expect(remove).not.toHaveBeenCalled();
});
it("shows execution failure in confirmation and keeps retry available",async()=>{
 vi.mocked(api.getMpaAgentDeletePreview).mockResolvedValue(preview);remove.mockRejectedValueOnce(new Error("tool permission denied")).mockResolvedValueOnce(undefined);
 await render();await click("agentWorkspace.deleteAgent");await click("agentWorkspace.deleteAgent");
 expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("tool permission denied");
 await click("agentWorkspace.deleteAgent");expect(remove).toHaveBeenCalledTimes(2);
 expect(document.querySelector('[role="alertdialog"]')).toBeNull();
});
it("general deletion never reads MPA preview",async()=>{
 const general={...agent,agentCategory:"general" as const};remove.mockResolvedValue(undefined);
 await render({agents:[general]});await click("agentWorkspace.deleteAgent");
 expect(api.getMpaAgentDeletePreview).not.toHaveBeenCalled();await click("agentWorkspace.deleteAgent");
 expect(remove).toHaveBeenCalledWith([expect.objectContaining({agentCategory:"general"})]);
});
