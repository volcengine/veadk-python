import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const loginSource = readFileSync(
  new URL("../src/ui/LoginPage.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const htmlSource = readFileSync(
  new URL("../index.html", import.meta.url),
  "utf8",
);

test("applies configured branding to the UI, document title, and favicon", () => {
  assert.match(appSource, /document\.title = siteBranding\.title/);
  assert.match(appSource, /favicon\.href = siteBranding\.logoUrl \|\| defaultSiteLogo/);
  assert.match(sidebarSource, /\{branding\.title\}/);
  assert.match(sidebarSource, /branding\.logoUrl \|\| volcengineLogo/);
  assert.match(sidebarSource, /width=\{20\}\s*height=\{20\}/);
  assert.match(loginSource, /width=\{20\}\s*height=\{20\}/);
  assert.match(loginSource, /<h1 className="login-title">\{branding\.title\}<\/h1>/);
  assert.match(loginSource, /<p className="login-sub">登录以继续使用<\/p>/);
  assert.match(loginSource, /火山引擎 AgentKit 提供企业级 Agent 解决方案/);
  assert.match(stylesSource, /flex: 0 0 20px/);
  assert.match(stylesSource, /object-fit: contain/);
  assert.match(htmlSource, /<link rel="icon"/);
  assert.match(htmlSource, /<title>VeADK Studio<\/title>/);
});

test("global sidebar can collapse to a compact icon rail", () => {
  assert.match(sidebarSource, /const SIDEBAR_AUTO_COLLAPSE_QUERY = "\(max-width: 860px\)"/);
  assert.match(sidebarSource, /const \[collapsed, setCollapsed\] = useState\(autoCollapsedRef\.current\)/);
  assert.match(sidebarSource, /query\.addEventListener\("change", handleViewportChange\)/);
  assert.match(sidebarSource, /autoCollapsedRef\.current = false;\s*setCollapsed\(\(value\) => !value\)/);
  assert.match(sidebarSource, /aria-label=\{collapsed \? "展开侧边栏" : "收起侧边栏"\}/);
  assert.match(stylesSource, /\.sidebar\s*\{[\s\S]*?width:\s*236px;/);
  assert.match(stylesSource, /\.sidebar\.is-collapsed\s*\{[\s\S]*?width:\s*56px;/);
  assert.match(
    stylesSource,
    /\.sidebar\.is-collapsed \.sidebar-history\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("history header offers a borderless new-session action", () => {
  assert.match(
    sidebarSource,
    /className="history-new-chat"[\s\S]*?onClick=\{onNewChat\}[\s\S]*?aria-label="新建会话"/,
  );
  assert.match(
    stylesSource,
    /\.history-new-chat\s*\{[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;/,
  );
  assert.match(stylesSource, /\.history-head\s*\{[\s\S]*?padding:\s*8px 10px 6px 20px;/);
  assert.match(
    stylesSource,
    /\.history-new-chat:hover\s*\{[\s\S]*?background:\s*transparent;[\s\S]*?color:\s*hsl\(var\(--foreground\)\);/,
  );
});

test("sidebar brand row aligns with the main header", () => {
  assert.match(
    stylesSource,
    /\.sidebar-brand-row\s*\{[\s\S]*?height:\s*54px;[\s\S]*?min-height:\s*54px;[\s\S]*?padding:\s*0 0 0 10px;/,
  );
  assert.match(
    stylesSource,
    /\.navbar\s*\{[\s\S]*?flex:\s*0 0 54px;[\s\S]*?padding:\s*0 10px;/,
  );
});

test("welcome headings use a restrained neutral shimmer and stable smoke avatars", () => {
  assert.match(sidebarSource, /function smokeAvatarStyle/);
  assert.match(sidebarSource, /style=\{avatarStyle\}/);
  assert.match(stylesSource, /@keyframes welcome-smoke-shimmer/);
  assert.match(stylesSource, /@keyframes avatar-smoke-drift/);
  assert.match(
    stylesSource,
    /\.account-avatar\s*\{[\s\S]*?border:\s*none;[\s\S]*?border-radius:\s*9px;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(stylesSource, /\.account-avatar--lg\s*\{[\s\S]*?border-radius:\s*11px;/);
  assert.match(
    stylesSource,
    /\.welcome-title\s*\{[\s\S]*?hsl\(42 8% 68%\)[\s\S]*?animation:\s*welcome-smoke-shimmer 9s/,
  );
  assert.match(
    stylesSource,
    /\.login-title\s*\{[\s\S]*?hsl\(42 8% 66%\)[\s\S]*?animation:\s*welcome-smoke-shimmer 9s/,
  );
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.account-avatar\s*\{[\s\S]*?animation:\s*none;/,
  );
});
