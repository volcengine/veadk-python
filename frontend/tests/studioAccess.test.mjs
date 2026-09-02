import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

const appSource = read("App.tsx");
const clientSource = read("adk/client.ts");
const connectionsSource = read("adk/connections.ts");
const selectorSource = read("ui/AgentSelector.tsx");
const myAgentsSource = read("ui/MyAgents.tsx");
const sidebarSource = read("ui/Sidebar.tsx");
const stylesSource = read("styles.css");
const roleIconsSource = read("ui/icons/StudioRoleIcons.tsx");
const cliFrontendSource = readFileSync(
  new URL("../../veadk/cli/cli_frontend.py", import.meta.url),
  "utf8",
);

test("Studio access fails closed until the server-derived role is known", () => {
  assert.match(clientSource, /export type StudioRole = "admin" \| "developer" \| "user"/);
  assert.match(clientSource, /telemetry:\s*\{\s*userId: string;\s*accountId\?: string;\s*\}/);
  assert.match(clientSource, /export const DEFAULT_STUDIO_ACCESS[\s\S]*?userId: ""[\s\S]*?accountId: ""[\s\S]*?createAgents: false[\s\S]*?manageAgents: false[\s\S]*?runtimeScope: "mine"/);
  assert.match(clientSource, /typeof access\.telemetry\?\.userId !== "string"/);
  assert.match(appSource, /accountId: access\.telemetry\.accountId \?\? ""/);
  assert.match(clientSource, /apiFetch\("\/web\/access"\)/);
  assert.match(appSource, /if \(!access\) \{\s*return <div className="boot" \/>;\s*\}/);
  assert.match(appSource, /setAccess\(DEFAULT_STUDIO_ACCESS\)/);
});

test("Studio entry telemetry uses anonymous UI config metadata", () => {
  assert.match(clientSource, /accountId: typeof studio\.accountId === "string"/);
  assert.match(clientSource, /accountIdResolutionError:[\s\S]*?typeof studio\.accountIdResolutionError === "string"/);
  assert.match(appSource, /accountId: studio\?\.accountId \?\? ""/);
  assert.match(appSource, /accountIdResolutionError: studio\?\.accountIdResolutionError \?\? ""/);
  assert.match(appSource, /trackStudioEntryViewed\(\{ authState: "anonymous" \}\)/);
});

test("Agent workspace creation and update actions obey Studio access", () => {
  assert.doesNotMatch(sidebarSource, /access\.capabilities\.createAgents && show\("addAgent"\)/);
  assert.doesNotMatch(sidebarSource, /access\.capabilities\.manageAgents && show\("manageAgents"\)/);
  assert.doesNotMatch(sidebarSource, /onManageAgents/);
  assert.match(appSource, /<MyAgents[\s\S]*?canCreate=\{canCreateAgents\}/);
  assert.match(appSource, /const visibleCreateView = canCreateAgents \? createView : null/);
  assert.match(appSource, /const showManageAgents = manageAgents/);
  assert.match(appSource, /if \(!access\.capabilities\.manageAgents\) setManageAgents\(false\)/);
  assert.match(appSource, /<AgentWorkspace[\s\S]*?canCreate=\{canCreateAgents\}[\s\S]*?canUpdate=\{canCreateAgents \|\| canManageAgents\}/);
  assert.match(appSource, /const canViewAgentUsage = features\.agentUsage && canManageAgents/);
  assert.match(appSource, /<AgentWorkspace[\s\S]*?canViewUsage=\{canViewAgentUsage\}/);
  assert.match(appSource, /if \(!canCreateAgents\)[\s\S]*?当前账号没有添加 Agent 的权限/);
  assert.match(appSource, /if \(!canManageAgents && !canCreateAgents\)[\s\S]*?当前账号没有管理 Agent 的权限/);
});

test("sidebar shows the OAuth email and accessible role icons", () => {
  assert.match(sidebarSource, /admin: "管理员"/);
  assert.match(sidebarSource, /developer: "开发者"/);
  assert.match(sidebarSource, /user: "普通用户"/);
  assert.match(sidebarSource, /typeof userInfo\.email === "string"/);
  assert.match(sidebarSource, /<SidebarUser\s+access=\{access\}/);
  assert.match(sidebarSource, /<StudioRoleIcon role=\{role\} className="studio-role-icon__glyph" \/>/);
  assert.match(sidebarSource, /aria-label=\{label\}/);
  assert.match(sidebarSource, /title=\{label\}/);
  assert.match(roleIconsSource, /export function StudioRoleIcon/);
  assert.match(roleIconsSource, /case "admin"/);
  assert.match(roleIconsSource, /case "developer"/);
  assert.match(stylesSource, /\.studio-role-icon\s*\{[\s\S]*?width:\s*18px;[\s\S]*?height:\s*18px;/);
  assert.doesNotMatch(stylesSource, /studio-role-badge/);
});

test("runtime selection obeys the server-granted scope", () => {
  assert.match(selectorSource, /const \[mineOnly, setMineOnly\] = useState\(runtimeScope === "mine"\)/);
  assert.match(selectorSource, /setMineOnly\(runtimeScope === "mine"\)/);
  assert.match(selectorSource, /\{runtimeScope === "all" && \(/);
  assert.match(selectorSource, /getRuntimes\(\{[\s\S]*?scope: "mine"/);
  assert.match(
    myAgentsSource,
    /getRuntimesWithTimeoutRetry\(\{[\s\S]*?scope: runtimeScope,[\s\S]*?region/,
  );
  assert.match(appSource, /<MyAgents[\s\S]*?runtimeScope=\{access\.capabilities\.runtimeScope\}/);
  assert.doesNotMatch(clientSource, /new URLSearchParams\(\{\s*author,/);
});

test("runtime proxy region does not consume upstream API region filters", () => {
  assert.match(clientSource, /runtimeParams\.set\("_runtime_region", ep\.region\)/);
  assert.match(cliFrontendSource, /proxy_region = request\.query_params\.get\("_runtime_region"\)/);
  assert.match(cliFrontendSource, /if proxy_region is None:[\s\S]*?studio_query_params\.add\("region"\)/);
});

test("only administrators and developers receive Agent deployment controls", () => {
  assert.match(appSource, /<MyAgents[\s\S]*?canCreate=\{canCreateAgents\}/);
  assert.match(
    myAgentsSource,
    /\{createAgent \? \([\s\S]*?className="my-agent-create-card"/,
  );
  assert.match(myAgentsSource, /const createAgent = canCreate/);
});

test("runtime authorization failures are not reported as unsupported", () => {
  assert.match(clientSource, /response\.clone\(\)\.json\(\)/);
  assert.match(clientSource, /runtime_access_denied/);
  assert.match(clientSource, /runtime_private_endpoint_unreachable/);
  assert.match(clientSource, /Runtime 已部署成功，但当前 Studio 无法访问私网 Runtime/);
  assert.match(clientSource, /runtime_proxy_connect_error/);
  assert.match(clientSource, /runtime_proxy_timeout/);
  assert.match(clientSource, /Runtime 已部署成功，但 Studio 暂时无法连接服务/);
  assert.match(cliFrontendSource, /endpoint_network_type == "private"[\s\S]*?runtime_private_endpoint_unreachable/);
  assert.match(cliFrontendSource, /def _runtime_proxy_is_retryable_read[\s\S]*?\{"GET", "HEAD"\}/);
  assert.match(cliFrontendSource, /def _runtime_proxy_attempts[\s\S]*?endpoint_network_type == "private"[\s\S]*?return 1[\s\S]*?return 3 if _runtime_proxy_is_retryable_read\(method\) else 1/);
  assert.match(cliFrontendSource, /max_attempts = _runtime_proxy_attempts[\s\S]*?for attempt in range\(1, max_attempts \+ 1\)/);
  assert.match(cliFrontendSource, /except \(httpx\.ConnectError, httpx\.TimeoutException\)[\s\S]*?attempt < max_attempts[\s\S]*?runtime-proxy request retry/);
  assert.match(clientSource, /res\.status === 404[\s\S]*?RuntimeProbeError/);
  assert.match(clientSource, /res\.status === 401 \|\| res\.status === 403/);
  assert.match(clientSource, /error instanceof RuntimeAccessDeniedError \|\|[\s\S]*?error instanceof RuntimeProbeError/);
  assert.match(selectorSource, /error instanceof RuntimeAccessDeniedError[\s\S]*?setError\(error\.message\)/);
  assert.match(selectorSource, /error instanceof RuntimeProbeError[\s\S]*?setError\(error\.message\)/);
  assert.match(connectionsSource, /removeRuntimeConnection\(runtimeId\)/);
});

test("selected Agent icons are optically aligned with the label", () => {
  assert.match(stylesSource, /\.agentsel-item\s*{[^}]*align-items:\s*center/);
  assert.match(
    stylesSource,
    /\.agentsel-item \.icon\s*{[^}]*width:\s*16px;[^}]*height:\s*16px;/,
  );
  assert.doesNotMatch(stylesSource, /\.agentsel-item \.icon[^}]*transform:/);
});

test("deployment and management requests rely on server identity, not author input", () => {
  assert.doesNotMatch(clientSource, /author: opts\?\.author/);
  assert.doesNotMatch(clientSource, /my-runtimes\?author=/);
  assert.doesNotMatch(appSource, /<ManageAgentsView[\s\S]*?author=/);
});
