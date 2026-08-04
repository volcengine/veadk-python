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
const githubSource = readFileSync(
  new URL("../src/ui/GitHubIntegration.tsx", import.meta.url),
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

test("adds the Applications destination with a repository-owned four-circle icon", () => {
  assert.match(sidebarSource, /SidebarPage = "new-chat" \| "agents" \| "applications" \| "search"/);
  assert.match(sidebarSource, /onApplications: \(\) => void/);
  assert.match(sidebarSource, /function ApplicationsIcon/);
  assert.equal((sidebarSource.match(/<circle /g) ?? []).length >= 4, true);
  assert.match(sidebarSource, /aria-label="应用"/);
  assert.match(sidebarSource, /<span className="sidebar-nav-label">应用<\/span>/);
  assert.match(appSource, /onApplications=\{openApplicationsPage\}/);
});

test("renders a searchable development catalog with GitHub as the first card", () => {
  assert.match(applicationsSource, /<h1>应用<\/h1>/);
  assert.match(applicationsSource, /aria-label="搜索应用"/);
  assert.match(applicationsSource, /placeholder="搜索应用"/);
  assert.match(applicationsSource, /label: "研发"/);
  assert.match(applicationsSource, /name: "GitHub 集成"/);
  assert.match(applicationsSource, /useDeferredValue\(query\)/);
  assert.match(applicationsSource, /没有匹配的应用/);
  assert.match(applicationsStyles, /grid-template-columns: repeat\(auto-fill, minmax\(min\(280px, 100%\), 1fr\)\)/);
});

test("GitHub detail keeps credentials ephemeral and exposes accessible submission states", () => {
  for (const heading of ["持续发布到 AgentKit Runtime", "权限与安全", "PR 记录"]) {
    assert.match(githubSource, new RegExp(heading));
  }
  assert.match(githubSource, /role="tablist"/);
  assert.match(githubSource, /type=\{showToken \? "text" : "password"\}/);
  assert.match(githubSource, /autoComplete="off"/);
  assert.match(githubSource, /提交 PR 中/);
  assert.match(githubSource, /role="alert"/);
  assert.match(githubSource, /event\.nativeEvent\.isComposing/);
  assert.doesNotMatch(githubSource, /localStorage|sessionStorage/);
  assert.match(apiSource, /\/web\/integrations\/github\/pull-requests/);
  assert.doesNotMatch(apiSource, /console\.(?:log|warn|error)/);
});

