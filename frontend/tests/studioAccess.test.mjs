import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

const appSource = read("App.tsx");
const clientSource = read("adk/client.ts");
const connectionsSource = read("adk/connections.ts");
const selectorSource = read("ui/AgentSelector.tsx");
const sidebarSource = read("ui/Sidebar.tsx");
const stylesSource = read("styles.css");

test("Studio access fails closed until the server-derived role is known", () => {
  assert.match(clientSource, /export type StudioRole = "admin" \| "developer" \| "user"/);
  assert.match(clientSource, /export const DEFAULT_STUDIO_ACCESS[\s\S]*?createAgents: false[\s\S]*?manageAgents: false[\s\S]*?runtimeScope: "mine"/);
  assert.match(clientSource, /apiFetch\("\/web\/access"\)/);
  assert.match(appSource, /if \(!access\) \{\s*return <div className="boot" \/>;\s*\}/);
  assert.match(appSource, /setAccess\(DEFAULT_STUDIO_ACCESS\)/);
});

test("ordinary users cannot render or open Agent creation and management", () => {
  assert.match(sidebarSource, /access\.capabilities\.createAgents && show\("addAgent"\)/);
  assert.match(sidebarSource, /access\.capabilities\.manageAgents && show\("manageAgents"\)/);
  assert.match(appSource, /const visibleCreateView = canCreateAgents \? createView : null/);
  assert.match(appSource, /const showManageAgents = canManageAgents && manageAgents/);
  assert.match(appSource, /if \(!canCreateAgents\)[\s\S]*?当前账号没有添加 Agent 的权限/);
  assert.match(appSource, /if \(!canManageAgents\)[\s\S]*?当前账号没有管理 Agent 的权限/);
});

test("sidebar shows the OAuth email and translated role badge", () => {
  assert.match(sidebarSource, /admin: "管理员"/);
  assert.match(sidebarSource, /developer: "开发者"/);
  assert.match(sidebarSource, /user: "普通用户"/);
  assert.match(sidebarSource, /typeof userInfo\.email === "string"/);
  assert.match(sidebarSource, /<SidebarUser access=\{access\}/);
  assert.match(stylesSource, /studio-role-badge--admin[\s\S]*?hsl\(271/);
  assert.match(stylesSource, /studio-role-badge--developer[\s\S]*?hsl\(47/);
  assert.match(stylesSource, /studio-role-badge--user[\s\S]*?hsl\(145/);
});

test("runtime selection obeys the server-granted scope", () => {
  assert.match(selectorSource, /const \[mineOnly, setMineOnly\] = useState\(runtimeScope === "mine"\)/);
  assert.match(selectorSource, /setMineOnly\(runtimeScope === "mine"\)/);
  assert.match(selectorSource, /\{runtimeScope === "all" && \(/);
  assert.match(selectorSource, /getRuntimes\(\{[\s\S]*?scope: "mine"/);
  assert.doesNotMatch(clientSource, /new URLSearchParams\(\{\s*author,/);
});

test("runtime authorization failures are not reported as unsupported", () => {
  assert.match(clientSource, /response\.clone\(\)\.json\(\)/);
  assert.match(clientSource, /runtime_access_denied/);
  assert.match(clientSource, /res\.status === 404[\s\S]*?RuntimeProbeError/);
  assert.match(clientSource, /res\.status === 401 \|\| res\.status === 403/);
  assert.match(clientSource, /error instanceof RuntimeAccessDeniedError \|\|[\s\S]*?error instanceof RuntimeProbeError/);
  assert.match(selectorSource, /error instanceof RuntimeAccessDeniedError[\s\S]*?setError\(error\.message\)/);
  assert.match(selectorSource, /error instanceof RuntimeProbeError[\s\S]*?setError\(error\.message\)/);
  assert.match(connectionsSource, /removeRuntimeConnection\(runtimeId\)/);
});

test("selected Agent icons are optically aligned with the label", () => {
  assert.match(stylesSource, /\.agent-row\s*{[^}]*align-items: center/);
  assert.doesNotMatch(stylesSource, /\.agent-row-lead[^}]*transform:/);
  assert.match(stylesSource, /\.agent-row-chev\.open[^}]*translateY\(1px\) rotate\(90deg\)/);
});

test("deployment and management requests rely on server identity, not author input", () => {
  assert.doesNotMatch(clientSource, /author: opts\?\.author/);
  assert.doesNotMatch(clientSource, /my-runtimes\?author=/);
  assert.doesNotMatch(appSource, /<ManageAgentsView[\s\S]*?author=/);
});
