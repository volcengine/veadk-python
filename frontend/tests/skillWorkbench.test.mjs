import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const center = readFileSync(new URL("../src/ui/SkillCenter.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/ui/Sidebar.tsx", import.meta.url), "utf8");
const workbench = readFileSync(
  new URL("../src/ui/skill-workbench/SkillWorkbench.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/ui/skill-workbench/api.ts", import.meta.url),
  "utf8",
);
const styles = readFileSync(
  new URL("../src/ui/skill-workbench/skill-workbench.css", import.meta.url),
  "utf8",
);
const shellStyles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const controller = readFileSync(
  new URL("../src/ui/skill-workbench/useSkillWorkbenchTasks.ts", import.meta.url),
  "utf8",
);
const browser = readFileSync(
  new URL("../src/ui/CodeBrowserDialog.tsx", import.meta.url),
  "utf8",
);
const editor = readFileSync(
  new URL("../src/ui/CodeEditor.tsx", import.meta.url),
  "utf8",
);

test("preserves the existing A/B Skill creator beside the DevEnv conversation flow", () => {
  assert.match(app, /<SkillCreateWorkspace initialJob=\{skillJob\}/);
  assert.match(app, /<SkillWorkbench/);
  assert.match(app, /<SkillCenterView/);
  assert.match(app, /skillWorkbenchOpen/);
});

test("opens Create and Optimize setup from a card-based Skill Space home", () => {
  assert.match(center, /function SkillWorkbenchSetup/);
  assert.match(center, /className="skillcenter-space-grid"/);
  assert.match(center, /className="skillcenter-create-action"/);
  assert.match(center, /className="skillcenter-optimize-action"/);
  assert.match(center, /openSetup\("create"\)/);
  assert.match(center, /beginOptimization/);
  assert.match(center, /onClick=\{beginOptimization\}/);
  assert.match(center, /className="composer composer--new-chat skillcenter-setup-composer"/);
  assert.match(center, /上传 ZIP/);
  assert.match(center, /isImeCompositionEvent/);
  assert.match(center, /event\.nativeEvent/);
  assert.match(center, /event\.target\.value = ""/);
  assert.match(center, /onStartTask/);
  assert.doesNotMatch(center, /function SkillCenterComposer/);
  assert.doesNotMatch(center, /role="radiogroup"/);
});

test("opens optimization sources in the dedicated conversation setup", () => {
  assert.match(center, /setSetupOperation\("optimize"\)/);
  assert.match(center, /setSource\(nextSource\)/);
  assert.match(center, /setSetupOpen\(true\)/);
  assert.match(center, /选择要优化的 Skill/);
  assert.match(center, /if \(selectingSource && nextSource\)[\s\S]*chooseOptimizationSource\(nextSource\)/);
  assert.match(center, /更换 Skill/);
  assert.match(center, /onOptimize=\{chooseOptimizationSource\}/);
  assert.doesNotMatch(workbench, /从技能中心选择/);
});

test("renders a single-column process until a complete artifact is available", () => {
  assert.match(workbench, /SkillConversationStream/);
  assert.match(workbench, /ExecutionStages/);
  assert.match(workbench, /skill-workbench__run-grid is-process-only/);
  assert.match(workbench, /ready \? \(/);
  assert.match(workbench, /<CodeBrowserWorkspace/);
  assert.match(workbench, /artifact\.files/);
  assert.match(workbench, /readOnly/);
  assert.match(api, /\/artifact/);
  assert.match(browser, /export function CodeBrowserWorkspace/);
  assert.match(editor, /readOnly\?: boolean/);
  assert.match(editor, /editable: !readOnly/);
  assert.doesNotMatch(workbench, /<pre><code>\{task\.skillMd\}/);
  assert.doesNotMatch(workbench, /skill-workbench__tabs/);
  assert.doesNotMatch(workbench, /产物将在生成后显示/);
});

test("uses contextual deletion and never offers cancellation after success", () => {
  assert.match(workbench, /skill-workbench__more/);
  assert.match(workbench, /取消并删除会话/);
  assert.match(workbench, /task\.state !== "ready"/);
  assert.match(workbench, /task\.state !== "published"/);
  assert.match(workbench, /StudioConfirmDialog/);
  assert.doesNotMatch(workbench, /skill-workbench__danger/);
  assert.match(sidebar, /onDeleteSkillConversation/);
});

test("merges Skill runs into the normal conversation list with delete controls", () => {
  assert.match(sidebar, /mergeSidebarConversations/);
  assert.match(sidebar, /conversation\.kind === "skill"/);
  assert.match(sidebar, /onOpenSkillConversation/);
  assert.match(sidebar, /onDeleteSkillConversation/);
  assert.match(sidebar, />会话</);
  assert.doesNotMatch(sidebar, /sidebar-skill-tasks/);
  assert.doesNotMatch(sidebar, /Skill 任务/);
  assert.match(app, /deleteSkillConversation/);
});

test("sidebar deletion marks an in-flight provisioning request before cleanup", () => {
  assert.match(
    controller,
    /const deleteTask[\s\S]*referencesRef\.current\.some[\s\S]*cancelProvisioning/,
  );
});

test("streams publish stages and returns a concrete destination", () => {
  assert.match(api, /\/publish-stream/);
  assert.match(api, /application\/x-ndjson/);
  assert.match(api, /getReader\(\)/);
  assert.match(api, /timeout,\s*0|request\([\s\S]*?,\s*0\)/);
  assert.match(workbench, /publishProgress/);
  assert.match(workbench, /<TextShimmer/);
  assert.match(workbench, /在技能中心查看/);
  assert.match(workbench, /onViewPublished/);
  assert.match(workbench, /skillSpaceIds/);
  assert.match(workbench, /task\.publication/);
  assert.match(workbench, /该版本已发布/);
});

test("keeps task polling above the workbench and supports safe reopening", () => {
  assert.match(app, /useSkillWorkbenchTasks/);
  assert.match(controller, /listSkillWorkbenchTasks/);
  assert.match(controller, /visibilitychange/);
  assert.match(controller, /setTimeout\(poll, LIST_POLL_INTERVAL_MS\)/);
  assert.match(controller, /setTimeout\(poll, DETAIL_POLL_INTERVAL_MS\)/);
  assert.match(controller, /activeSelectionRevision/);
  assert.match(controller, /setActiveSelectionRevision\(\(revision\) => revision \+ 1\)/);
  assert.doesNotMatch(workbench, /setTimeout\(poll/);
  assert.match(controller, /reserveSkillWorkbenchTask/);
  assert.match(controller, /state: "provisioning"/);
  assert.match(controller, /PROVISIONING_TTL_SECONDS/);
  assert.match(controller, /cancelRequested/);
  assert.match(controller, /saveProvisioningReferences/);
  assert.doesNotMatch(controller, /localStorage\.setItem\([^\n]*(intent|source|file|activities)/);
  assert.match(controller, /ARTIFACT_RETRY_INTERVAL_MS/);
  assert.match(controller, /refreshActiveArtifact/);
});

test("uses a wider artifact view, a spacious process-only view, and reduced motion", () => {
  assert.match(styles, /grid-template-columns:\s*minmax\(260px,\s*\.58fr\)\s+minmax\(480px,\s*1\.42fr\)/);
  assert.match(styles, /\.skill-workbench__run-grid\.is-process-only\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*860px\)/);
  assert.match(styles, /min-height:\s*0/);
  assert.match(styles, /overflow-y:\s*auto/);
  assert.match(styles, /@media \(max-width: 980px\)/);
  assert.match(styles, /prefers-reduced-motion: reduce/);
  assert.match(shellStyles, /\.skillcenter-regions button\s*\{[^}]*min-width:\s*52px;[^}]*height:\s*32px;/);
  assert.match(shellStyles, /\.skillcenter-space-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(min\(280px,\s*100%\),\s*1fr\)\)/);
  assert.doesNotMatch(shellStyles, /sidebar-skill-task__live/);
});

test("keeps a running Skill conversation at the bottom without stealing manual scroll", () => {
  assert.match(workbench, /activityRef/);
  assert.match(workbench, /followActivityRef/);
  assert.match(workbench, /scrollHeight - scrollTop - clientHeight/);
  assert.match(workbench, /activityRef\.current\.scrollTop = activityRef\.current\.scrollHeight/);
  assert.match(workbench, /onScroll=\{handleActivityScroll\}/);
  assert.match(
    styles,
    /\.skill-workbench \.skill-conversation \.(?:think-head|tool-head):focus-visible/,
  );
  assert.match(styles, /\.skill-workbench \.skill-conversation \.builtin-tool-head:focus-visible/);
});

test("turns a released remote DevEnv into an actionable expired conversation", () => {
  assert.match(controller, /SKILL_TASK_EXPIRED/);
  assert.match(controller, /DevEnv 已到期或被释放/);
  assert.match(controller, /state: "expired"/);
  assert.match(
    controller,
    /current\.filter\(\(task\) =>\s*task\.state !== "provisioning"/,
  );
  assert.match(workbench, /DevEnv 已到期/);
  assert.doesNotMatch(workbench, /DevEnv Session 已过期/);
});

test("warns ready users that DevEnv TTL limits download and publishing", () => {
  assert.match(api, /sessionTtlSeconds/);
  assert.match(workbench, /DevEnv 最长保留/);
  assert.match(workbench, /请及时下载或发布/);
  assert.match(workbench, /超过保留时间后将无法下载或发布/);
  assert.match(workbench, /产物也无法恢复/);
});

test("uses the user intent for Skill conversation titles and no Skill Center badge", () => {
  assert.match(sidebar, /function skillConversationTitle[\s\S]*task\.intent/);
  assert.doesNotMatch(sidebar, /\("name" in task \? task\.name/);
  assert.doesNotMatch(sidebar, /sidebar-skill-count/);
  assert.doesNotMatch(sidebar, /runningSkillConversations/);
});
