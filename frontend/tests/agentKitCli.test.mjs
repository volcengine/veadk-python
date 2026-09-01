import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/AgentKitCliDialog.tsx", import.meta.url),
  "utf8",
);
const sandboxControlsSource = readFileSync(
  new URL("../src/ui/SandboxControls.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/agentkitCli.ts", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("places the AgentKit CLI entry between the promo and account", () => {
  assert.match(sidebarSource, /onAgentKitCli: \(\) => void/);
  assert.match(
    sidebarSource,
    /<AgentKitPromoCard[\s\S]*?className="new-chat sidebar-agentkit-cli"[\s\S]*?<SidebarUser/,
  );
  assert.match(sidebarSource, /<SandboxTerminalIcon className="icon" \/>[\s\S]*?AgentKit CLI/);
  assert.match(sidebarSource, /<span className="sidebar-nav-label">AgentKit CLI<\/span>/);
  assert.match(appSource, /onAgentKitCli=\{\(\) => setAgentKitCliOpen\(true\)\}/);
  assert.match(appSource, /<AgentKitCliDialog[\s\S]*?open=\{agentKitCliOpen\}/);
});

test("initializes a non-persistent per-user AgentKit CLI session", () => {
  assert.match(clientSource, /const API = "\/web\/agentkit-cli"/);
  assert.match(clientSource, /JSON\.stringify\(\{ persistent: false \}\)/);
  assert.match(dialogSource, /agentKitCliClient\.listSessions/);
  assert.match(dialogSource, /agentKitCliClient\.createSession/);
  assert.match(dialogSource, /agentKitCliClient\.openSession/);
  assert.match(dialogSource, /agentKitCliClient\.launchTerminal/);
  assert.match(dialogSource, /searching: "正在查找已有环境"/);
  assert.match(dialogSource, /creating: "环境初始化中"/);
  assert.match(dialogSource, /connecting: "正在连接已有环境"/);
  assert.match(dialogSource, /onStage\("searching"\)/);
  assert.match(dialogSource, /onStage\("creating"\)/);
  assert.match(dialogSource, /onStage\("connecting"\)/);
});

test("reuses the current terminal launch while its session is valid", () => {
  assert.match(
    dialogSource,
    /if \(launch && isLaunchReusable\(expireAt, Date\.now\(\)\)\) \{[\s\S]*?setState\("ready"\);[\s\S]*?return undefined;/,
  );
  assert.doesNotMatch(
    dialogSource,
    /if \(!open\) return undefined;[\s\S]{0,120}setLaunch\(null\);/,
  );
  assert.match(dialogSource, /<DialogShell[\s\S]*?keepMounted/);
  assert.match(sandboxControlsSource, /if \(!open && !keepMounted\) return null/);
  assert.match(sandboxControlsSource, /hidden=\{!open\}/);
});

test("shows configuration, retry, terminal, and expiry states", () => {
  assert.match(
    clientSource,
    /管理员未配置 AgentKit Dev Sandbox，请配置后再使用/,
  );
  assert.match(dialogSource, /小时 \$\{minutes\} 分钟后环境回收/);
  assert.match(dialogSource, /分钟后环境回收/);
  assert.doesNotMatch(dialogSource, /在专属 Dev Sandbox Session 中体验 AgentKit CLI/);
  assert.match(dialogSource, /AgentKit CLI 请求失败/);
  assert.match(dialogSource, /agentkit-cli-error-detail/);
  assert.match(dialogSource, /未收到服务端响应/);
  assert.match(dialogSource, /原始错误/);
  assert.match(clientSource, /httpErrorMessage\(response, fallback\)/);
  assert.match(dialogSource, />\s*重试\s*</);
  assert.match(dialogSource, /title="AgentKit CLI 终端"/);
});
