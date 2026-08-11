import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const apiUrl = new URL("../src/adk/migrations.ts", import.meta.url);
const workspaceUrl = new URL(
  "../src/migrations/MigrationWorkspace.tsx",
  import.meta.url,
);
const stylesUrl = new URL(
  "../src/migrations/MigrationWorkspace.css",
  import.meta.url,
);
const iconsUrl = new URL(
  "../src/migrations/MigrationIcons.tsx",
  import.meta.url,
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);

test("exposes a typed migration API with bounded transfer requests", () => {
  assert.equal(existsSync(apiUrl), true);
  const source = readFileSync(apiUrl, "utf8");

  assert.match(source, /const API_ROOT = "\/web\/migrations"/);
  assert.match(source, /export type MigrationFramework/);
  assert.match(source, /export interface MigrationTask/);
  assert.match(source, /export async function getMigrationCapabilities/);
  assert.match(source, /export async function listMigrationTasks/);
  assert.match(source, /export async function createMigrationTask/);
  assert.match(source, /export async function uploadMigrationSource/);
  assert.match(source, /export async function confirmMigrationTask/);
  assert.match(source, /export async function stopMigrationTask/);
  assert.match(source, /export async function getMigrationArtifact/);
  assert.match(source, /export async function downloadMigrationArtifact/);
  assert.match(source, /TRANSFER_REQUEST_TIMEOUT_MS/);
  assert.match(source, /withAuth/);
  assert.match(source, /withLocalUser/);
});

test("enables the existing migration entry and renders its workspace", () => {
  assert.match(
    appSource,
    /type CreateMode = QuickCreateKind \| "package" \| "migration"/,
  );
  assert.match(
    appSource,
    /key: "migration"[\s\S]*?title: "从存量迁移"[\s\S]*?onClick: \(\) => \{[\s\S]*?setCreateView\("migration"\)/,
  );
  assert.doesNotMatch(
    appSource,
    /key: "migration"[\s\S]*?status: "敬请期待"[\s\S]*?disabled: true/,
  );
  assert.match(appSource, /visibleCreateView === "migration"/);
  assert.match(appSource, /<MigrationWorkspace/);
});

test("implements the confirmed migration lifecycle as a desktop chat workspace", () => {
  assert.equal(existsSync(workspaceUrl), true);
  assert.equal(existsSync(stylesUrl), true);
  assert.equal(existsSync(iconsUrl), true);
  const source = readFileSync(workspaceUrl, "utf8");
  const styles = readFileSync(stylesUrl, "utf8");

  assert.doesNotMatch(source, /from "lucide-react"/);
  assert.match(source, /from "\.\/MigrationIcons"/);
  assert.match(source, /const MAX_SOURCE_BYTES = 50 \* 1024 \* 1024/);
  assert.match(source, /accept="\.zip,application\/zip"/);
  assert.match(source, /TextShimmer/);
  assert.match(source, /listMigrationTasks/);
  assert.match(source, /getMigrationTask/);
  assert.match(source, /confirmMigrationTask/);
  assert.match(source, /stopMigrationTask/);
  assert.match(source, /downloadMigrationArtifact/);
  assert.match(source, /task\.canUpload/);
  assert.match(source, /task\?\.canConfirm/);
  assert.match(source, /task\?\.canStop/);
  assert.match(source, /MigrationApiError && cause\.retryable/);
  assert.match(source, /async function reconcileTaskState/);
  assert.match(source, /async function reconcileTaskList/);
  assert.match(source, /crypto\.randomUUID\(\)/);
  assert.match(source, /taskId/);
  assert.match(source, /const transferAbortRef = useRef<AbortController \| null>\(null\)/);
  assert.match(source, /if \(transferAbortRef\.current\) return/);
  assert.match(source, /createMigrationTask\(\{[\s\S]*?signal: controller\.signal/);
  assert.match(source, /uploadMigrationSource\([\s\S]*?controller\.signal/);
  assert.match(
    source,
    /className="migration-new-button"[\s\S]*?disabled=\{composerBusy\}/,
  );
  assert.match(
    source,
    /className=\{item\.id === selectedTaskId \? "is-active" : ""\}[\s\S]*?disabled=\{composerBusy\}/,
  );
  assert.match(source, /type="file"[\s\S]*?disabled=\{composerBusy\}/);
  assert.match(
    source,
    /const value = event\.currentTarget\.value;[\s\S]*?\[question\.id\]: value/,
  );
  assert.doesNotMatch(
    source,
    /setAnswers\(\(current\) => \(\{[\s\S]*?\[question\.id\]: event\.currentTarget\.value/,
  );
  assert.match(source, /artifactErrorRetryable/);
  assert.match(source, /重新读取/);
  assert.match(source, /function expireTasksAtDeadline/);
  assert.match(source, /setTasks\(\(current\) => expireTasksAtDeadline/);
  assert.match(source, /path: "migration-result\.json"/);
  assert.doesNotMatch(
    source,
    /artifact\.files\.map\(\(file\) => \(\{[\s\S]*?content: ""/,
  );
  assert.match(source, /Dev Sandbox 已超过 1 小时 TTL/);
  assert.match(source, /迁移执行中不能修改附件或迁移方式/);
  assert.match(source, /role="log"/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /ProjectPreview/);
  assert.match(source, /StudioConfirmDialog/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(styles, /\.migration-workspace\s*\{[\s\S]*?grid-template-columns/);
  assert.match(
    styles,
    /@media \(max-width: 980px\)[\s\S]*?\.migration-artifact-browser\s*\{[\s\S]*?grid-template-rows:/,
  );
  assert.match(styles, /overflow-wrap:\s*anywhere/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});
