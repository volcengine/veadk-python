import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
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
const cliFrontendSource = readFileSync(
  new URL("../../veadk/cli/cli_frontend.py", import.meta.url),
  "utf8",
);
const registrySource = readFileSync(
  new URL("../src/automations/registry.ts", import.meta.url),
  "utf8",
);
const templateSource = readFileSync(
  new URL("../src/automations/templateProject.ts", import.meta.url),
  "utf8",
);
const deliverySource = readFileSync(
  new URL("../src/automations/runtimeDelivery.ts", import.meta.url),
  "utf8",
);
const reviewSource = readFileSync(
  new URL("../src/automations/pullRequestReview.ts", import.meta.url),
  "utf8",
);
const feishuSource = readFileSync(
  new URL("../src/automations/feishuBot.ts", import.meta.url),
  "utf8",
);
const feishuDetailSource = readFileSync(
  new URL("../src/automations/feishu/FeishuBotIntegration.tsx", import.meta.url),
  "utf8",
);
const feishuStyles = readFileSync(
  new URL("../src/automations/feishu/FeishuBotIntegration.css", import.meta.url),
  "utf8",
);
const feishuDeploymentSource = readFileSync(
  new URL("../src/automations/feishu/deployment.ts", import.meta.url),
  "utf8",
);
const websiteIntegrationSource = readFileSync(
  new URL("../src/automations/website-integration/WebsiteIntegration.tsx", import.meta.url),
  "utf8",
);
const websiteIntegrationApiSource = readFileSync(
  new URL("../src/adk/websiteIntegration.ts", import.meta.url),
  "utf8",
);
const websiteIntegrationLoaderSource = readFileSync(
  new URL("../public/website-integration.js", import.meta.url),
  "utf8",
);
const websiteIntegrationWidgetSource = readFileSync(
  new URL("../src/website-integration/WebsiteChatWidget.tsx", import.meta.url),
  "utf8",
);
const websiteIntegrationEntrySource = readFileSync(
  new URL("../src/website-integration/main.tsx", import.meta.url),
  "utf8",
);
const websiteIntegrationStyles = readFileSync(
  new URL("../src/website-integration/website-integration.css", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("places Automation below scheduled tasks without a beta badge", () => {
  assert.match(
    sidebarSource,
    /SidebarPage\s*=\s*[\s\S]*?"new-chat"[\s\S]*?"agents"[\s\S]*?"applications"[\s\S]*?"search"[\s\S]*?"feedback"/,
  );
  assert.match(sidebarSource, /onApplications: \(\) => void/);
  assert.match(sidebarSource, /function ApplicationsIcon/);
  assert.equal((sidebarSource.match(/<circle /g) ?? []).length >= 4, true);
  assert.match(sidebarSource, /aria-label="自动化"/);
  assert.match(sidebarSource, /<span className="sidebar-nav-label">自动化<\/span>/);
  assert.doesNotMatch(sidebarSource, /sidebar-cronjobs-beta|>\s*Beta\s*</);
  const searchIndex = sidebarSource.indexOf("<SearchButton");
  const cronJobsIndex = sidebarSource.indexOf('aria-label="定时任务"');
  const applicationsIndex = sidebarSource.indexOf('aria-label="自动化"');
  assert.equal(searchIndex >= 0, true);
  assert.equal(searchIndex < cronJobsIndex, true);
  assert.equal(cronJobsIndex < applicationsIndex, true);
  assert.match(
    appSource,
    /onApplications=\{\(\) => requestIntelligentNavigation\(openApplicationsPage\)\}/,
  );
});

test("renders category-filtered automations from independent capability modules", () => {
  assert.match(applicationsSource, /<h1>自动化<\/h1>/);
  assert.match(applicationsSource, /aria-label="搜索自动化"/);
  assert.match(applicationsSource, /placeholder="搜索自动化"/);
  assert.match(registrySource, /label: "研发"/);
  assert.match(registrySource, /label: "消息渠道"/);
  const registryListIndex = registrySource.indexOf("export const AUTOMATIONS");
  const templateIndex = registrySource.indexOf("templateProjectAutomation", registryListIndex);
  const deliveryIndex = registrySource.indexOf("runtimeDeliveryAutomation", registryListIndex);
  const reviewIndex = registrySource.indexOf("pullRequestReviewAutomation", registryListIndex);
  const feishuIndex = registrySource.indexOf("feishuBotAutomation", registryListIndex);
  assert.equal(templateIndex >= 0, true);
  assert.equal(templateIndex < deliveryIndex, true);
  assert.equal(deliveryIndex < reviewIndex, true);
  assert.equal(reviewIndex < feishuIndex, true);
  assert.match(templateSource, /在您的仓库中创建一个可持续交付到 AgentKit Runtime 的最简智能体/);
  assert.match(deliverySource, /name: "AgentKit Runtime 持续交付"/);
  assert.match(reviewSource, /name: "PR 自动评审"/);
  assert.match(feishuSource, /name: "飞书机器人"/);
  assert.match(feishuSource, /badge: "Beta"/);
  assert.match(feishuSource, /category: "channels"/);
  assert.match(feishuSource, /直接接入 AgentKit Runtime/);
  assert.match(applicationsSource, /application\.category === activeCategory/);
  assert.match(applicationsSource, /className="application-card"[\s\S]*?onClick=\{\(\) => onOpen\(application\.id\)\}/);
  assert.match(applicationsSource, /isCodingAgentsAutomationAvailable\(window\.location\.hostname\)/);
  assert.match(applicationsSource, /application\.id === "coding-agents" && !codingAgentsAvailable/);
  assert.match(applicationsSource, /<GitHubLogo className="application-card-icon"/);
  assert.match(applicationsSource, /feishu-logo\.svg/);
  assert.match(applicationsSource, /application-card-badge is-\$\{application\.badgeTone \|\| "default"\}/);
  assert.match(applicationsStyles, /\.application-card-badge\s*\{[\s\S]*?background: hsl\(var\(--destructive\)\);[\s\S]*?color: hsl\(0 0% 100%\)/);
  assert.match(applicationsStyles, /\.application-card-badge\.is-success\s*\{[\s\S]*?background: hsl\(145 52% 44% \/ 0\.12\);[\s\S]*?color: hsl\(145 55% 29%\)/);
  assert.doesNotMatch(applicationsSource, /查看集成|application-card-heading/);
  assert.doesNotMatch(applicationsStyles, /\.application-card > button/);
  assert.match(applicationsStyles, /\.application-card \{[\s\S]*?min-height: 96px/);
  assert.match(githubLogoSource, /GitHub's official mark/);
  assert.match(githubLogoSource, /fill="currentColor"/);
  assert.match(applicationsSource, /useDeferredValue\(query\)/);
  assert.match(applicationsSource, /没有匹配的自动化/);
  assert.match(applicationsStyles, /grid-template-columns: repeat\(auto-fill, minmax\(min\(280px, 100%\), 1fr\)\)/);
});

test("GitHub detail keeps credentials ephemeral and exposes accessible submission states", () => {
  assert.match(githubSource, /getGitHubAutomation\(automation\)/);
  assert.match(githubSource, /<h1>\{definition\.title\}<\/h1>/);
  assert.match(githubSource, /aria-label="返回自动化列表"/);
  assert.doesNotMatch(githubSource, /<h2>持续发布到 AgentKit Runtime<\/h2>/);
  assert.doesNotMatch(githubSource, /权限与安全|PR 记录|role="tablist"/);
  assert.match(githubSource, /type=\{showToken \? "text" : "password"\}/);
  assert.match(githubSource, /autoComplete="off"/);
  assert.match(githubSource, /获取 Token/);
  assert.match(githubSource, /personal-access-tokens\/new/);
  assert.match(githubSource, /required \? "必填" : "可选"/);
  assert.match(githubSource, /definition\.fields\.map\(field\)/);
  assert.match(githubSource, /cloudRegionOptions\(cloudProvider\)/);
  assert.match(githubSource, /definition\.secrets\(\{ cloudProvider \}\)/);
  assert.doesNotMatch(githubSource, /automation === "review"|automation === "template"/);
  assert.match(templateSource, /normalizeRepositoryPath\(values\.projectPath, "agentkit-basic-agent"\)/);
  assert.match(reviewSource, /Sandbox Tool ID/);
  assert.match(reviewSource, /模型 API 地址/);
  assert.match(githubSource, /className="pp-region-trigger"/);
  assert.match(githubSource, /role="listbox" aria-label="地域"/);
  assert.doesNotMatch(githubSource, /<select/);
  assert.match(appSource, /<GitHubIntegration[\s\S]*?cloudProvider=\{cloudProvider\}/);
  assert.match(templateSource, /cloudCredentialSecretLabels\(cloudProvider\)/);
  assert.doesNotMatch(appSource, /applicationsView !== "github" \? <Sidebar/);
  assert.match(
    appSource,
    /<Sidebar[\s\S]*?onApplications=\{\(\) => requestIntelligentNavigation\(openApplicationsPage\)\}/,
  );
  assert.match(githubStyles, /\.github-section-panel \{[\s\S]*?border: 0/);
  assert.match(githubStyles, /\.github-section-panel \{[\s\S]*?background: transparent/);
  assert.match(githubStyles, /\.github-section-panel \{[^}]*width: 100%;/);
  assert.doesNotMatch(githubStyles, /\.github-section-panel \{[^}]*width: min\(100%, 760px\)/);
  assert.match(
    githubStyles,
    /\.github-field > label,[\s\S]*?font-size: 13px;/,
  );
  assert.match(
    githubStyles,
    /\.github-field input \{[\s\S]*?height: 38px;[\s\S]*?font-size: 14px;/,
  );
  assert.match(
    githubStyles,
    /\.github-field-help \{[^}]*font-size: 12px;[^}]*line-height: 1\.5;/,
  );
  assert.match(
    githubStyles,
    /\.github-region-picker \.pp-region-trigger,[\s\S]*?font-size: 14px;/,
  );
  assert.match(githubSource, /提交 PR 中/);
  assert.match(githubSource, /role="alert"/);
  assert.match(githubSource, /event\.nativeEvent\.isComposing/);
  assert.doesNotMatch(githubSource, /localStorage|sessionStorage/);
  assert.match(apiSource, /https:\/\/api\.github\.com/);
  assert.match(apiSource, /Authorization: `Bearer \$\{options\.token\}`/);
  assert.match(apiSource, /export async function createGitHubPullRequest/);
  assert.match(deliverySource, /createGitHubPullRequest/);
  assert.match(templateSource, /createGitHubPullRequest/);
  assert.match(reviewSource, /createGitHubPullRequest/);
  assert.doesNotMatch(apiSource, /\/web\/integrations\/github/);
  assert.doesNotMatch(cliFrontendSource, /frontend_github_integration/);
  assert.equal(
    existsSync(new URL("../../veadk/cli/frontend_github_integration.py", import.meta.url)),
    false,
  );
  assert.equal(
    existsSync(new URL("../../veadk/cli/github_automations", import.meta.url)),
    false,
  );
  assert.match(appSource, /useState<"catalog" \| ApplicationId \| null>/);
  assert.doesNotMatch(apiSource, /console\.(?:log|warn|error)/);
});

test("Feishu detail deploys a new basic Runtime from customer credentials", () => {
  assert.match(appSource, /applicationsView === "feishu"/);
  assert.match(appSource, /<FeishuBotIntegration/);
  assert.match(feishuDetailSource, /deployFeishuBotRuntime/);
  assert.match(feishuDetailSource, /label htmlFor="feishu-app-id"/);
  assert.match(feishuDetailSource, /label htmlFor="feishu-app-secret"/);
  assert.match(feishuDetailSource, /className="feishu-region-trigger"/);
  assert.match(feishuDetailSource, /role="listbox"[\s\S]*?aria-label="部署地域"/);
  assert.match(feishuDetailSource, /创建飞书机器人 Runtime/);
  assert.match(feishuDetailSource, /App Secret 仅用于本次部署/);
  assert.match(feishuDetailSource, /cancelAgentkitDeployment/);
  assert.match(feishuDetailSource, /window\.confirm\("取消部署将停止任务并清理已创建的 Runtime/);
  assert.match(feishuDetailSource, /event\.nativeEvent\.isComposing/);
  assert.match(feishuDetailSource, /event\.key === "ArrowDown"/);
  assert.match(feishuDetailSource, /event\.key === "ArrowUp"/);
  assert.match(feishuDetailSource, /event\.key === "Home"/);
  assert.match(feishuDetailSource, /event\.key === "End"/);
  assert.match(feishuDetailSource, /regionTriggerRef\.current\?\.focus\(\)/);
  assert.doesNotMatch(feishuDetailSource, /getRuntimes|<select|飞书授权页|已有 Runtime/);
  assert.doesNotMatch(feishuDetailSource, /GitHub|repository|Codex|sandboxToolId/);
  assert.doesNotMatch(feishuDetailSource, /localStorage|sessionStorage/);
  assert.match(feishuDeploymentSource, /generateAgentProject\(draft\)/);
  assert.match(feishuDeploymentSource, /deployAgentkitProject/);
  assert.match(feishuDeploymentSource, /feishuEnabled: true/);
  assert.match(feishuDeploymentSource, /FEISHU_APP_ID/);
  assert.match(feishuDeploymentSource, /FEISHU_APP_SECRET/);
  assert.match(feishuDeploymentSource, /minInstance: 1/);
  assert.match(feishuDeploymentSource, /maxInstance: 1/);
  assert.doesNotMatch(feishuDeploymentSource, /envValues/);
  assert.match(feishuStyles, /\.feishu-section-panel \{ width: 100%;/);
  assert.match(feishuStyles, /\.feishu-region-trigger \{[\s\S]*?height: 36px;[\s\S]*?font-size: 12px;/);
  assert.match(feishuStyles, /\.feishu-region-menu \{[\s\S]*?top: calc\(100% \+ 6px\)/);
  assert.match(feishuStyles, /\.feishu-region-option \{[\s\S]*?min-height: 34px/);
  assert.doesNotMatch(feishuStyles, /font-family:\s*(?:monospace|[^;]*Mono)/i);
});

test("Website integration creates an Origin-bound embed token and chat loader", () => {
  assert.match(registrySource, /websiteIntegrationAutomation/);
  assert.match(appSource, /applicationsView === "website-integration"/);
  assert.match(appSource, /<WebsiteIntegration/);
  assert.match(websiteIntegrationSource, /<h1>网站集成<\/h1>/);
  assert.match(websiteIntegrationSource, /添加网站/);
  assert.match(websiteIntegrationSource, /AgentKit Runtime/);
  assert.match(websiteIntegrationSource, /引入方法/);
  assert.match(websiteIntegrationSource, /CopyButton/);
  assert.match(websiteIntegrationSource, /getRuntimes/);
  assert.match(websiteIntegrationSource, /probeRuntimeApps/);
  assert.doesNotMatch(websiteIntegrationSource, /localStorage|sessionStorage|重启/);
  assert.match(websiteIntegrationApiSource, /\/web\/website-integrations/);
  assert.doesNotMatch(websiteIntegrationApiSource, /localStorage|sessionStorage/);
  assert.match(websiteIntegrationLoaderSource, /data-token/);
  assert.match(websiteIntegrationWidgetSource, /\/embed\/session/);
  assert.match(websiteIntegrationWidgetSource, /\/embed\/run_sse/);
  assert.match(websiteIntegrationWidgetSource, /<Blocks/);
  assert.match(websiteIntegrationWidgetSource, /<Markdown/);
  assert.match(websiteIntegrationWidgetSource, /CompactComposer/);
  assert.match(websiteIntegrationWidgetSource, /\/web\/site-logo/);
  assert.match(websiteIntegrationWidgetSource, /window\.addEventListener\("pointermove"/);
  assert.match(websiteIntegrationWidgetSource, /window\.addEventListener\("pointerup"/);
  assert.match(websiteIntegrationWidgetSource, /window\.addEventListener\("pointercancel"/);
  assert.doesNotMatch(websiteIntegrationWidgetSource, /setPointerCapture/);
  assert.match(websiteIntegrationWidgetSource, /suppressClickRef/);
  assert.match(websiteIntegrationEntrySource, /attachShadow/);
  assert.match(websiteIntegrationEntrySource, /builtin-tools\.css\?inline/);
  assert.match(websiteIntegrationEntrySource, /text-shimmer\.css\?inline/);
  assert.match(websiteIntegrationStyles, /\.website-widget\s*\{[\s\S]*?text-align: left;/);
  assert.match(websiteIntegrationStyles, /\.website-widget__launcher\s*\{[\s\S]*?touch-action: none;/);
  assert.match(websiteIntegrationStyles, /\.website-widget__launcher-logo\s*\{[\s\S]*?filter: brightness\(0\) invert\(1\);/);
});
