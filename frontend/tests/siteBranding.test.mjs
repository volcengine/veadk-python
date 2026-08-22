import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const searchSource = readFileSync(
  new URL("../src/ui/Search.tsx", import.meta.url),
  "utf8",
);
const navbarSource = readFileSync(
  new URL("../src/ui/Navbar.tsx", import.meta.url),
  "utf8",
);
const agentSelectorSource = readFileSync(
  new URL("../src/ui/AgentSelector.tsx", import.meta.url),
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
const sidebarIconsSource = readFileSync(
  new URL("../src/ui/icons/SidebarIcons.tsx", import.meta.url),
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
  assert.match(clientSource, /title: "AgentKit Studio"/);
  assert.match(appSource, /import defaultSiteLogo from "\.\/assets\/logo\.svg"/);
  assert.match(appSource, /document\.title = studioDocumentTitle/);
  assert.match(appSource, /cloudProvider === "byteplus" \? byteplusLogo : defaultSiteLogo/);
  assert.match(sidebarSource, /\{branding\.title\}/);
  assert.match(sidebarSource, /import defaultSiteLogo from "\.\.\/assets\/logo\.svg"/);
  assert.match(sidebarSource, /cloudProvider === "byteplus" \? byteplusLogo : defaultSiteLogo/);
  assert.match(sidebarSource, /branding\.logoUrl \|\| fallbackLogo/);
  assert.match(sidebarSource, /width=\{20\}\s*height=\{20\}/);
  assert.match(
    sidebarSource,
    /className="brand"[\s\S]*?onClick=\{onNewChat\}[\s\S]*?aria-label="返回首页"/,
  );
  assert.match(loginSource, /width=\{20\}\s*height=\{20\}/);
  assert.match(loginSource, /import defaultSiteLogo from "\.\.\/assets\/logo\.svg"/);
  assert.match(loginSource, /cloudProvider === "byteplus" \? byteplusLogo : defaultSiteLogo/);
  assert.match(loginSource, /branding\.logoUrl \|\| fallbackLogo/);
  assert.match(
    loginSource,
    /<TextShimmer as="h1" className="login-title"[\s\S]*?\{branding\.title\}[\s\S]*?<\/TextShimmer>/,
  );
  assert.match(loginSource, /<p className="login-sub">登录以继续使用<\/p>/);
  assert.match(loginSource, /火山引擎 AgentKit 提供企业级 Agent 解决方案/);
  assert.match(loginSource, /BytePlus AgentKit 提供企业级 Agent 解决方案/);
  assert.match(loginSource, /继续即表示你已阅读并同意 AgentKit/);
  assert.match(loginSource, /https:\/\/docs\.volcengine\.com\/docs\/86681\/1925174\?lang=zh/);
  assert.match(loginSource, /https:\/\/docs\.byteplus\.com\/en\/docs\/legal/);
  assert.match(loginSource, /cloudProvider: "volcengine" \| "byteplus"/);
  assert.match(loginSource, /target="_blank"/);
  assert.match(
    stylesSource,
    /\.brand-logo\s*\{[\s\S]*?width:\s*22px;[\s\S]*?height:\s*22px;[\s\S]*?flex:\s*0 0 22px;/,
  );
  assert.match(
    stylesSource,
    /\.login-brand-logo\s*\{[\s\S]*?width:\s*20px;[\s\S]*?height:\s*20px;[\s\S]*?flex:\s*0 0 20px;/,
  );
  assert.match(stylesSource, /object-fit: contain/);
  assert.match(
    stylesSource,
    /\.brand-logo,[\s\S]*?\.brand-title,[\s\S]*?\.brand\s*\{[\s\S]*?cursor:\s*pointer;/,
  );
  assert.match(
    stylesSource,
    /@font-face\s*\{[\s\S]*?font-family:\s*"Byte Sans";[\s\S]*?ByteSans-Medium\.ttf[\s\S]*?font-weight:\s*500;/,
  );
  assert.match(
    stylesSource,
    /\.brand\s*\{[\s\S]*?font-size:\s*17px;[\s\S]*?line-height:\s*1\.4;/,
  );
  assert.match(
    stylesSource,
    /\.brand-title\s*\{[\s\S]*?font-family:\s*"Byte Sans",\s*ui-sans-serif,/,
  );
  assert.match(
    stylesSource,
    /\.login-brand-logo,[\s\S]*?\.login-brand,[\s\S]*?\.login-title\s*\{[\s\S]*?cursor:\s*text;/,
  );
  assert.match(htmlSource, /<link rel="icon" type="image\/svg\+xml" href="\/src\/assets\/logo\.svg" \/>/);
  assert.match(htmlSource, /<title>AgentKit Studio<\/title>/);
});

test("global sidebar can collapse to a compact icon rail", () => {
  assert.match(sidebarSource, /const SIDEBAR_AUTO_COLLAPSE_QUERY = "\(max-width: 860px\)"/);
  assert.match(
    sidebarSource,
    /const \[collapsed, setCollapsed\] = useState\(\s*autoCollapse \|\| autoCollapsedRef\.current,?\s*\)/,
  );
  assert.match(sidebarSource, /query\.addEventListener\("change", handleViewportChange\)/);
  assert.match(sidebarSource, /autoCollapsedRef\.current = false;\s*setCollapsed\(\(value\) => !value\)/);
  assert.match(sidebarSource, /aria-label=\{collapsed \? "展开侧边栏" : "收起侧边栏"\}/);
  assert.match(
    stylesSource,
    /\.sidebar\s*\{[\s\S]*?width:\s*240px;[\s\S]*?background:\s*hsl\(var\(--sidebar\)\);/,
  );
  assert.match(stylesSource, /\.sidebar\.is-collapsed\s*\{[\s\S]*?width:\s*56px;/);
  assert.doesNotMatch(
    stylesSource,
    /@media \(max-width:\s*860px\)[\s\S]*?\.sidebar\s*\{[\s\S]*?width:\s*204px;/,
  );
  assert.match(
    stylesSource,
    /\.sidebar\.is-collapsed \.sidebar-history\s*\{[\s\S]*?display:\s*none;/,
  );
});

test("expanded sidebar navigation keeps equal visual gutters beside the main panel", () => {
  assert.match(
    stylesSource,
    /\.sidebar:not\(\.is-collapsed\) \.sidebar-top\s*\{[\s\S]*?padding-inline:\s*8px;/,
  );
  assert.match(
    stylesSource,
    /\.sidebar:not\(\.is-collapsed\) \.sidebar-brand-row\s*\{[\s\S]*?padding-right:\s*0;/,
  );
  assert.match(
    stylesSource,
    /\.new-chat\s*\{[\s\S]*?width:\s*100%;[\s\S]*?gap:\s*8px;[\s\S]*?padding:\s*7px 10px;/,
  );
  assert.match(
    stylesSource,
    /\.new-chat:hover,[\s\S]*?\.new-chat\.is-active\s*\{\s*background:\s*hsl\(var\(--sidebar-item-hover\)\);/,
  );
});

test("sidebar navigation uses the Figma-aligned custom icons", () => {
  assert.match(sidebarSource, /<NewChatIcon className="icon" \/>/);
  assert.match(sidebarSource, /<SidebarAgentIcon className="icon" \/>/);
  assert.match(sidebarSource, /<ResourceLibraryIcon className="icon" \/>/);
  assert.match(searchSource, /<SidebarSearchIcon className="icon" \/>/);
  assert.match(sidebarSource, /<SidebarExpandIcon className="icon" \/>/);
  assert.match(sidebarSource, /<SidebarCollapseIcon className="icon" \/>/);
  assert.doesNotMatch(sidebarSource, /PanelLeftOpen|PanelLeftClose/);
  assert.match(sidebarIconsSource, /export function SidebarCollapseIcon/);
  assert.match(sidebarIconsSource, /export function SidebarExpandIcon/);
  assert.match(sidebarIconsSource, /className="sidebar-panel-glyph__divider"/);
  assert.match(sidebarIconsSource, /className="sidebar-panel-glyph__frame"/);
  assert.match(
    stylesSource,
    /--sidebar-collapse-frame-stroke:\s*#0c0d0e;[\s\S]*?--sidebar-collapse-divider-fill:\s*#80838a;/,
  );
  assert.doesNotMatch(
    stylesSource,
    /new-chat--conversation:hover\s*>\s*\.icon|sidebar-plus-return/,
  );
  assert.match(
    stylesSource,
    /\.new-chat \.icon\s*\{[\s\S]*?width:\s*16px;[\s\S]*?height:\s*16px;[\s\S]*?flex:\s*0 0 16px;/,
  );
});

test("sidebar persistently highlights only the current top-level page", () => {
  assert.match(
    sidebarSource,
    /export type SidebarPage\s*=[\s\S]*?"new-chat"[\s\S]*?"agents"[\s\S]*?"applications"[\s\S]*?"search"[\s\S]*?"feedback"[\s\S]*?null/,
  );
  assert.match(sidebarSource, /activePage: SidebarPage/);
  assert.match(
    sidebarSource,
    /new-chat--conversation\$\{[\s\S]*?activePage === "new-chat" \? " is-active" : ""/,
  );
  assert.match(
    sidebarSource,
    /new-chat--agents\$\{[\s\S]*?activePage === "agents" \? " is-active" : ""/,
  );
  assert.match(
    sidebarSource,
    /new-chat--applications\$\{[\s\S]*?activePage === "applications" \? " is-active" : ""/,
  );
  assert.match(
    sidebarSource,
    /aria-current=\{activePage === "new-chat" \? "page" : undefined\}/,
  );
  assert.match(sidebarSource, /<SearchButton active=\{activePage === "search"\}/);
  assert.match(
    searchSource,
    /className=\{`new-chat\$\{active \? " is-active" : ""\}`\}[\s\S]*?aria-current=\{active \? "page" : undefined\}/,
  );
  assert.match(
    appSource,
    /const sidebarActivePage: SidebarPage =[\s\S]*?searchView[\s\S]*?myAgents \|\| manageAgents \|\| sandboxAgentDetailTarget \|\| sandboxAgentWorkspace[\s\S]*?sessionId[\s\S]*?"new-chat"/,
  );
  assert.match(appSource, /<Sidebar[\s\S]*?activePage=\{sidebarActivePage\}/);
  assert.match(
    stylesSource,
    /\.new-chat:hover,\s*\.new-chat\.is-active\s*\{\s*background:\s*hsl\(var\(--sidebar-item-hover\)\);\s*\}/,
  );
});

test("the main navbar owns the complete Agent selector", () => {
  assert.match(navbarSource, /<AgentSelector[\s\S]*?variant="navbar"/);
  assert.doesNotMatch(sidebarSource, /<AgentSelector/);
  assert.match(agentSelectorSource, /const active = currentRuntime\?\.runtimeId === rt\.runtimeId/);
  assert.match(agentSelectorSource, /<RuntimeIdentityIcon \/>/);
});

test("history header offers a borderless new-session action", () => {
  assert.match(
    sidebarSource,
    /className="history-new-chat"[\s\S]*?onClick=\{sandboxHistory\?\.onNew \?\? onNewChat\}[\s\S]*?aria-label="新建会话"/,
  );
  assert.match(
    stylesSource,
    /\.history-new-chat\s*\{[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;/,
  );
  assert.match(
    stylesSource,
    /\.history-head\s*\{[\s\S]*?height:\s*32px;[\s\S]*?padding:\s*0 18px;[\s\S]*?font-size:\s*13px;[\s\S]*?font-weight:\s*400;[\s\S]*?line-height:\s*22px;[\s\S]*?color:\s*hsl\(var\(--sidebar-section-title\)\);/,
  );
  assert.match(
    stylesSource,
    /\.history-new-chat:hover\s*\{[\s\S]*?background:\s*transparent;[\s\S]*?color:\s*hsl\(var\(--foreground\)\);/,
  );
});

test("main panel fills the shell edge to edge with no global navbar", () => {
  assert.match(
    stylesSource,
    /\.sidebar-brand-row\s*\{[\s\S]*?height:\s*64px;[\s\S]*?min-height:\s*64px;[\s\S]*?padding:\s*0 0 0 8px;/,
  );
  assert.match(
    stylesSource,
    /\.main\s*\{[\s\S]*?flex:\s*1;[\s\S]*?margin:\s*0;[\s\S]*?border:\s*0;[\s\S]*?border-radius:\s*0;/,
  );
  assert.doesNotMatch(appSource, /<Navbar\b/);
  assert.doesNotMatch(appSource, /<DeploymentTaskStatus\b/);
  assert.doesNotMatch(appSource, /<StudioUpdateControl\b/);
});

test("welcome heading uses the synchronized reveal while login keeps TextShimmer", () => {
  assert.match(sidebarSource, /function smokeAvatarStyle/);
  assert.match(sidebarSource, /style=\{avatarStyle\}/);
  assert.match(appSource, /<h1 className="welcome-title">/);
  assert.doesNotMatch(appSource, /<TextShimmer as="h1" className="welcome-title"/);
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
