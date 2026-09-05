import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebarSource = readFileSync(new URL("../src/ui/Sidebar.tsx", import.meta.url), "utf8");
const workspaceSource = readFileSync(new URL("../src/ui/WorkspaceCenter.tsx", import.meta.url), "utf8");
const clientSource = readFileSync(new URL("../src/adk/client.ts", import.meta.url), "utf8");

test("adds one workspace sidebar entry with the former environment icon", () => {
  assert.match(sidebarSource, /\| "workspaces"/);
  assert.match(sidebarSource, /onWorkspace: \(\) => void/);
  assert.match(sidebarSource, /onClick=\{onWorkspace\}/);
  assert.match(sidebarSource, /aria-label="工作区"/);
  assert.match(sidebarSource, /<Box className="icon" \/>/);
  assert.doesNotMatch(sidebarSource, />环境<\/span>/);
  assert.match(appSource, /<WorkspaceCenter cloudProvider=\{cloudProvider\} \/>/);
});

test("manages reusable environments inside workspaces", () => {
  assert.match(workspaceSource, /同一个环境可以加入多个工作区/);
  assert.match(workspaceSource, /type="checkbox"/);
  assert.match(workspaceSource, /environmentIds\.includes/);
  assert.match(workspaceSource, /createWorkspace/);
  assert.match(workspaceSource, /updateWorkspace/);
  assert.match(workspaceSource, /deleteWorkspace/);
  assert.match(workspaceSource, /<EnvironmentCenter/);
  assert.match(workspaceSource, /label: "环境"/);
});

test("reads environment share codes during the environment tab gesture", () => {
  assert.match(
    workspaceSource,
    /clipboardRead = navigator\.clipboard\.readText\(\);[\s\S]*?setSection\("environments"\)/,
  );
  assert.match(workspaceSource, /clipboardImport=\{clipboardImport\}/);
  assert.match(workspaceSource, /clipboardReadError=\{clipboardReadError\}/);
  assert.match(workspaceSource, /请允许剪贴板权限/);
  assert.match(workspaceSource, /permission\?\.state === "denied"/);
});

test("exposes typed workspace CRUD APIs", () => {
  assert.match(clientSource, /export interface StudioWorkspace/);
  assert.match(clientSource, /\/web\/workspaces/);
  assert.match(clientSource, /export function createWorkspace/);
  assert.match(clientSource, /export function updateWorkspace/);
  assert.match(clientSource, /export async function deleteWorkspace/);
});
