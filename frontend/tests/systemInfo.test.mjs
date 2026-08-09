import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

const appSource = read("App.tsx");
const clientSource = read("adk/client.ts");
const sidebarSource = read("ui/Sidebar.tsx");
const systemInfoSource = read("ui/SystemInfo.tsx");
const systemInfoStylesSource = read("ui/SystemInfo.css");

test("account menu navigates to the system information page", () => {
  assert.match(clientSource, /version: string;/);
  assert.match(appSource, /setVersion\(cfg\.version\)/);
  assert.match(
    appSource,
    /<SystemInfo version=\{version\} localMode=\{agentsSource === "local"\} \/>/,
  );
  assert.match(appSource, /const \[systemInfo, setSystemInfo\] = useState\(false\)/);
  assert.match(
    sidebarSource,
    /系统信息[\s\S]*?退出登录/,
    "system information should appear above logout",
  );
  assert.match(sidebarSource, /onSystemInfo\(\)/);
  assert.doesNotMatch(sidebarSource, /role="dialog"/);
  assert.doesNotMatch(sidebarSource, /createPortal/);
});

test("system information page lists sandbox tools and the current identity user pool", () => {
  assert.match(clientSource, /\/web\/system-info/);
  assert.match(systemInfoSource, /当前版本/);
  assert.match(systemInfoSource, />通用</);
  assert.match(systemInfoSource, />沙箱信息</);
  assert.match(systemInfoSource, /用户池/);
  assert.match(systemInfoSource, /listIdentityUserPools/);
  assert.match(systemInfoSource, /pools\.filter\(\(pool\) => pool\.isCurrent\)/);
  assert.match(systemInfoSource, /重新加载/);
  assert.match(systemInfoSource, /setSandboxReloadKey/);
  assert.match(systemInfoSource, /setUserPoolsReloadKey/);
  assert.match(systemInfoSource, /role="alert"/);
  assert.match(systemInfoSource, /未配置/);
  assert.match(systemInfoSource, /本地模式未配置用户池/);
  assert.match(systemInfoSource, /当前 Studio 未配置用户池/);
  assert.match(systemInfoSource, /Volcengine credentials not found/);
  assert.match(systemInfoStylesSource, /\.system-info-page\s*\{[^}]*padding:\s*32px 32px 0;/);
  assert.match(systemInfoStylesSource, /font-family:\s*inherit/);
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-tool,\s*\.system-info-pool\s*\{/,
  );
  assert.match(
    systemInfoStylesSource,
    /\.system-info-pool\s*\{[^}]*padding:\s*4px 0;[^}]*\}/,
  );
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-pool\s*\{[^}]*(?:background|border):/,
  );
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-empty\s*\{[^}]*background:/,
  );
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-loading\s*\{[^}]*(?:background|border|border-radius):/,
  );
});
