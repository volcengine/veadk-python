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
const resourceSource = readFileSync(
  new URL("../src/ui/ResourceCollection.tsx", import.meta.url),
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

test("places Automation below scheduled tasks without a scheduled-task beta badge", () => {
  assert.match(sidebarSource, /\| "applications"\s*\| "cronjobs"/);
  assert.match(sidebarSource, /onCronJobs: \(\) => void/);
  assert.match(sidebarSource, /import \{ Clock \} from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.doesNotMatch(sidebarSource, /function ScheduledTasksIcon/);
  const automationIndex = sidebarSource.indexOf('aria-label={t("navigation.automations")}');
  const cronJobsIndex = sidebarSource.indexOf('aria-label={t("navigation.cronjobs")}');
  assert.equal(automationIndex >= 0, true);
  assert.equal(cronJobsIndex < automationIndex, true);
  assert.doesNotMatch(sidebarSource, /sidebar-cronjobs-beta|>\s*Beta\s*</);
  assert.match(appSource, /onCronJobs=\{\(\) => requestIntelligentNavigation\(openCronJobsPage\)\}/);
  assert.match(appSource, /cronJobsView \? \(\s*<CronJobs cloudProvider=\{cloudProvider\}/);
});

test("renders the shared resource card list, independent-session form, details, and full execution lifecycle states", () => {
  assert.match(cronJobsSource, /<ResourcePageHeader[\s\S]*?title=\{cronText\("page\.title"\)\}/);
  assert.match(cronJobsSource, /<ResourceTabs[\s\S]*?idPrefix="cronjobs-filter"/);
  assert.match(cronJobsSource, /<ResourceGrid>[\s\S]*?<ResourceCreateCard[\s\S]*?<LibraryResourceCard/);
  assert.match(cronJobsSource, /<LibraryResourceCard[\s\S]*?title=\{job\.name\}/);
  assert.match(cronJobsSource, /metadata=\{\[/);
  const cardSource = cronJobsSource.slice(
    cronJobsSource.indexOf("<LibraryResourceCard"),
    cronJobsSource.indexOf("/>", cronJobsSource.indexOf("<LibraryResourceCard")),
  );
  assert.match(cardSource, /label: cronText\("fields\.schedule"\)/);
  assert.doesNotMatch(cardSource, /label: "Runtime"|label: "下次执行"|action=\{\{/);
  assert.match(cronJobsSource, /detailAction=\{\{ label: cronText\("actions\.viewDetails"\)/);
  assert.match(cronJobsSource, /cronText\("drawer\.description"\)/);
  assert.match(cronJobsSource, /type="datetime-local"/);
  assert.match(cronJobsSource, /type="time"/);
  assert.match(cronJobsSource, /cronText\("fields\.cronExpression"\)/);
  assert.match(cronJobsSource, /cronText\("fields\.timezone"\)/);
  assert.match(cronJobsSource, /cronText\("fields\.enableAfterCreate"\)/);
  for (const status of ["pending", "queued", "running", "retrying", "success", "failed", "cancelled", "skipped"]) {
    assert.match(modelSource, new RegExp(`${status}: "status\\.${status}"`));
  }
  assert.match(cronJobsSource, /cronText\("page\.loadFailed"\)/);
  assert.match(cronJobsSource, /cronText\("actions\.createScheduledTask"\)/);
  assert.match(cronJobsSource, /cronText\("history\.emptyTitle"\)/);
  assert.match(cronJobsSource, /"actions\.stopRun"/);
  assert.match(cronJobsSource, /CRONJOB_ACTIVE_REFRESH_MS/);
  assert.match(cronJobsSource, /window\.setInterval/);
  assert.match(cronJobsSource, /StudioConfirmDialog/);
  assert.match(cronJobsSource, /cronText\("notices\.deleted"\)/);
  assert.match(cronJobsSource, /DeploymentErrorMessage/);
  assert.match(cronJobsSource, /retryLabel=\{cronText\("actions\.rerun"\)\}/);
  assert.match(cronJobsSource, /cronText\("notices\.requeued"\)/);
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
  assert.match(cronJobsSource, /"actions\.connectingRuntime"/);
  assert.match(cronJobsSource, /cronText\("validation\.runtimeAppMissing"\)/);
});

test("uses Apps SDK controls while keeping only domain layout and responsive styling", () => {
  assert.doesNotMatch(cronJobsStyles, /\.cronjobs-table|\.cronjobs-toolbar|\.cronjobs-row-actions/);
  assert.match(resourceStyles, /\.resource-card\s*\{/);
  assert.match(resourceStyles, /\.resource-grid\s*\{/);
  assert.match(resourceStyles, /\.resource-card__actions\s*\{/);
  assert.match(cronJobsStyles, /\.cronjobs-drawer\s*\{[\s\S]*?width: min\(520px, 100vw\)/);
  assert.match(cronJobsStyles, /@media \(max-width: 900px\)/);
  assert.match(cronJobsStyles, /@media \(max-width: 520px\)/);
  assert.doesNotMatch(cronJobsSource.slice(
    cronJobsSource.indexOf("<LibraryResourceCard"),
    cronJobsSource.indexOf("/>", cronJobsSource.indexOf("<LibraryResourceCard")),
  ), /label: "下次执行"/);
  assert.match(resourceStyles, /@media \(max-width: 720px\)[\s\S]*?\.resource-grid\s*\{[\s\S]*?grid-template-columns: 1fr/);
  assert.match(cronJobsStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(cronJobsStyles, /#[0-9a-f]{3,8}/i);
  assert.doesNotMatch(cronJobsStyles, /font-family:\s*(?:monospace|[^;]*Mono)/i);
  assert.doesNotMatch(cronJobsSource, /from "lucide-react"|emoji/i);
  for (const component of ["Alert", "Badge", "Button", "EmptyMessage", "Input", "SegmentedControl", "Select", "Switch", "Textarea", "Tooltip"]) {
    assert.match(cronJobsSource, new RegExp(`@openai/apps-sdk-ui/components/${component}`));
  }
  assert.match(cronJobsSource, /<ResourceLoadingState \/>/);
  assert.match(resourceSource, /@openai\/apps-sdk-ui\/components\/Indicator/);
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
