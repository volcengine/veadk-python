import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const applicationsSource = readFileSync(
  new URL("../src/ui/Applications.tsx", import.meta.url),
  "utf8",
);
const applicationsStyles = readFileSync(
  new URL("../src/ui/Applications.css", import.meta.url),
  "utf8",
);
const githubLogoSource = readFileSync(
  new URL("../src/ui/GitHubLogo.tsx", import.meta.url),
  "utf8",
);
const githubSource = readFileSync(
  new URL("../src/ui/GitHubIntegration.tsx", import.meta.url),
  "utf8",
);
const githubStyles = readFileSync(
  new URL("../src/ui/GitHubIntegration.css", import.meta.url),
  "utf8",
);
const apiSource = readFileSync(
  new URL("../src/adk/githubIntegration.ts", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("adds the Automation destination with a repository-owned four-circle icon", () => {
  assert.match(sidebarSource, /SidebarPage = "new-chat" \| "agents" \| "applications" \| "search"/);
  assert.match(sidebarSource, /onApplications: \(\) => void/);
  assert.match(sidebarSource, /function ApplicationsIcon/);
  assert.equal((sidebarSource.match(/<circle /g) ?? []).length >= 4, true);
  assert.match(sidebarSource, /aria-label="自动化"/);
  assert.match(sidebarSource, /<span className="sidebar-nav-label">自动化<\/span>/);
  assert.match(appSource, /onApplications=\{openApplicationsPage\}/);
});

test("renders a searchable automation catalog with Runtime delivery first", () => {
  assert.match(applicationsSource, /<h1>自动化<\/h1>/);
  assert.match(applicationsSource, /aria-label="搜索自动化"/);
  assert.match(applicationsSource, /placeholder="搜索自动化"/);
  assert.match(applicationsSource, /label: "研发"/);
  assert.match(applicationsSource, /name: "AgentKit Runtime 持续交付"/);
  assert.match(applicationsSource, /为您的仓库添加持续交付到 AgentKit Runtime 的自动化工作流/);
  assert.match(applicationsSource, /className="application-card"[\s\S]*?onClick=\{onOpenGitHub\}/);
  assert.match(applicationsSource, /<GitHubLogo className="application-card-icon"/);
  assert.doesNotMatch(applicationsSource, /查看集成|application-card-heading|application\.category/);
  assert.doesNotMatch(applicationsStyles, /\.application-card > button/);
  assert.match(applicationsStyles, /\.application-card \{[\s\S]*?min-height: 96px/);
  assert.match(githubLogoSource, /GitHub's official mark/);
  assert.match(githubLogoSource, /fill="currentColor"/);
  assert.match(applicationsSource, /useDeferredValue\(query\)/);
  assert.match(applicationsSource, /没有匹配的自动化/);
  assert.match(applicationsStyles, /grid-template-columns: repeat\(auto-fill, minmax\(min\(280px, 100%\), 1fr\)\)/);
});

test("GitHub detail keeps credentials ephemeral and exposes accessible submission states", () => {
  assert.match(githubSource, /<h1>AgentKit Runtime 持续交付<\/h1>/);
  assert.match(githubSource, /aria-label="返回自动化列表"/);
  assert.doesNotMatch(githubSource, /<h2>持续发布到 AgentKit Runtime<\/h2>/);
  assert.doesNotMatch(githubSource, /权限与安全|PR 记录|role="tablist"/);
  assert.match(githubSource, /type=\{showToken \? "text" : "password"\}/);
  assert.match(githubSource, /autoComplete="off"/);
  assert.match(githubSource, /获取 Token/);
  assert.match(githubSource, /personal-access-tokens\/new/);
  assert.match(githubSource, /required \? "必填" : "可选"/);
  assert.match(githubSource, /baseBranch: form\.baseBranch\.trim\(\) \|\| "main"/);
  assert.match(githubSource, /projectPath: form\.projectPath\.trim\(\) \|\| "\."/);
  assert.match(githubSource, /目录内需包含 app\.py，导出由/);
  assert.match(githubSource, /create_agentkit_app\(root_agent, …\)/);
  assert.match(githubSource, /run_agentkit_app\(app\)/);
  assert.match(githubSource, /className="pp-region-trigger"/);
  assert.match(githubSource, /role="listbox" aria-label="地域"/);
  assert.doesNotMatch(githubSource, /<select/);
  assert.match(githubSource, /VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY（必填）/);
  assert.match(githubSource, /VOLCENGINE_SESSION_TOKEN（使用临时凭据时必填）/);
  assert.doesNotMatch(appSource, /applicationsView !== "github" \? <Sidebar/);
  assert.match(appSource, /<Sidebar[\s\S]*?onApplications=\{openApplicationsPage\}/);
  assert.match(githubStyles, /\.github-section-panel \{[\s\S]*?border: 0/);
  assert.match(githubStyles, /\.github-section-panel \{[\s\S]*?background: transparent/);
  assert.match(githubSource, /提交 PR 中/);
  assert.match(githubSource, /role="alert"/);
  assert.match(githubSource, /event\.nativeEvent\.isComposing/);
  assert.doesNotMatch(githubSource, /localStorage|sessionStorage/);
  assert.match(apiSource, /\/web\/integrations\/github\/pull-requests/);
  assert.doesNotMatch(apiSource, /console\.(?:log|warn|error)/);
});
