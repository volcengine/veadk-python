import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const cronJobsSource = readFileSync(
  new URL("../src/cronjobs/CronJobs.tsx", import.meta.url),
  "utf8",
);
const cronJobsStyles = readFileSync(
  new URL("../src/cronjobs/CronJobs.css", import.meta.url),
  "utf8",
);
const resourceStyles = readFileSync(
  new URL("../src/ui/ResourceCollection.css", import.meta.url),
  "utf8",
);
const modelSource = readFileSync(
  new URL("../src/cronjobs/model.ts", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const confirmSource = readFileSync(
  new URL("../src/ui/StudioConfirmDialog.tsx", import.meta.url),
  "utf8",
);

test("places Automation below scheduled tasks with a scheduled-task beta badge", () => {
  assert.match(sidebarSource, /\| "applications"\s*\| "cronjobs"/);
  assert.match(sidebarSource, /onCronJobs: \(\) => void/);
  assert.match(sidebarSource, /import \{ Clock \} from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.doesNotMatch(sidebarSource, /function ScheduledTasksIcon/);
  const automationIndex = sidebarSource.indexOf('aria-label="自动化"');
  const cronJobsIndex = sidebarSource.indexOf('aria-label="定时任务"');
  assert.equal(automationIndex >= 0, true);
  assert.equal(cronJobsIndex < automationIndex, true);
  assert.match(
    sidebarSource,
    /aria-label="定时任务"[\s\S]*?<Badge[\s\S]*?className="sidebar-cronjobs-beta"[\s\S]*?>[\s\S]*?Beta[\s\S]*?<\/Badge>/,
  );
  assert.doesNotMatch(
    sidebarSource,
    /aria-label="自动化"[\s\S]*?sidebar-cronjobs-beta/,
  );
  assert.match(appSource, /onCronJobs=\{\(\) => requestIntelligentNavigation\(openCronJobsPage\)\}/);
  assert.match(appSource, /cronJobsView \? \(\s*<CronJobs cloudProvider=\{cloudProvider\}/);
});

test("renders the shared resource card list, independent-session form, details, and full execution lifecycle states", () => {
  assert.match(cronJobsSource, /<ResourcePageHeader[\s\S]*?title="定时任务"/);
  assert.match(cronJobsSource, /<ResourceTabs[\s\S]*?idPrefix="cronjobs-filter"/);
  assert.match(cronJobsSource, /<ResourceGrid>[\s\S]*?<ResourceCreateCard[\s\S]*?<LibraryResourceCard/);
  assert.match(cronJobsSource, /<LibraryResourceCard[\s\S]*?title=\{job\.name\}/);
  assert.match(cronJobsSource, /metadata=\{\[/);
  assert.match(cronJobsSource, /action=\{\{/);
  assert.match(cronJobsSource, /detailAction=\{\{ label: "查看详情"/);
  assert.match(cronJobsSource, /每次触发都会为 Runtime Agent 创建独立 Session/);
  assert.match(cronJobsSource, /type="datetime-local"/);
  assert.match(cronJobsSource, /type="time"/);
  assert.match(cronJobsSource, /Cron 表达式/);
  assert.match(cronJobsSource, /时区/);
  assert.match(cronJobsSource, /创建后启用/);
  assert.match(modelSource, /pending: "准备中"/);
  assert.match(modelSource, /queued: "已排队"/);
  assert.match(modelSource, /running: "执行中"/);
  assert.match(modelSource, /retrying: "自动重试中"/);
  assert.match(modelSource, /success: "成功"/);
  assert.match(modelSource, /failed: "失败"/);
  assert.match(modelSource, /cancelled: "已取消"/);
  assert.match(modelSource, /skipped: "已跳过"/);
  assert.match(cronJobsSource, /无法加载定时任务/);
  assert.match(cronJobsSource, />\s*创建定时任务\s*<\/ResourceCreateCard>/);
  assert.match(cronJobsSource, /暂无执行记录/);
  assert.match(cronJobsSource, /终止本次执行/);
  assert.match(cronJobsSource, /CRONJOB_ACTIVE_REFRESH_MS/);
  assert.match(cronJobsSource, /window\.setInterval/);
  assert.match(cronJobsSource, /StudioConfirmDialog/);
  assert.match(cronJobsSource, /任务及其执行历史已删除/);
  assert.match(cronJobsSource, /DeploymentErrorMessage/);
  assert.match(cronJobsSource, /retryLabel="重新执行"/);
  assert.match(cronJobsSource, /任务已重新排队，将在一分钟内开始执行/);
  assert.match(cronJobsSource, /catch \(cause\) \{\s*setError\(/);
  assert.match(cronJobsSource, /error=\{confirmError\}/);
  assert.match(confirmSource, /<Alert className="studio-confirm-error" color="danger"/);
  assert.match(cronJobsSource, /drawerRef\.current\?\.querySelectorAll/);
  assert.match(cronJobsSource, /event\.key !== "Tab"/);
  assert.match(cronJobsSource, /const busyRef = useRef\(isBusy\)/);
  assert.match(cronJobsSource, /const onCloseRef = useRef\(onClose\)/);
  assert.match(
    cronJobsSource,
    /job\?\.runtimeId === runtime\.runtimeId[\s\S]*?job\.agentName\.trim\(\)/,
  );
  assert.match(cronJobsSource, /if \(!agentName\) \{[\s\S]*?fetchRemoteApps/);
  assert.match(cronJobsSource, /fetchRemoteApps\("", "", \{/);
  assert.match(cronJobsSource, /agentName = runtimeApp\?\.trim\(\) \?\? ""/);
  assert.match(cronJobsSource, /runtimeName: runtime\.name,[\s\S]*?agentName,/);
  assert.match(cronJobsSource, /正在连接 Runtime/);
  assert.match(cronJobsSource, /Runtime Agent 未返回可调用的 appName/);
});

test("uses Apps SDK controls while keeping only domain layout and responsive styling", () => {
  assert.doesNotMatch(cronJobsStyles, /\.cronjobs-table|\.cronjobs-toolbar|\.cronjobs-row-actions/);
  assert.match(resourceStyles, /\.resource-card\s*\{/);
  assert.match(resourceStyles, /\.resource-grid\s*\{/);
  assert.match(resourceStyles, /\.resource-card__actions\s*\{/);
  assert.match(cronJobsStyles, /\.cronjobs-drawer\s*\{[\s\S]*?width: min\(520px, 100vw\)/);
  assert.match(cronJobsStyles, /@media \(max-width: 900px\)/);
  assert.match(cronJobsStyles, /@media \(max-width: 520px\)/);
  assert.match(cronJobsSource, /label: "下次执行"/);
  assert.match(resourceStyles, /@media \(max-width: 720px\)[\s\S]*?\.resource-grid\s*\{[\s\S]*?grid-template-columns: 1fr/);
  assert.match(cronJobsStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(cronJobsStyles, /#[0-9a-f]{3,8}/i);
  assert.doesNotMatch(cronJobsStyles, /font-family:\s*(?:monospace|[^;]*Mono)/i);
  assert.doesNotMatch(cronJobsSource, /from "lucide-react"|emoji/i);
  for (const component of ["Alert", "Badge", "Button", "EmptyMessage", "Indicator", "Input", "SegmentedControl", "Select", "Switch", "Textarea", "Tooltip"]) {
    assert.match(cronJobsSource, new RegExp(`@openai/apps-sdk-ui/components/${component}`));
  }
  assert.match(cronJobsSource, /@openai\/apps-sdk-ui\/components\/Icon/);
  assert.doesNotMatch(cronJobsStyles, /\.cronjobs-button|\.cronjobs-icon-button/);
  assert.doesNotMatch(cronJobsStyles, /\.cronjobs-field (?:input|select|textarea)/);
});

test("defines typed same-origin cronjob APIs for list, mutation, run history, and cancellation", () => {
  assert.match(clientSource, /export interface CronJobInput/);
  assert.match(clientSource, /export type CronJobRunStatus/);
  assert.match(clientSource, /function cronJobPath/);
  assert.match(clientSource, /export async function listCronJobs/);
  assert.match(clientSource, /export async function createCronJob/);
  assert.match(clientSource, /export async function updateCronJob/);
  assert.match(clientSource, /`\$\{cronJobPath\(jobId\)\}\/update`/);
  assert.match(clientSource, /export async function setCronJobEnabled/);
  assert.match(clientSource, /export async function runCronJobNow/);
  assert.match(clientSource, /export async function listCronJobRuns/);
  assert.match(clientSource, /export async function cancelCronJobRun/);
  assert.match(clientSource, /export async function deleteCronJob/);
  assert.match(clientSource, /`\/web\/cronjobs/);
  assert.doesNotMatch(cronJobsSource, /localStorage|sessionStorage/);
});
