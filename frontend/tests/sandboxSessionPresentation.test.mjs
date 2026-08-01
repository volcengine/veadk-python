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
const sandboxAgentWorkspaceSource = readFileSync(
  new URL("../src/ui/SandboxAgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const composerSource = readFileSync(
  new URL("../src/ui/SandboxComposer.tsx", import.meta.url),
  "utf8",
);
const commandsSource = readFileSync(
  new URL("../src/ui/sandboxCommands.ts", import.meta.url),
  "utf8",
);
const commandHookSource = readFileSync(
  new URL("../src/ui/useSandboxCodexCommands.ts", import.meta.url),
  "utf8",
);
const controlsSource = readFileSync(
  new URL("../src/ui/SandboxControls.tsx", import.meta.url),
  "utf8",
);
const controlsStylesSource = readFileSync(
  new URL("../src/ui/SandboxControls.css", import.meta.url),
  "utf8",
);
const controlIconSource = readFileSync(
  new URL("../src/ui/icons/SandboxControlIcons.tsx", import.meta.url),
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
  assert.match(dialogSource, /agentKind === "openclaw" \? "OpenClaw" : "Hermes"/);
  assert.match(dialogSource, /`创建 \$\{agentLabel\} 智能体`/);
  assert.match(dialogSource, /创建一个可重复进入的 AgentKit Session/);
  assert.match(dialogSource, /DEFAULT_SANDBOX_DISPLAY_NAME = "我的智能体"/);
  assert.match(dialogSource, /useState\(defaultDisplayName\)/);
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
    /const nextSession = sandboxLaunchKind === "codex"[\s\S]*?sandboxClient\.startSession\(\{[\s\S]*?sandboxClient\.startAgentSession\(sandboxLaunchKind,[\s\S]*?setCodexSessionsRefreshKey/,
  );
  assert.match(sandboxClientSource, /\/web\/\$\{kind\}\/sessions/);
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

test("managed OpenClaw and Hermes Sessions open a WebUI and Terminal workspace", () => {
  assert.match(sandboxClientSource, /async openAgentSession\(kind, sessionId/);
  assert.match(sandboxClientSource, /\/web\/\$\{kind\}\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/open/);
  assert.match(sandboxClientSource, /async launchAgentTerminal\(kind, sessionId/);
  assert.match(appSource, /async function openSandboxAgentSession/);
  assert.match(appSource, /<SandboxAgentWorkspace[\s\S]*?onRequestTerminal=/);
  assert.match(sandboxAgentWorkspaceSource, /主页面/);
  assert.match(sandboxAgentWorkspaceSource, /Terminal/);
  assert.match(sandboxAgentWorkspaceSource, /<iframe/);
  assert.match(sandboxAgentWorkspaceSource, /返回列表/);
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
    /myAgents \|\|[\s\S]*?sandboxAgentWorkspace \|\|[\s\S]*?agentDetailTarget \|\|[\s\S]*?sandboxSession/,
  );
  assert.match(
    appSource,
    /let cancelled = false;[\s\S]*?await refreshSessions\(appName\);[\s\S]*?if \(cancelled\) return;[\s\S]*?startNewChat\(\);[\s\S]*?cancelled = true;/,
  );
  assert.match(
    appSource,
    /\[[\s\S]*?agentDetailTarget,[\s\S]*?sandboxAgentWorkspace,[\s\S]*?sandboxSession,[\s\S]*?userId,[\s\S]*?\]/,
  );
});

test("sandbox visuals use repository-owned icons and reduced motion", () => {
  assert.match(iconSource, /export function InsightIcon/);
  assert.match(iconSource, /viewBox="0 0 24 24"/);
  assert.doesNotMatch(iconSource, /lucide-react|<img|data:image/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)/);
});

test("sandbox composer keeps every upload and adds Terminal and Browser", () => {
  assert.match(composerSource, /上传图片/);
  assert.match(composerSource, /上传文档或 PDF/);
  assert.match(composerSource, /上传视频/);
  assert.match(
    composerSource,
    /SandboxTerminalIcon[\s\S]*?Terminal[\s\S]*?SandboxBrowserIcon[\s\S]*?Browser/,
  );
  assert.match(appSource, /onAddFiles=\{addSandboxFiles\}/);
  assert.match(appSource, /sandboxClient\.uploadFile/);
  assert.match(sandboxClientSource, /\/files/);
  assert.match(appSource, /if \(!leavingSandbox\) discardDraftAttachments\(attachments\)/);
  assert.match(
    appSource,
    /sandboxUploadRunRef\.current === uploadRun[\s\S]*releaseAttachmentPreviews/,
  );
});

test("permission and workspace controls extend the existing composer grid", () => {
  assert.match(composerSource, /className="composer-left-controls"/);
  assert.match(composerSource, /SandboxPermissionsIcon/);
  assert.match(composerSource, /SandboxWorkspaceIcon/);
  assert.match(
    stylesSource,
    /\.sandbox-composer-wrap \.composer-left-controls[\s\S]*grid-row:\s*2[\s\S]*grid-column:\s*1/,
  );
  assert.match(stylesSource, /\.sandbox-composer-wrap \.comp-send[\s\S]*grid-column:\s*2/);
  assert.match(controlsSource, /当前对话已经开始，工作空间已锁定/);
  assert.match(appSource, /workspaceLocked:\s*true/);
});

test("sandbox permissions are Session-wide and approvals stay interactive", () => {
  assert.match(controlsSource, /同步到其中的所有 Thread/);
  assert.match(sandboxClientSource, /updatePermissions\(/);
  assert.match(sandboxClientSource, /updateWorkspace\(/);
  assert.match(sandboxClientSource, /event === "approval"/);
  assert.match(sandboxClientSource, /event === "approval_resolved"/);
  assert.match(appSource, /onApproval: \(approval\) =>/);
  assert.match(appSource, /sandboxClient\.resolveApproval/);
  assert.match(controlsSource, /仅本次允许/);
  assert.match(controlsSource, /本会话允许/);
});

test("sandbox tools use restrained dialogs and repository-owned product icons", () => {
  assert.match(controlsSource, /SandboxToolDialog/);
  assert.match(controlsSource, /<iframe/);
  assert.doesNotMatch(controlsSource, /RotateCw|ExternalLink|新窗口/);
  assert.doesNotMatch(
    controlsSource,
    /sandbox-tool-toolbar[\s\S]*?>\s*刷新\s*</,
  );
  assert.match(
    controlsSource,
    /sandbox-control-state is-error[\s\S]*onClick=\{onReload\}[\s\S]*重试/,
  );
  assert.match(controlsStylesSource, /\.sandbox-tool-dialog/);
  assert.match(controlsStylesSource, /\.sandbox-settings-dialog/);
  assert.match(controlIconSource, /export function SandboxTerminalIcon/);
  assert.match(controlIconSource, /export function SandboxBrowserIcon/);
  assert.match(controlIconSource, /export function SandboxPermissionsIcon/);
  assert.match(controlIconSource, /export function SandboxWorkspaceIcon/);
  assert.doesNotMatch(controlIconSource, /lucide-react|<img|data:image/);
});

test("sandbox actions render as local system records without entering Codex prompts", () => {
  assert.match(sandboxSessionSource, /SandboxActivityRecord/);
  assert.match(sandboxSessionSource, /操作记录/);
  assert.match(stylesSource, /\.sandbox-activity-record/);
  assert.match(appSource, /role:\s*"system"/);
  assert.match(appSource, /appendSandboxActivity/);
  assert.match(appSource, /已上传文件到 Sandbox|已上传 \$\{uploadedFiles\.length\} 个文件到 Sandbox/);
  assert.match(appSource, /已更新当前 Sandbox Session 的 Codex 权限/);
  assert.match(appSource, /已更新工作空间/);
  assert.match(appSource, /approvalActivityTitle/);
  assert.match(
    appSource,
    /const beforeIndex = current\.findIndex[\s\S]*sandboxActiveAssistantTurnIdRef\.current/,
  );

  const sendStart = appSource.indexOf("async function sendSandboxMessage");
  const nextFunction = appSource.indexOf(
    "\n  async function submitSandboxInput",
    sendStart + 1,
  );
  const sendSource = appSource.slice(
    sendStart,
    nextFunction === -1 ? appSource.length : nextFunction,
  );
  assert.ok(sendStart >= 0);
  assert.match(sendSource, /const prompt = uploadedPaths\.length > 0/);
  assert.doesNotMatch(sendSource, /appendSandboxActivity|activity\.title/);
});

test("sandbox slash commands and Skills stay local until a real turn starts", () => {
  assert.match(commandsSource, /name: "model"/);
  assert.match(commandsSource, /name: "skill"/);
  assert.match(commandsSource, /name: "skills"/);
  assert.match(commandsSource, /name: "resume"/);
  assert.match(composerSource, /matchingSandboxCommands/);
  assert.match(composerSource, /\(\^\|\\s\)\\\$\(\[\^\\s\$\]\*\)\$/);
  assert.match(appSource, /async function submitSandboxInput/);
  assert.match(commandHookSource, /if \(!content\.startsWith\("\/"\)\)/);
  assert.match(commandHookSource, /未知快捷命令/);
  assert.match(commandHookSource, /sandboxClient\.newThread/);
  assert.match(commandHookSource, /sandboxClient\.resumeThread/);
  assert.match(commandHookSource, /sandboxClient\.forkThread/);
  assert.match(commandHookSource, /sandboxClient\.compactThread/);
  assert.match(commandHookSource, /sandboxClient\.archiveThread/);
});

test("sandbox token usage comes from the app-server event and is optional", () => {
  assert.match(sandboxClientSource, /event === "usage"/);
  assert.match(sandboxClientSource, /onUsage\?: \(update: SandboxTokenUsageUpdate\)/);
  assert.match(appSource, /sandboxUsage: update\.usage/);
  assert.match(appSource, /SandboxTokenUsageRow/);
  assert.match(sandboxSessionSource, /Cached input/);
  assert.match(sandboxSessionSource, /Reasoning output/);
  assert.match(sandboxSessionSource, /usage\.cachedInputTokens > 0/);
  assert.match(sandboxSessionSource, /usage\.reasoningOutputTokens > 0/);
});
