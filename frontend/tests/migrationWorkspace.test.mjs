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
const deploymentEnvironmentUrl = new URL(
  "../src/migrations/deploymentEnvironment.ts",
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

  assert.match(source, /const API_ROOT = "\/web\/agent-migrations"/);
  assert.match(source, /export type MigrationFramework/);
  assert.match(source, /export interface MigrationTask/);
  assert.match(source, /export async function getMigrationCapabilities/);
  assert.match(source, /export async function listMigrationTasks/);
  assert.match(source, /export async function createMigrationTask/);
  assert.match(source, /export async function uploadMigrationSource/);
  assert.match(source, /export async function confirmMigrationTask/);
  assert.match(source, /export async function stopMigrationTask/);
  assert.match(source, /export async function getMigrationActivity/);
  assert.match(source, /export async function getMigrationArtifact/);
  assert.match(source, /export async function downloadMigrationArtifact/);
  assert.match(source, /TRANSFER_REQUEST_TIMEOUT_MS/);
  assert.match(source, /withAuth/);
  assert.match(source, /withLocalUser/);
});

test("enables the existing migration entry and renders its workspace", () => {
  assert.match(
    appSource,
    /type CreateView = "custom" \| "package" \| "migration" \| null/,
  );
  assert.match(
    appSource,
    /return v === "package" \|\| v === "migration" \? v : null/,
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
  const deploymentEnvironment = readFileSync(deploymentEnvironmentUrl, "utf8");

  assert.doesNotMatch(source, /from "lucide-react"/);
  assert.match(source, /from "\.\/MigrationIcons"/);
  assert.match(source, /const MAX_SOURCE_BYTES = 50 \* 1024 \* 1024/);
  assert.match(source, /accept="\.zip,application\/zip"/);
  assert.match(source, /\.toLowerCase\(\)/);
  assert.match(
    source,
    /\/\^\[a-z0-9\]\(\?:\[a-z0-9-\]\{0,61\}\[a-z0-9\]\)\?\$\//,
  );
  assert.match(source, /只能包含小写字母、数字和连字符/);
  assert.match(source, /TextShimmer/);
  assert.match(source, /listMigrationTasks/);
  assert.match(source, /getMigrationTask/);
  assert.match(source, /confirmMigrationTask/);
  assert.match(source, /stopMigrationTask/);
  assert.match(source, /getMigrationActivity/);
  assert.match(source, /function MigrationActivityFeed/);
  assert.match(source, /import \{ Blocks \} from "\.\.\/ui\/Blocks"/);
  assert.match(source, /useStickToBottom<HTMLDivElement>/);
  assert.match(source, /kind: "thinking"/);
  assert.match(source, /kind: "text"/);
  assert.match(source, /Codex 执行动态/);
  assert.match(source, /暂时无法读取 Codex 执行动态，不影响当前任务/);
  assert.match(source, /function shouldShowCodexActivity/);
  assert.match(source, /task\.state === "analyzing"/);
  assert.match(source, /Codex 正在开始分析/);
  assert.match(source, /当前 ZIP 暂时无法迁移/);
  assert.match(source, /按提示整理项目后，新建迁移并重新上传/);
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
  assert.match(source, /迁移环境已过期，内容和产物无法继续访问/);
  assert.match(source, /function taskDisplayMessage/);
  assert.match(source, /迁移产物已生成，请查看迁移提示/);
  assert.match(
    source,
    /task\.state === "failed"[\s\S]*?<p>\{task\.message\}<\/p>/,
  );
  assert.match(
    source,
    /产物可预览、下载和部署。运行效果取决于源项目和部署环境变量/,
  );
  assert.match(source, /产物校验未完成/);
  assert.match(source, /迁移执行中不能修改附件或迁移方式/);
  assert.doesNotMatch(source, /const \[instruction, setInstruction\]/);
  assert.doesNotMatch(
    source,
    /const \[additionalInstruction, setAdditionalInstruction\]/,
  );
  assert.doesNotMatch(source, /描述迁移目标、需要保留的行为和验收要求/);
  assert.doesNotMatch(source, /补充迁移要求/);
  assert.match(
    source,
    /createMigrationTask\(\{[\s\S]*?instruction: "",[\s\S]*?signal:/,
  );
  assert.match(
    source,
    /confirmMigrationTask\(\{[\s\S]*?instruction: "",[\s\S]*?analysisAttempt:/,
  );
  assert.doesNotMatch(
    source,
    /filter\(\(key\) => !key\.startsWith\("MODEL_AGENT_"\)\)/,
  );
  assert.match(source, /requiredSecretEnv=\{deploymentSecretEnv\}/);
  assert.match(deploymentEnvironment, /MODEL_AGENT_API_KEY/);
  assert.match(source, /migrationDeploymentEnvDefaults\(artifact, cloudProvider\)/);
  assert.match(
    source,
    /options=\{\(capability\?\.frameworks \?\? \[\]\)\.map/,
  );
  assert.match(source, /any: "Any（通用迁移）"/);
  assert.match(source, /className="migration-confirm-upload-button"/);
  assert.match(source, /\{task \? "继续上传" : "开始迁移"\}/);
  assert.match(source, /function MigrationTransferProgress/);
  assert.match(source, /className="migration-transfer-progress__marker"/);
  assert.match(source, /创建迁移环境/);
  assert.match(source, /上传项目/);
  assert.match(source, /分析项目/);
  assert.match(source, /正在创建 Dev Sandbox/);
  assert.match(
    source,
    /正在初始化迁移工作目录，并检查 AgentKit CLI、Codex 和迁移能力。环境就绪后将自动上传项目。/,
  );
  assert.match(source, /已等待 \{formatElapsedTime\(createElapsedSeconds\)\}/);
  assert.match(
    source,
    /action === "create" && sourceFile[\s\S]*?migration-turn is-user[\s\S]*?sourceFile\.name/,
  );
  assert.match(source, /role="status"/);
  assert.match(
    source,
    /className="migration-main__header-actions"[\s\S]*?task\?\.canStop[\s\S]*?终止迁移/,
  );
  assert.doesNotMatch(source, /className="migration-running-actions"/);
  assert.match(source, /role="log"/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /ProjectPreview/);
  assert.match(source, /StudioConfirmDialog/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(styles, /\.migration-workspace\s*\{[\s\S]*?grid-template-columns/);
  assert.match(
    styles,
    /@media \(max-width: 1120px\)[\s\S]*?\.migration-artifact-browser\s*\{[\s\S]*?grid-template-rows:/,
  );
  assert.match(styles, /overflow-wrap:\s*anywhere/);
  assert.match(styles, /--migration-content-width:\s*1180px/);
  assert.match(
    styles,
    /\.migration-turn,[\s\S]*?\.migration-result,[\s\S]*?\{[\s\S]*?max-width:\s*var\(--migration-content-width\)/,
  );
  assert.match(
    styles,
    /\.migration-composer\s*\{[\s\S]*?var\(--migration-content-width\)/,
  );
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(styles, /\.migration-transfer-progress__marker/);
  assert.match(styles, /\.migration-activity/);
  assert.match(styles, /\.migration-activity__marker/);
  assert.doesNotMatch(styles, /\.migration-transfer-progress > div > span/);
});
