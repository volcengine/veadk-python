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
const detailsSource = readFileSync(
  new URL("../src/ui/SandboxAgentDetails.tsx", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/ui/SandboxAgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const workspaceStyles = readFileSync(
  new URL("../src/ui/SandboxAgentWorkspace.css", import.meta.url),
  "utf8",
);
const sandboxSessionSource = readFileSync(
  new URL("../src/ui/SandboxSession.tsx", import.meta.url),
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
  assert.match(sandboxClientSource, /startSession\(options\?: SandboxStartOptions\)/);
  assert.match(sandboxClientSource, /listAgentSessions\([\s\S]*kind: SandboxAgentKind/);
  assert.match(sandboxClientSource, /startAgentSession\([\s\S]*kind: SandboxAgentKind/);
  assert.match(sandboxClientSource, /deleteAgentSession\([\s\S]*kind: SandboxAgentKind/);
  assert.match(sandboxClientSource, /sendMessage\([\s\S]*options\?: SandboxRequestOptions/);
  assert.match(sandboxClientSource, /closeSession\([\s\S]*options\?: SandboxRequestOptions/);
  assert.match(sandboxClientSource, /signal\?: AbortSignal/);
  assert.match(sandboxClientSource, /\/web\/sandbox\/sessions/);
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

test("sandbox errors preserve HTTP status and backend detail", () => {
  assert.match(sandboxClientSource, /const text = await response\.text\(\)\.catch\(\(\) => ""\)/);
  assert.match(sandboxClientSource, /nestedDetail \?\? payload\.error \?\? payload\.message/);
  assert.match(sandboxClientSource, /detail == null[\s\S]*?JSON\.stringify\(detail\)/);
  assert.match(sandboxClientSource, /`\$\{fallback\}（HTTP \$\{response\.status\}）`/);
  assert.match(sandboxClientSource, /text \? `\$\{summary\}：\$\{text\}` : summary/);
});

test("new-chat built-in agent mode launches the AgentKit sandbox", () => {
  assert.match(modeSelectorSource, /value: "temporary"[\s\S]*?label: "内置智能体"/);
  assert.match(appSource, /mode === "temporary"[\s\S]*?openSandboxLaunch\(\)/);
  assert.doesNotMatch(appSource, /<SandboxEntryButton/);
});

test("sandbox launch dialog covers confirmation loading failure and retry", () => {
  assert.match(dialogSource, /role="dialog"/);
  assert.match(dialogSource, /`创建 \$\{agentLabel\} 智能体`/);
  assert.doesNotMatch(dialogSource, /创建一个可重复进入的 AgentKit Session/);
  assert.match(dialogSource, /<span>智能体名称<\/span>/);
  assert.match(dialogSource, /type="text"[\s\S]*?required/);
  assert.match(dialogSource, /`正在创建 \$\{agentLabel\} 智能体`/);
  assert.match(dialogSource, /正在创建并等待 \{agentLabel\} 智能体就绪，这通常需要半分钟/);
  assert.match(dialogSource, /启动失败/);
  assert.match(dialogSource, /重新尝试/);
  assert.match(dialogSource, /确认创建/);
  assert.match(dialogSource, /nativeEvent\.isComposing/);
  assert.match(dialogSource, /if \(event\.key === "Escape"/);
  assert.match(appSource, /sandboxLaunchAbortRef\.current\?\.abort\(\)/);
});

test("active sandbox conversation identifies the selected agent and never uses normal sessions", () => {
  assert.match(sandboxSessionSource, /当前您在使用 \{agentName\} 智能体/);
  assert.doesNotMatch(sandboxSessionSource, /退出后对话内容消失/);
  assert.match(sandboxSessionSource, /退出当前智能体/);
  assert.doesNotMatch(sandboxSessionSource, /退出内置智能体/);
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

test("sandbox agents expose detail deletion and reusable workspaces", () => {
  assert.match(detailsSource, /Session 详情/);
  assert.match(detailsSource, /删除智能体/);
  assert.match(detailsSource, /role="alertdialog"/);
  assert.match(detailsSource, /确认删除/);
  assert.match(appSource, /sandboxClient\.deleteSession\(session\.id\)/);
  assert.match(appSource, /sandboxClient\.deleteAgentSession\(session\.toolName, session\.id\)/);
  assert.match(workspaceSource, /主界面/);
  assert.match(workspaceSource, /终端/);
  assert.match(workspaceSource, /sandboxClient\.launchAgentTerminal/);
  assert.match(workspaceSource, /size="lg"/);
  assert.match(workspaceSource, /gutterSize="lg"/);
  assert.match(workspaceSource, /block/);
  assert.match(workspaceStyles, /\.sandbox-agent-workspace-tabs\s*\{[\s\S]*?width: 200px/);
  assert.match(workspaceStyles, /@media \(max-width: 720px\)[\s\S]*?\.sandbox-agent-workspace-tabs\s*\{[\s\S]*?width: 100%/);
});

test("disconnecting Codex keeps the agent while deletion removes it", () => {
  assert.match(sandboxClientSource, /\/disconnect/);
  assert.match(sandboxClientSource, /async deleteSession\([\s\S]*?method: "DELETE"/);
  assert.match(appSource, /\.closeSession\(closingSession\.id\)/);
  assert.match(appSource, /await sandboxClient\.deleteSession\(session\.id\)/);
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
