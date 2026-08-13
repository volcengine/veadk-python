import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const manageSource = readFileSync(
  new URL("../src/ui/ManageAgents.tsx", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const connectionsSource = readFileSync(
  new URL("../src/adk/connections.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const manageStyles = readFileSync(
  new URL("../src/ui/ManageAgents.css", import.meta.url),
  "utf8",
);

test("managed runtimes connect through the Agent page", () => {
  assert.match(manageSource, /onConnect:\s*\(runtime:\s*ManagedRuntime\)/);
  assert.match(manageSource, /连接到此 Agent/);
  assert.match(manageSource, /currentRuntimeId === rt\.runtimeId[\s\S]*?已连接/);
  assert.match(appSource, /connectMyAgent[\s\S]*?connectRuntime\(/);
  assert.match(appSource, /<MyAgents[\s\S]*?onUseAgent=\{/);
  assert.match(workspaceSource, /onSelectAgent\(agent\.id\)/);
  assert.match(
    manageStyles,
    /@media \(max-width:\s*700px\)[\s\S]*?\.manage-item-actions\s*\{[\s\S]*?width:\s*100%;/,
  );
});

test("runtime connection probing is shared with the Agent selector", () => {
  assert.match(connectionsSource, /export async function connectRuntime/);
  assert.match(clientSource, /VOLCENGINE_RUNTIME_REGION_FALLBACKS = \["cn-beijing", "cn-shanghai"\]/);
  assert.match(clientSource, /activeCloudProvider === "byteplus"[\s\S]*?BYTEPLUS_DEFAULT_REGION/);
  assert.match(clientSource, /setClientCloudProvider\(provider\)/);
  assert.match(connectionsSource, /runtimeRegionCandidates,/);
  assert.match(connectionsSource, /for \(const candidate of runtimeRegionCandidates\(region\)\)/);
  assert.match(connectionsSource, /probeRuntimeApps\(runtimeId, candidate,[\s\S]*?retryProbe: true/);
  assert.match(connectionsSource, /resolvedRegion = candidate/);
  assert.match(connectionsSource, /addRuntimeConnection\(/);
  assert.match(connectionsSource, /resolvedRegion,[\s\S]*?apps,[\s\S]*?labels/);
  assert.match(connectionsSource, /return remoteAppId\(connection\.id, apps\[0\]\)/);
});

test("runtime connections keep the Runtime resource name separate from Agent labels", () => {
  assert.match(connectionsSource, /agentName\?: string/);
  assert.match(
    connectionsSource,
    /const resolvedAgentName = agentName\?\.trim\(\) \|\| apps\[0\]/,
  );
  assert.match(
    connectionsSource,
    /Object\.fromEntries\([\s\S]*?apps\.map\(\(app\) => \[app, app === apps\[0\] \? resolvedAgentName : app\]\)[\s\S]*?\)/,
  );
  assert.match(
    appSource,
    /connectRuntime\([\s\S]*?result\.runtimeId,[\s\S]*?result\.runtimeName,[\s\S]*?agentName: result\.agentName/,
  );
});

test("fresh deployments wait for the Runtime network to become reachable", () => {
  assert.match(connectionsSource, /DEPLOYED_RUNTIME_CONNECT_INTERVAL_MS = 3_000/);
  assert.match(connectionsSource, /DEPLOYED_RUNTIME_CONNECT_TIMEOUT_MS = 60_000/);
  assert.match(connectionsSource, /waitForReady\?: boolean/);
  assert.match(
    connectionsSource,
    /while \(true\)[\s\S]*?connectRuntimeOnce\([\s\S]*?error instanceof RuntimeProbeError[\s\S]*?error\.retryable[\s\S]*?waitForRuntimeProbe\(delayMs\)/,
  );
  assert.match(
    appSource,
    /const finishDeployment = useCallback[\s\S]*?connectRuntime\([\s\S]*?waitForReady: true,[\s\S]*?agentName: result\.agentName/,
  );
});

test("management defaults to the active provider region without trailing list whitespace", () => {
  assert.match(manageSource, /defaultCloudRegion\(cloudProvider\)/);
  assert.match(manageSource, /cloudRegionOptions\(cloudProvider\)/);
  assert.match(manageSource, /formatCloudRegion\(regionFilter, cloudProvider\)/);
  assert.doesNotMatch(manageSource, /value: "all"/);
  assert.match(manageSource, /role="listbox" aria-label="区域"/);
  assert.match(manageSource, /role="option"[\s\S]*?aria-selected=\{selected\}/);
  assert.match(manageStyles, /\.manage-region-menu\s*\{[\s\S]*?border-radius:\s*12px;/);
  assert.match(manageSource, /列出你有权管理的 AgentKit Runtime\s*<\/p>/);
  assert.doesNotMatch(manageSource, /列出你有权管理的 AgentKit Runtime。/);
  assert.match(
    manageStyles,
    /\.manage\s*\{[\s\S]*?padding:\s*28px 24px 16px;/,
  );
});
