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
const activityBlocksUrl = new URL(
  "../src/migrations/migrationActivityBlocks.ts",
  import.meta.url,
);
const deploymentEnvironmentUrl = new URL(
  "../src/migrations/deploymentEnvironment.ts",
  import.meta.url,
);
const migratedProjectsUrl = new URL(
  "../src/migrations/MigratedProjectsPage.tsx",
  import.meta.url,
);
const iconsUrl = new URL(
  "../src/migrations/MigrationIcons.tsx",
  import.meta.url,
);
const zhResourceUrl = new URL(
  "../src/i18n/resources/zh-CN/migrations.json",
  import.meta.url,
);
const enResourceUrl = new URL(
  "../src/i18n/resources/en-US/migrations.json",
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
  assert.match(source, /unsupportedModelIds\?: string\[\]/);
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
    /key: "migration"[\s\S]*?title: t\("addAgent\.migrate\.title"\)[\s\S]*?onClick: \(\) => \{[\s\S]*?setCreateView\("migration"\)/,
  );
  assert.doesNotMatch(appSource, /key: "migration"[\s\S]*?disabled: true/);
  assert.match(appSource, /visibleCreateView === "migration"/);
  assert.match(appSource, /<MigrationWorkspace/);
});

test("keeps new migration and migrated projects as parallel workspace pages", () => {
  const source = readFileSync(workspaceUrl, "utf8");
  const projects = readFileSync(migratedProjectsUrl, "utf8");

  assert.match(source, /initialPage = "new"/);
  assert.match(source, /useState<"new" \| "projects">\(initialPage\)/);
  assert.match(source, /useState\(initialProjectId\)/);
  assert.match(source, /t\("workspace\.newMigration"\)/);
  assert.match(source, /t\("projects\.title"\)/);
  assert.match(source, /t\("workspace\.recent"\)/);
  assert.match(
    source,
    /aria-current=\{page === "projects" \? "page" : undefined\}/,
  );
  assert.match(source, /page === "projects" \? \(/);
  assert.match(source, /<MigratedProjectsPage/);
  assert.match(source, /task\.persistence\?\.state === "saved"/);
  assert.match(source, /t\("artifact\.viewProjects"\)/);
  assert.match(projects, /origin="migration"/);
  assert.match(projects, /title=\{t\("projects\.libraryTitle"\)\}/);
  assert.match(projects, /onSelectBaseVersion=\{setOptimizationBase\}/);
  assert.match(projects, /<IntelligentOptimizationDialog/);
  assert.match(projects, /onCreate=\{onOptimize\}/);
  assert.match(projects, /onDownload=\{onDownload\}/);
  assert.match(projects, /onDeploy=\{onDeploy\}/);
  assert.match(
    appSource,
    /initialPage=\{migrationProjectReturn \? "projects" : "new"\}/,
  );
  assert.match(
    appSource,
    /onOptimizeVersion=\{\(goal, modelId, base\) =>[\s\S]*?startIntelligentDevelopment\([\s\S]*?goal,[\s\S]*?modelId,[\s\S]*?base,[\s\S]*?\{ projectId: base\.projectId \}/,
  );
  const migrationWorkspaceBlock =
    appSource.match(
      /visibleCreateView === "migration" \? \(([\s\S]*?)\) : turns\.length === 0/,
    )?.[1] ?? "";
  assert.doesNotMatch(
    migrationWorkspaceBlock,
    /setCreateView\("intelligent"\)/,
  );
  assert.match(
    appSource,
    /function returnToIntelligentCreate\(\)[\s\S]*?migrationProjectReturn[\s\S]*?setCreateView\("migration"\)/,
  );
});

test("implements the confirmed migration lifecycle as a desktop chat workspace", () => {
  assert.equal(existsSync(workspaceUrl), true);
  assert.equal(existsSync(stylesUrl), true);
  assert.equal(existsSync(iconsUrl), true);
  const source = readFileSync(workspaceUrl, "utf8");
  const styles = readFileSync(stylesUrl, "utf8");
  const activityBlocks = readFileSync(activityBlocksUrl, "utf8");
  const deploymentEnvironment = readFileSync(deploymentEnvironmentUrl, "utf8");
  const zhResource = readFileSync(zhResourceUrl, "utf8");
  const enResource = readFileSync(enResourceUrl, "utf8");

  assert.doesNotMatch(source, /from "lucide-react"/);
  assert.match(source, /from "\.\/MigrationIcons"/);
  assert.match(source, /const MAX_SOURCE_BYTES = 20 \* 1024 \* 1024/);
  assert.match(source, /capability\?\.maxUploadBytes \?\? MAX_SOURCE_BYTES/);
  assert.match(source, /accept="\.zip,application\/zip"/);
  assert.match(source, /\.toLowerCase\(\)/);
  assert.match(
    source,
    /\/\^\[a-z0-9\]\(\?:\[a-z0-9-\]\{0,61\}\[a-z0-9\]\)\?\$\//,
  );
  assert.match(source, /migrationText\("validation\.agentNameInvalid"\)/);
  assert.match(source, /TextShimmer/);
  assert.match(source, /listMigrationTasks/);
  assert.match(source, /getMigrationTask/);
  assert.match(source, /confirmMigrationTask/);
  assert.match(source, /stopMigrationTask/);
  assert.match(source, /getMigrationActivity/);
  assert.match(source, /function MigrationActivityFeed/);
  assert.match(source, /import \{ Blocks \} from "\.\.\/ui\/Blocks"/);
  assert.match(source, /useStickToBottom<HTMLDivElement>/);
  assert.match(activityBlocks, /kind: "thinking"/);
  assert.match(activityBlocks, /kind: "text"/);
  assert.match(source, /t\("activity\.title"\)/);
  assert.match(source, /t\("activity\.loadError"\)/);
  assert.match(source, /function shouldShowCodexActivity/);
  assert.match(source, /task\.state === "analyzing"/);
  assert.match(source, /t\("activity\.startingAnalysis"\)/);
  assert.match(source, /t\("conversation\.unsupportedTitle"\)/);
  assert.match(source, /t\("conversation\.unsupportedHint"\)/);
  assert.match(source, /downloadMigrationArtifact/);
  assert.match(source, /task\.canUpload/);
  assert.match(source, /task\?\.canConfirm/);
  assert.match(source, /task\?\.canStop/);
  assert.match(source, /MigrationApiError && cause\.retryable/);
  assert.match(source, /async function reconcileTaskState/);
  assert.match(source, /async function reconcileTaskList/);
  assert.match(source, /crypto\.randomUUID\(\)/);
  assert.match(source, /taskId/);
  assert.match(
    source,
    /const transferAbortRef = useRef<AbortController \| null>\(null\)/,
  );
  assert.match(source, /if \(transferAbortRef\.current\) return/);
  assert.match(
    source,
    /createMigrationTask\(\{[\s\S]*?signal: controller\.signal/,
  );
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
  assert.match(source, /t\("actions\.reload"\)/);
  assert.match(source, /function expireTasksAtDeadline/);
  assert.match(source, /setTasks\(\(current\) => expireTasksAtDeadline/);
  assert.match(source, /function migrationExpiryCopy/);
  assert.match(source, /migrationText\("expiry\.countdown"/);
  assert.match(source, /migrationText\("expiry\.savedUnaffected"\)/);
  assert.match(source, /migrationText\("expiry\.savingUnaffected"\)/);
  assert.match(source, /migrationText\("expiry\.savedAvailable"\)/);
  assert.doesNotMatch(source, /剩余 \$\{minutes\}:/);
  assert.match(
    source,
    /className="migration-ttl" aria-live="off"[\s\S]*?<strong>[\s\S]*?<small>/,
  );
  assert.match(styles, /\.migration-ttl strong/);
  assert.match(styles, /\.migration-ttl small/);
  assert.match(source, /path: "migration-result\.json"/);
  assert.doesNotMatch(
    source,
    /artifact\.files\.map\(\(file\) => \(\{[\s\S]*?content: ""/,
  );
  assert.match(source, /migrationText\("expiry\.expiredSavedMessage"\)/);
  assert.match(source, /function taskDisplayMessage/);
  assert.match(source, /migrationText\("task\.readyWithWarnings"\)/);
  assert.match(
    source,
    /task\.state === "failed"[\s\S]*?<p>\{task\.message\}<\/p>/,
  );
  assert.match(source, /t\("artifact\.saved"\)/);
  assert.match(source, /t\("upload\.retention"\)/);
  assert.match(source, /migrationText\("verification\.degraded"\)/);
  assert.match(source, /t\("conversation\.migrationLocked"\)/);
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
  assert.match(deploymentEnvironment, /isMigrationRuntimeEnvironmentKey/);
  assert.match(
    source,
    /migrationDeploymentEnvDefaults\(artifact, cloudProvider\)/,
  );
  assert.match(
    source,
    /artifact\.environment\.required[\s\S]*?\.filter\(isMigrationRuntimeEnvironmentKey\)/,
  );
  assert.match(
    source,
    /artifact\.environment\.optional[\s\S]*?\.filter\(isMigrationRuntimeEnvironmentKey\)/,
  );
  assert.match(source, /options=\{\(capability\?\.frameworks \?\? \[\]\)\.map/);
  assert.match(source, /any: "framework\.any"/);
  assert.match(source, /className="migration-confirm-upload-button"/);
  assert.match(
    source,
    /task \? t\("upload\.continue"\) : t\("upload\.start"\)/,
  );
  assert.match(source, /listModelOptions\(\{/);
  assert.match(
    source,
    /<NewChatCompactSelect[\s\S]*?label=\{t\("model\.label"\)\}[\s\S]*?searchable[\s\S]*?disabled=\{composerBusy \|\| Boolean\(task\)\}/,
  );
  assert.match(
    source,
    /createMigrationTask\(\{[\s\S]*?modelId: selectedModelId \|\| undefined/,
  );
  assert.match(
    source,
    /model\.available \|\| model\.lifecycleStatus === "Retiring"/,
  );
  assert.match(source, /!unsupportedModelIds\.has\(model\.id\)/);
  assert.doesNotMatch(source, /listModelApiKeys|revealModelApiKey/);
  assert.match(styles, /\.migration-composer__model-select/);
  assert.match(source, /function MigrationTransferProgress/);
  assert.match(source, /className="migration-transfer-progress__marker"/);
  assert.match(source, /t\("transfer\.session"\)/);
  assert.match(source, /t\("transfer\.upload"\)/);
  assert.match(source, /t\("transfer\.analysis"\)/);
  assert.match(source, /t\("conversation\.creatingSandbox"\)/);
  assert.match(source, /t\("conversation\.initializing"\)/);
  assert.match(
    source,
    /t\(\s*"conversation\.elapsed",\s*\{\s*duration: formatElapsedTime\(createElapsedSeconds\),?\s*\},?\s*\)/,
  );
  assert.match(
    source,
    /action === "create" && sourceFile[\s\S]*?migration-turn is-user[\s\S]*?sourceFile\.name/,
  );
  assert.match(source, /role="status"/);
  assert.match(
    source,
    /className="migration-main__header-actions"[\s\S]*?task\?\.canStop[\s\S]*?t\("actions\.stop"\)/,
  );
  assert.doesNotMatch(source, /className="migration-running-actions"/);
  assert.match(source, /role="log"/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /ProjectPreview/);
  assert.match(source, /StudioConfirmDialog/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(
    styles,
    /\.migration-workspace\s*\{[\s\S]*?grid-template-columns/,
  );
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
  assert.doesNotMatch(source, /[\p{Script=Han}]/u);
  assert.match(zhResource, /"workspace"/);
  assert.match(zhResource, /"从存量迁移"/);
  assert.match(enResource, /"Migrate existing project"/);
});

test("renders Codex migration events through one shared block stream", () => {
  const source = readFileSync(workspaceUrl, "utf8");
  const styles = readFileSync(stylesUrl, "utf8");
  const activityBlocks = readFileSync(activityBlocksUrl, "utf8");

  assert.match(source, /import \{ migrationActivityBlocks \}/);
  assert.match(activityBlocks, /function migrationActivityBlocks/);
  assert.match(activityBlocks, /kind: "plan"/);
  assert.match(activityBlocks, /kind: "tool"/);
  assert.match(source, /<Blocks[\s\S]*?blocks=\{blocks\}/);
  assert.doesNotMatch(source, /migration-activity__status/);
  assert.doesNotMatch(styles, /\.migration-activity__status/);
});

test("preserves Codex activity while the same migration advances", () => {
  const source = readFileSync(workspaceUrl, "utf8");

  assert.match(
    source,
    /useEffect\(\(\) => \{\s*setActivity\(null\);\s*setActivityError\(""\);\s*setActivityLoading\(false\);\s*\}, \[task\?\.id\]\);/,
  );

  const pollingEffect = source.slice(
    source.indexOf("if (!task || !shouldShowCodexActivity(task))"),
    source.indexOf("const analysisKey ="),
  );
  assert.doesNotMatch(pollingEffect, /setActivity\(null\)/);
});
