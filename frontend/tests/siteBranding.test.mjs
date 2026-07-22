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
const textShimmerSource = readFileSync(
  new URL("../src/ui/text-shimmer/TextShimmer.tsx", import.meta.url),
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
  assert.match(
    loginSource,
    /<TextShimmer as="h1" className="login-title"[\s\S]*?\{branding\.title\}[\s\S]*?<\/TextShimmer>/,
  );
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

test("connected cloud Agent uses a calm green selector icon", () => {
  assert.match(sidebarSource, /agent-row--connected/);
  assert.match(
    stylesSource,
    /\.agent-row--connected \.agent-row-lead\s*\{[^}]*color:\s*hsl\(142 48% 38%\);/,
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
  assert.match(sidebarSource, /const MAIN_PANEL_TOP_PX = 54;/);
  assert.match(sidebarSource, /anchorTop=\{MAIN_PANEL_TOP_PX\}/);
});

test("welcome headings share the neutral TextShimmer and stable smoke avatars", () => {
  assert.match(sidebarSource, /function smokeAvatarStyle/);
  assert.match(sidebarSource, /style=\{avatarStyle\}/);
  assert.match(appSource, /<TextShimmer as="h1" className="welcome-title"/);
  assert.match(loginSource, /<TextShimmer as="h1" className="login-title"/);
  assert.match(textShimmerSource, /hsl\(var\(--muted-foreground\)\)/);
  assert.match(textShimmerSource, /hsl\(var\(--foreground\)\) 50%/);
  assert.doesNotMatch(stylesSource, /welcome-smoke-shimmer/);
  assert.match(stylesSource, /@keyframes avatar-smoke-drift/);
  assert.match(
    stylesSource,
    /\.account-avatar\s*\{[\s\S]*?border:\s*none;[\s\S]*?border-radius:\s*9px;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(stylesSource, /\.account-avatar--lg\s*\{[\s\S]*?border-radius:\s*11px;/);
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation-duration:\s*0\.001ms !important;/,
  );
});

test("OAuth profile pictures fall back to the generated account avatar", () => {
  assert.match(sidebarSource, /profilePictureUrl\(userInfo\)/);
  assert.match(sidebarSource, /pictureUrl === failedAvatarUrl \? "" : pictureUrl/);
  assert.match(sidebarSource, /className="account-avatar-image"/);
  assert.match(
    sidebarSource,
    /onError=\{\(\) => setFailedAvatarUrl\(visiblePictureUrl\)\}/,
  );
  assert.match(
    stylesSource,
    /\.account-avatar-image\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?object-fit:\s*cover;/,
  );
});
