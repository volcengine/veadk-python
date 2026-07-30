import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const sandboxClientSource = readFileSync(
  new URL("../src/adk/sandbox.ts", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/SandboxLaunchDialog.tsx", import.meta.url),
  "utf8",
);
const sandboxSessionSource = readFileSync(
  new URL("../src/ui/SandboxSession.tsx", import.meta.url),
  "utf8",
);
const myAgentsSource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/ui/SandboxSession.css", import.meta.url),
  "utf8",
);
const iconSource = readFileSync(
  new URL("../src/ui/icons/InsightIcon.tsx", import.meta.url),
  "utf8",
);
const modeSelectorSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatModeSelector.tsx", import.meta.url),
  "utf8",
);

test("sandbox access is isolated behind a reusable typed client", () => {
  assert.match(sandboxClientSource, /export interface AgentKitSandboxClient/);
  assert.match(sandboxClientSource, /listSessions\(options\?: SandboxRequestOptions\)/);
  assert.match(sandboxClientSource, /startSession\(options\?: SandboxStartOptions\)/);
  assert.match(
    sandboxClientSource,
    /connectSession\([\s\S]*options\?: SandboxRequestOptions/,
  );
  assert.match(sandboxClientSource, /sendMessage\([\s\S]*options\?: SandboxRequestOptions/);
  assert.match(sandboxClientSource, /closeSession\([\s\S]*options\?: SandboxRequestOptions/);
  assert.match(sandboxClientSource, /signal\?: AbortSignal/);
  assert.match(sandboxClientSource, /\/web\/sandbox\/sessions/);
  assert.match(sandboxClientSource, /method: "GET"/);
  assert.match(sandboxClientSource, /\/connect/);
  assert.match(sandboxClientSource, /withAuth/);
  assert.match(sandboxClientSource, /withLocalUser/);
  assert.match(sandboxClientSource, /Accept: "text\/event-stream"/);
  assert.match(sandboxClientSource, /onBlocks\?: \(blocks: Block\[\]\) => void/);
  assert.match(sandboxClientSource, /event === "activity"/);
  assert.match(sandboxClientSource, /kind === "thinking"/);
  assert.match(sandboxClientSource, /payload\.kind !== "tool"/);
  assert.match(appSource, /onBlocks: \(blocks\) =>/);
  assert.doesNotMatch(sandboxClientSource, /setTimeout|crypto\.randomUUID/);
});

test("new-chat built-in agent mode opens the AgentKit sandbox creator", () => {
  assert.match(modeSelectorSource, /value: "temporary"[\s\S]*?label: "内置智能体"/);
  assert.match(appSource, /mode === "temporary"[\s\S]*?openSandboxLaunch\(\)/);
  assert.doesNotMatch(appSource, /<SandboxEntryButton/);
});

test("sandbox launch dialog covers confirmation loading failure and retry", () => {
  assert.match(dialogSource, /role="dialog"/);
  assert.match(dialogSource, /创建 Codex 智能体/);
  assert.match(dialogSource, /创建一个可重复进入的 AgentKit 沙箱/);
  assert.match(dialogSource, /DEFAULT_SANDBOX_DISPLAY_NAME = "我的智能体"/);
  assert.match(dialogSource, /useState\(DEFAULT_SANDBOX_DISPLAY_NAME\)/);
  assert.match(
    dialogSource,
    /maxLength=\{SANDBOX_DISPLAY_NAME_MAX_LENGTH\}/,
  );
  assert.match(dialogSource, /智能体名称（可选）/);
  assert.match(dialogSource, /onCompositionStart/);
  assert.match(dialogSource, /nativeEvent\.isComposing/);
  assert.match(dialogSource, /keyCode === 229/);
  assert.match(dialogSource, /正在创建沙箱/);
  assert.match(dialogSource, /启动失败/);
  assert.match(dialogSource, /重新尝试/);
  assert.match(dialogSource, /if \(event\.key === "Escape"/);
  assert.match(appSource, /sandboxLaunchAbortRef\.current\?\.abort\(\)/);
});

test("active sandbox conversation returns to the reusable Session list", () => {
  assert.match(sandboxSessionSource, /返回列表不会删除沙箱/);
  assert.match(sandboxSessionSource, /返回智能体列表/);
  assert.match(appSource, /sandboxClient\.sendMessage/);
  assert.doesNotMatch(sandboxClientSource, /runSSE/);
  assert.match(stylesSource, /\.main\.is-sandbox-session::before/);
  assert.match(stylesSource, /\.sandbox-session-warning/);
  assert.match(
    stylesSource,
    /\.sandbox-session-warning-copy[\s\S]*text-align:\s*center/,
  );
  assert.match(
    stylesSource,
    /\.sandbox-composer-wrap \.composer-box[\s\S]*grid-template-rows/,
  );
  assert.match(
    stylesSource,
    /\.main\.is-sandbox-session[\s\S]*linear-gradient\([\s\S]*to bottom/,
  );
});

test("creating a sandbox refreshes the list while opening an item connects it", () => {
  const launchStart = appSource.indexOf("async function launchSandboxSession");
  const connectStart = appSource.indexOf("async function connectSandboxSession");
  const launchSource = appSource.slice(launchStart, connectStart);
  assert.ok(launchStart >= 0 && connectStart > launchStart);
  assert.match(
    launchSource,
    /const nextSession = await sandboxClient\.startSession\(\{[\s\S]*?displayName[\s\S]*?setCodexSessionsRefreshKey/,
  );
  assert.match(sandboxClientSource, /body: JSON\.stringify\(\{ displayName:/);
  assert.match(
    sandboxClientSource,
    /SANDBOX_DISPLAY_NAME_MAX_LENGTH = 40/,
  );
  assert.match(sandboxClientSource, /displayName: data\.displayName \?\? ""/);
  assert.match(
    appSource,
    /nextSession\.displayName\s*\|\|\s*nextSession\.userSessionId/,
  );
  assert.doesNotMatch(
    launchSource,
    /setSandboxSession\(nextSession\)/,
  );
  assert.match(
    appSource,
    /async function connectSandboxSession[\s\S]*?sandboxClient\.connectSession[\s\S]*?setSandboxSession/,
  );
  assert.match(
    appSource,
    /function returnToCodexAgents[\s\S]*?exitSandboxSession\(\)[\s\S]*?setAgentDirectoryType\("codex"\)[\s\S]*?setMyAgents\(true\)/,
  );
  const clientCreateStart = sandboxClientSource.indexOf("async startSession");
  const clientConnectStart = sandboxClientSource.indexOf("async connectSession");
  assert.ok(clientCreateStart >= 0 && clientConnectStart > clientCreateStart);
  assert.doesNotMatch(
    sandboxClientSource.slice(clientCreateStart, clientConnectStart),
    /status\.toLowerCase\(\) !== "ready"/,
  );
  assert.match(
    myAgentsSource,
    /CODEX_TRANSITIONAL_STATUSES[\s\S]*?setTimeout\([\s\S]*?fetchCodexSessions\(\)[\s\S]*?3_000/,
  );
});

test("active sandbox conversation does not wait for normal Agent capabilities", () => {
  assert.match(
    appSource,
    /turns\.length === 0 && !sandboxSession && !newChatCapabilitiesReady/,
  );
});

test("normal session refresh cannot close a newly launched sandbox session", () => {
  assert.match(
    appSource,
    /if \(myAgents \|\| agentDetailTarget \|\| sandboxSession \|\| !appName \|\| !userId\)/,
  );
  assert.match(
    appSource,
    /let cancelled = false;[\s\S]*?await refreshSessions\(appName\);[\s\S]*?if \(cancelled\) return;[\s\S]*?startNewChat\(\);[\s\S]*?cancelled = true;/,
  );
  assert.match(
    appSource,
    /\[agentDetailTarget, appName, myAgents, sandboxSession, userId\]/,
  );
});

test("sandbox visuals use repository-owned icons and reduced motion", () => {
  assert.match(iconSource, /export function InsightIcon/);
  assert.match(iconSource, /viewBox="0 0 24 24"/);
  assert.doesNotMatch(iconSource, /lucide-react|<img|data:image/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)/);
});
