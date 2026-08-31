import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const appSource = source("../src/App.tsx");
const clientSource = source("../src/adk/client.ts");
const railSource = source("../src/ui/AgentTopology.tsx");
const pickerSource = source("../src/ui/SessionEnvironmentPicker.tsx");
const stylesSource = source("../src/styles.css");

test("runSSE keeps multiple environment mounts in the Studio BFF request only", () => {
  assert.match(clientSource, /environmentMounts\?: readonly SessionEnvironmentMountSelection\[\]/);
  assert.match(clientSource, /environment_mounts: \[\.\.\.environmentMounts\]/);
  assert.match(clientSource, /environment_mount: environmentMount/);
  assert.match(clientSource, /environment_id: string/);
  assert.match(clientSource, /environment_version_id: string/);
  assert.match(clientSource, /toolStatus: EnvironmentSandboxToolStatus/);
  assert.match(clientSource, /toolId: typeof candidate\.toolId === "string"/);
});

test("Studio offers only tool-ready AIO Sandbox environment versions", () => {
  assert.match(appSource, /environment\.baseEnvironment === "aio-sandbox"/);
  assert.match(appSource, /environment\.latestVersion\?\.status === "available"/);
  assert.match(appSource, /environment\.latestVersion\.toolStatus === "ready"/);
  assert.match(appSource, /Boolean\(environment\.latestVersion\.toolId\)/);
  assert.match(appSource, /listEnvironments\(controller\.signal\)/);
  assert.match(appSource, /listWorkspaces\(controller\.signal\)/);
});

test("environments are mounted dynamically after a Session exists", () => {
  assert.doesNotMatch(appSource, /draftEnvironmentMounts/);
  assert.match(appSource, /environmentMountsBySession/);
  assert.match(appSource, /const environmentMounts = createsSession\s*\? \[\]/);
  assert.match(appSource, /if \(!sessionId\) return;/);
  assert.match(appSource, /setEnvironmentMountsBySession\(\(current\) => \(\{/);
  assert.match(appSource, /ENVIRONMENT_STUDIO_TOOL_IDS = \[[\s\S]*?"list_envs"[\s\S]*?"get_env_manifest"[\s\S]*?"execute_in_sandbox"/);
  assert.match(appSource, /selections\.length > 0[\s\S]*?ENVIRONMENT_STUDIO_TOOL_IDS[\s\S]*?selectedIds\.filter/);
  assert.match(appSource, /const visibleStudioTools = studioToolCapabilities\?\.tools\.filter/);
  assert.match(appSource, /managedStudioToolIds=\{selectedEnvironmentMounts\.length > 0/);
  assert.match(appSource, /environmentMounts: currentRuntime && environmentMounts\.length > 0/);
  assert.doesNotMatch(appSource, /environmentsLocked/);
});

test("environment picker stays in Agent info below skills", () => {
  assert.match(pickerSource, /className="topo-capability-add-slot"/);
  assert.match(pickerSource, /type="checkbox"/);
  assert.match(pickerSource, /className="session-environment-check"/);
  assert.match(stylesSource, /input:checked \+ \.session-environment-check/);
  assert.match(pickerSource, /确认添加/);
  assert.match(pickerSource, /createPortal/);
  assert.match(pickerSource, /选择工作区/);
  assert.match(pickerSource, /workspaceEnvironmentMounts/);
  assert.match(pickerSource, /已由工作区/);
  assert.match(pickerSource, /disabled=\{covered\}/);
  assert.match(pickerSource, /onConfirm\(environments\.flatMap[\s\S]*?\[\.\.\.draftWorkspaceIds\]/);
  assert.doesNotMatch(appSource, /<SessionEnvironmentPicker/);
  const homepagePanelStart = appSource.indexOf("turns.length === 0 ?");
  const transcriptStart = appSource.indexOf('className={`transcript', homepagePanelStart);
  const homepageSource = appSource.slice(homepagePanelStart, transcriptStart);
  const transcriptSource = appSource.slice(transcriptStart);
  assert.doesNotMatch(homepageSource, /<AgentInfoPanel/);
  assert.doesNotMatch(homepageSource, /environments=\{/);
  assert.match(transcriptSource, /environments=\{sessionEnvironments\}/);
  assert.match(transcriptSource, /workspaces=\{sessionWorkspaces\}/);
  assert.doesNotMatch(pickerSource, /仅对当前 Session 生效/);
  assert.doesNotMatch(pickerSource, /固定已添加的环境|环境集合已固定/);
  assert.match(railSource, /<ModuleTitle title="环境"/);
  assert.match(railSource, /<SessionEnvironmentPicker/);
  assert.match(railSource, /tool\.custom && tool\.removable/);
  assert.match(railSource, /!managedIds\.has\(tool\.id\)/);
  assert.ok(
    railSource.indexOf('title="环境"') > railSource.indexOf('title="技能"'),
    "environment section should follow skills",
  );
  assert.match(stylesSource, /\.session-environment-dialog__footer/);
  assert.match(stylesSource, /\.session-environment-item/);
  assert.match(stylesSource, /\.topo-module-stack:has\(\.topo-environment-card\)/);
  assert.match(pickerSource, /addButtonRef\.current\?\.focus\(\)/);
});

test("environment picker keeps compact typography and spacing", () => {
  assert.match(
    stylesSource,
    /\.topo-capability-add-slot > svg\s*\{[^}]*width:\s*15px;[^}]*height:\s*15px;/s,
  );
  assert.match(
    stylesSource,
    /\.session-environment-picker__group\s*\{[^}]*gap:\s*8px;/s,
  );
  assert.match(
    stylesSource,
    /\.session-environment-picker__group > h3\s*\{[^}]*font-size:\s*11px;/s,
  );
  assert.match(
    stylesSource,
    /\.session-environment-option \.studio-tool-option-copy small\s*\{[^}]*font-size:\s*10\.5px;/s,
  );
  assert.match(
    stylesSource,
    /\.session-environment-dialog__footer\s*\{[^}]*display:\s*flex;/s,
  );
  assert.match(
    stylesSource,
    /@media \(max-width:\s*720px\)[\s\S]*?\.session-environment-dialog__footer\s*\{[^}]*flex-direction:\s*column;/,
  );
});
