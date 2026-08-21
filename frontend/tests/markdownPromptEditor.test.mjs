import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const editorSource = readFileSync(
  new URL("../src/create/MarkdownPromptEditor.tsx", import.meta.url),
  "utf8",
);
const createSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const createStyles = readFileSync(
  new URL("../src/create/CustomCreate.css", import.meta.url),
  "utf8",
);
const createIconSource = readFileSync(
  new URL("../src/ui/icons/CreateAgentIcons.tsx", import.meta.url),
  "utf8",
);
const catalogSource = readFileSync(
  new URL("../src/create/veadkCatalog.ts", import.meta.url),
  "utf8",
);
const localPickerSource = readFileSync(
  new URL("../src/create/LocalPicker.tsx", import.meta.url),
  "utf8",
);
const skillHubPickerSource = readFileSync(
  new URL("../src/create/SkillHubPicker.tsx", import.meta.url),
  "utf8",
);
const skillHubSource = readFileSync(
  new URL("../src/create/skills/skillhub.ts", import.meta.url),
  "utf8",
);
const skillSpacePickerSource = readFileSync(
  new URL("../src/create/SkillSpacePicker.tsx", import.meta.url),
  "utf8",
);
const localSkillSource = readFileSync(
  new URL("../src/create/skills/local.ts", import.meta.url),
  "utf8",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);
const generatedAgentConfigSources = [
  "../src/create/types.ts",
  "../src/create/normalizeDraft.ts",
  "../src/create/TemplateCreate.tsx",
]
  .map((path) => readFileSync(new URL(path, import.meta.url), "utf8"))
  .concat(configYamlSource)
  .join("\n");
const displayTextSource = readFileSync(
  new URL("../src/create/displayText.ts", import.meta.url),
  "utf8",
);
const appStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("system prompt lazily loads a focused Markdown editor", () => {
  assert.match(
    createSource,
    /lazy\(\(\) => import\("\.\/MarkdownPromptEditor"\)\)/,
  );
  assert.match(createSource, /<MarkdownPromptEditor/);
  assert.match(editorSource, /markdownShortcutPlugin\(\)/);
  assert.match(
    editorSource,
    /headingsPlugin\(\{ allowedHeadingLevels: \[1, 2, 3\] \}\)/,
  );
  assert.match(editorSource, /suppressHtmlProcessing/);
  assert.match(editorSource, /trim=\{false\}/);
  assert.match(editorSource, /if \(!initialMarkdownNormalize\)/);
  assert.match(
    createStyles,
    /\.cw-markdown-editor:not\(\.mdxeditor-popup-container\):focus-within\s*\{[\s\S]*?border-color:\s*hsl\(var\(--border\)\);[\s\S]*?0 0 0 1px hsl\(var\(--ring\) \/ 0\.38\) inset,[\s\S]*?0 0 0 3px hsl\(var\(--ring\) \/ 0\.09\),[\s\S]*?inset 0 1px 0 hsl\(var\(--foreground\) \/ 0\.015\);/,
  );
});

test("agent builder waits for real conversation events without placeholder thinking", () => {
  assert.match(
    createSource,
    /id: assistantMessageId,\s*role: "assistant",\s*blocks: \[\],\s*streaming: true/,
  );
  assert.doesNotMatch(createSource, /正在理解你的需求。/);
  assert.match(createSource, /acc = applyEvent\(acc, adkEvent\)/);
});

test("description remains a plain text field", () => {
  assert.match(
    createSource,
    /<Textarea[\s\S]*?id="cw-agent-description"[\s\S]*?value=\{node\.description\}[\s\S]*?patch\(\{ description:/,
  );
});

test("configuration controls omit redundant component descriptions", () => {
  assert.match(displayTextSource, /replace\(\/\[。\.\]\+\$\//);
  assert.doesNotMatch(createSource, /className="cw-check-desc"/);
  assert.doesNotMatch(createSource, /className="cw-seg-desc"/);
  assert.doesNotMatch(createSource, /className="cw-toggle-desc"/);
  assert.doesNotMatch(createSource, /<small>\{t\.desc\}<\/small>/);
});

test("long form content scrolls inside bounded editors", () => {
  assert.match(
    createStyles,
    /\.cw-markdown-editor:not\(\.mdxeditor-popup-container\)/,
  );
  assert.doesNotMatch(createStyles, /(?:^|,)\s*\.cw-markdown-editor\s*\{/m);
  assert.match(
    createStyles,
    /\.cw-markdown-content\s*\{[\s\S]*?max-height:\s*360px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-detail \.cw-markdown-content\s*\{[\s\S]*?padding:\s*6px 12px;/,
  );
});

test("application shell contains scrolling within the viewport", () => {
  assert.match(appStyles, /html, body, #root\s*\{[\s\S]*?overflow:\s*hidden;/);
  assert.match(
    appStyles,
    /#root\s*\{[\s\S]*?position:\s*fixed;[\s\S]*?inset:\s*0;/,
  );
  assert.match(
    appStyles,
    /\.layout\s*\{[\s\S]*?height:\s*100dvh;[\s\S]*?overflow:\s*hidden;/,
  );
  assert.match(
    appStyles,
    /\.sidebar\s*\{[\s\S]*?height:\s*100%;[\s\S]*?min-height:\s*0;/,
  );
});

test("configuration form omits the redundant right-side step rail", () => {
  assert.doesNotMatch(createSource, /className="cw-rail"/);
  assert.doesNotMatch(createStyles, /\.cw-rail\s*\{/);
});

test("build workspace reuses the Figma navigation and hides the old footer", () => {
  assert.match(createSource, /import \{ CreateAgentHeader \}/);
  assert.match(
    createSource,
    /<CreateAgentHeader[\s\S]*?onBack=\{onBack\}[\s\S]*?onDebug=\{onDebug\}[\s\S]*?onDeploy=\{onDeploy\}[\s\S]*?debugMode=\{debugMode\}/,
  );
  assert.doesNotMatch(createSource, /WORKSPACE_TITLES/);
  assert.doesNotMatch(createSource, /WorkspaceLifecycleFooter|cw-publish-primary-action/);
});

test("build workspace uses a continuous dotted canvas and compact configuration drawer", () => {
  const rootRule = createStyles.match(/\.cw-root\s*\{[^}]*\}/)?.[0] ?? "";
  const mainRule = createStyles.match(/\.cw-workspace-main\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(rootRule, /background-color:\s*#f0f0f0/);
  assert.match(rootRule, /background-size:\s*18px 18px/);
  assert.match(mainRule, /width:\s*var\(--cw-workspace-width\)/);
  assert.match(createStyles, /\.cw-detail\s*\{[\s\S]*?width:\s*420px/);
  assert.match(createStyles, /\.cw-detail-tabs\s*\{[\s\S]*?height:\s*28px/);
  assert.match(createStyles, /\.cw-detail \.cw-field\s*\{[\s\S]*?flex-direction:\s*column/);
  assert.doesNotMatch(createStyles, /\.cw-detail \.cw-input\s*\{/);
  assert.doesNotMatch(createStyles, /\.cw-detail \.cw-textarea/);
  assert.doesNotMatch(createStyles, /\.cw-detail \[role="combobox"\]/);
});

test("lets searchable configuration menus escape rounded sections", () => {
  assert.match(
    createStyles,
    /\.cw-section:has\(\.cw-a2a-space-picker:not\(\.cw-model-picker\)\)\s*\{[^}]*overflow:\s*visible;/,
  );
  assert.match(
    createStyles,
    /\.cw-section:has\(\.cw-a2a-space-picker:not\(\.cw-model-picker\)\) > \.cw-sec-head\s*\{[^}]*border-radius:\s*17px 17px 0 0;/,
  );
});

test("build-stage intelligent generation lives in the Figma chat drawer", () => {
  assert.match(createSource, /<AgentBuilderChatPanel/);
  assert.match(
    createSource,
    /onSubmit=\{\(goal\) => void runAgentBuilderConversation\(goal\)\}/,
  );
  assert.match(createSource, /initialGoalGenerationRef/);
  assert.match(createSource, /void runAgentBuilderConversation\(goal\)/);
  assert.match(createSource, /createGeneratedAgentConversation\(/);
  assert.match(createSource, /runGeneratedAgentConversationSSE\(/);
  assert.match(createSource, /eventType === "agent_draft"/);
  assert.match(createSource, /\{workspaceMode === "publish" && \(/);
});

test("debug comparison configuration explains duplicate disabled actions", () => {
  assert.match(
    createSource,
    /const configurationUnavailable =[\s\S]*?duplicateConfiguration/,
  );
  assert.match(
    createSource,
    /duplicateConfiguration[\s\S]*?"该配置与已有测试组相同"/,
  );
  assert.match(
    createSource,
    /\{configurationUnavailable && \([\s\S]*?className="cw-ab-config-error"[\s\S]*?\{disabledReason\}/,
  );
  assert.match(createStyles, /\.cw-ab-config-error\s*\{[\s\S]*?color:\s*hsl\(var\(--destructive\)\)/);
});

test("debug variants configure and run their own model, description, and prompt", () => {
  assert.match(
    createSource,
    /interface DebugVariant \{[\s\S]*?modelName: string;[\s\S]*?description: string;[\s\S]*?instruction: string;/,
  );
  assert.match(
    createSource,
    /<span>描述 <b>\*<\/b>[\s\S]*?value=\{variant\.description\}[\s\S]*?<span>系统提示词 <b>\*<\/b>[\s\S]*?value=\{variant\.instruction\}/,
  );
  assert.match(
    createSource,
    /<Textarea[\s\S]*?className="cw-ab-config-control"[\s\S]*?value=\{variant\.description\}[\s\S]*?<Input[\s\S]*?className="cw-ab-config-control"[\s\S]*?value=\{variant\.modelName\}[\s\S]*?<Textarea[\s\S]*?className="cw-ab-config-control"[\s\S]*?value=\{variant\.instruction\}/,
  );
  assert.match(
    createSource,
    /const renderComposer = \(compact: boolean\)[\s\S]*?<Textarea[\s\S]*?className="cw-debug-input"[\s\S]*?isImeCompositionEvent\(event\.nativeEvent\)[\s\S]*?event\.key === "Enter" && !event\.shiftKey/,
  );
  assert.match(
    createStyles,
    /\.cw-debug-input > textarea\s*\{[\s\S]*?resize:\s*none;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-config \.cw-ab-config-control\s*\{[\s\S]*?padding:\s*0;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(
    createSource,
    /const variantDraft: AgentDraft = \{[\s\S]*?\.\.\.providerDraft[\s\S]*?description: variant\.description,[\s\S]*?instruction: variant\.instruction/,
  );
  assert.match(
    createSource,
    /function debugVariantConfigurationKey[\s\S]*?modelName: variant\.modelName\.trim\(\)[\s\S]*?description: variant\.description\.trim\(\)[\s\S]*?instruction: variant\.instruction\.trim\(\)/,
  );
});

test("debug groups keep independent, aligned config controls", () => {
  assert.doesNotMatch(createSource, /className="cw-ab-settings-toggle"/);
  assert.match(
    createSource,
    /className="cw-ab-group-config-toggle"[\s\S]*?aria-label=\{variant\.configOpen[\s\S]*?variant\.configOpen \? <CreateCloseIcon \/> : <DebugSettingsIcon \/>/,
  );
  assert.match(
    createSource,
    /onClick=\{\(\) =>[\s\S]*?variant\.configOpen[\s\S]*?onCancelConfig\(variant\.id\)[\s\S]*?onOpenSettings\(variant\.id\)/,
  );
  assert.match(
    createSource,
    /onOpenSettings=\{\(id\) =>[\s\S]*?configOpen: variant\.id === id/,
  );
  assert.match(
    createSource,
    /\.\.\.current\.map\(\(variant\) => \(\{ \.\.\.variant, configOpen: false \}\)\)[\s\S]*?configOpen: true/,
  );
  assert.match(
    createSource,
    /onCancelConfig=\{\(id\) =>[\s\S]*?configOpen:[\s\S]*?variant\.id === id \? false : variant\.configOpen/,
  );
  assert.match(
    createSource,
    /className="cw-ab-column-label"[\s\S]*?className="cw-ab-group-chip"[\s\S]*?className="cw-ab-change-summary"[\s\S]*?className="cw-ab-group-config-toggle"/,
  );
  assert.match(
    createSource,
    /className="cw-ab-config-column"[\s\S]*?layoutDependency=\{variants\.length\}/,
  );
  assert.match(
    createSource,
    /className="cw-ab-result-column"[\s\S]*?layoutDependency=\{variants\.length\}/,
  );
  assert.doesNotMatch(
    createSource,
    /className="cw-ab-change-summary">\s*\{variantIndex === 0[\s\S]*?"基准组 A"/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-column-label\s*\{[\s\S]*?grid-template-columns:\s*auto minmax\(0, 1fr\) 28px;[\s\S]*?align-items:\s*center;/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-group-config-toggle\s*\{[\s\S]*?width:\s*28px;[\s\S]*?height:\s*28px;[\s\S]*?place-items:\s*center;/,
  );
  assert.match(
    createIconSource,
    /export function DebugSettingsIcon[\s\S]*?M0\.75 3H9\.75[\s\S]*?stroke="currentColor"/,
  );
});

test("baseline debug config defaults to the first configured Agent model", () => {
  assert.match(
    createSource,
    /function defaultDebugModelName\(draft: AgentDraft\): string \{[\s\S]*?draft\.modelName\?\.trim\(\)[\s\S]*?for \(const child of draft\.subAgents\)[\s\S]*?defaultDebugModelName\(child\)/,
  );
  assert.match(
    createSource,
    /const initialProviderDraft = draftForCloudProvider\([\s\S]*?initialDraft \?\? emptyDraft\(cloudProvider\),[\s\S]*?cloudProvider,[\s\S]*?\);[\s\S]*?id: "baseline",[\s\S]*?modelName: defaultDebugModelName\(initialProviderDraft\)/,
  );
  assert.match(
    createSource,
    /if \(id === "baseline" && field === "modelName"\)[\s\S]*?baselineModelEditedRef\.current = true/,
  );
  assert.match(
    createSource,
    /variant\.id === "baseline"[\s\S]*?modelName: baselineModelEditedRef\.current[\s\S]*?variant\.modelName[\s\S]*?defaultDebugModelName\(providerDraft\)/,
  );
});

test("debug starts with one baseline and preserves comparisons across workspace changes", () => {
  assert.match(
    createSource,
    /const \[debugVariants, setDebugVariants\][\s\S]*?return \[[\s\S]*?id: "baseline"[\s\S]*?\];/,
  );
  assert.match(
    createSource,
    /const openValidation = \(\) => \{[\s\S]*?setDebugVariants\(\(current\) =>[\s\S]*?current\.map\(\(variant\) =>[\s\S]*?variant\.id === "baseline"/,
  );
  assert.doesNotMatch(
    createSource,
    /const openValidation = \(\) => \{[\s\S]*?\.filter\(\(variant\) => variant\.id === "baseline"\)/,
  );
  assert.doesNotMatch(
    createSource,
    /const openValidation = \(\) => \{[\s\S]*?debugVariantSequenceRef\.current = 1/,
  );
  assert.match(
    createSource,
    /const addDebugVariant = \(\) => \{[\s\S]*?if \(current\.length >= 2\) return current;[\s\S]*?name: `对照组 \$\{sequence\}`/,
  );
});

test("debug streaming applies each event outside the React state updater", () => {
  const start = createSource.indexOf("const sendDebugMessage = async () =>");
  const end = createSource.indexOf("const updateDebugVariantConfig", start);
  const sendDebugMessage = createSource.slice(start, end);
  const applyIndex = sendDebugMessage.indexOf("acc = applyEvent(acc, event)");
  const updateIndex = sendDebugMessage.indexOf("setDebugVariants((current) =>", applyIndex);

  assert.ok(applyIndex >= 0);
  assert.ok(updateIndex > applyIndex);
  assert.doesNotMatch(
    sendDebugMessage.slice(updateIndex),
    /acc = applyEvent\(acc, event\)/,
  );
});

test("debug comparison highlights the test configuration entry", () => {
  assert.match(
    createStyles,
    /\.cw-ab-config-trigger\s*\{[\s\S]*?background:\s*transparent;[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\)/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-config-trigger:hover:not\(:disabled\)\s*\{[\s\S]*?background:\s*hsl\(var\(--secondary\) \/ 0\.58\)/,
  );
});

test("debug comparison keeps equal spacing above cards and composer", () => {
  assert.match(
    createStyles,
    /\.cw-ab-stage\s*\{[\s\S]*?padding:\s*8px var\(--cw-workspace-gutter\)/,
  );
});

test("leaving debug mode uses the shared Studio confirm dialog", () => {
  const confirmStart = createSource.indexOf("const confirmLeaveDebug = async () =>");
  const publishStart = createSource.indexOf("const openPublishPreview = async", confirmStart);
  assert.ok(confirmStart >= 0 && publishStart > confirmStart);
  assert.match(createSource, /import \{ StudioConfirmDialog \} from "\.\.\/ui\/StudioConfirmDialog"/);
  assert.match(createSource, /const \[debugLeaveConfirmOpen, setDebugLeaveConfirmOpen\] = useState\(false\)/);
  assert.match(createSource, /debugLeaveConfirmResolverRef/);
  assert.doesNotMatch(
    createSource.slice(confirmStart, publishStart),
    /window\.confirm/,
  );
  assert.match(
    createSource,
    /debugLeaveConfirmOpen && \([\s\S]*?<StudioConfirmDialog[\s\S]*?variant="warning"[\s\S]*?title="离开调试？"/,
  );
  assert.match(createSource, /confirmLabel=\{debugLeaveCleaning \? "清理中\.\.\." : "确定离开"\}/);
  assert.match(createSource, /onConfirm=\{\(\) => void acceptDebugLeaveConfirm\(\)\}/);
});

test("agent type is a form section with radio choices", () => {
  assert.match(createSource, /<Section meta=\{metaOf\("type"\)\}>/);
  assert.match(
    createSource,
    /@openai\/apps-sdk-ui\/components\/RadioGroup/,
  );
  assert.match(
    createSource,
    /<RadioGroup<AgentType>[\s\S]*?aria-label="Agent 类型"/,
  );
  assert.match(createSource, /<RadioGroup\.Item[\s\S]*?className="cw-agent-type-control"/);
  assert.doesNotMatch(createSource, /type="radio"/);
  assert.match(createStyles, /\.cw-agent-type-options\s*\{[\s\S]*?display:\s*grid/);
  assert.match(createStyles, /\.cw-agent-type-option\.is-on\s*\{/);
  assert.match(
    createStyles,
    /\.cw-agent-type-option > \.flex\s*\{[\s\S]*?align-self:\s*stretch;[\s\S]*?flex:\s*1;/,
  );
  assert.doesNotMatch(createSource, /cw-typebar|cw-typeradio/);
});

test("configuration checkboxes use Apps SDK UI controls", () => {
  assert.match(
    createSource,
    /@openai\/apps-sdk-ui\/components\/Checkbox/,
  );
  assert.match(
    createSource,
    /function Checklist[\s\S]*?<Checkbox[\s\S]*?checked=\{on\}[\s\S]*?onCheckedChange=/,
  );
  assert.doesNotMatch(createSource, /type="checkbox"/);
});

test("build workspace validates before entering debugging without an old footer", () => {
  assert.match(
    createSource,
    /const openValidation = \(\) => \{[\s\S]*?if \(!requireCompleteDraft\(\)\) return;[\s\S]*?setWorkspaceMode\("validate"\);/,
  );
  assert.doesNotMatch(createSource, /WorkspaceLifecycleFooter|cw-workspace-nav-button/);
  assert.doesNotMatch(createStyles, /\.cw-workspace-nav-actions|\.cw-workspace-nav-button/);
  assert.doesNotMatch(createSource, /className="cw-build-next/);
});

test("invalid drafts reveal and focus the first failing field", () => {
  assert.match(
    createSource,
    /function focusValidationProblem[\s\S]*?scrollIntoView\([\s\S]*?focus\(\{ preventScroll: true \}\)/,
  );
  assert.match(
    createSource,
    /const requireCompleteDraft = \(\) => \{[\s\S]*?setSelectedPath\(problems\[0\]\.path\)[\s\S]*?focusValidationProblem\(problems\[0\]\)/,
  );
  assert.match(
    createSource,
    /data-validation-field="name"[\s\S]*?aria-invalid=\{showErrors && nameInvalid\}[\s\S]*?aria-describedby=/,
  );
  assert.match(
    createSource,
    /id="cw-agent-name-error"[\s\S]*?role="alert"/,
  );
});

test("container agents require child agents before debug or publish", () => {
  assert.match(
    createSource,
    /if \(isOrchestratorType\(n\.agentType\)\)[\s\S]*?return n\.subAgents\.length === 0 \? "缺少子 Agent" : null;/,
  );
  assert.match(createSource, /typeLabel: agentTypeMeta\(root\.agentType\)\.label/);
  assert.match(
    createSource,
    /function validationProblemMessage\(problem: TreeProblem\): string \{[\s\S]*?problem\.problem === "缺少子 Agent"[\s\S]*?`\$\{problem\.typeLabel\}至少需要添加一个子 Agent 后才能调试或发布。`/,
  );
  assert.match(
    createSource,
    /const sectionId = problem\.problem === "缺少子 Agent" \? "type" : "basic";/,
  );
  assert.match(
    createSource,
    /<Section meta=\{metaOf\("type"\)\}>[\s\S]*?className="cw-agent-type-options"[\s\S]*?\{showErrors\s*&&\s*orchestrator\s*&&\s*node\.subAgents\.length === 0\s*&& \([\s\S]*?<span className="cw-error-text">[\s\S]*?validationProblemMessage\(\{[\s\S]*?typeLabel: agentTypeMeta\(node\.agentType\)\s*\.label,[\s\S]*?problem: "缺少子 Agent"/,
  );
  assert.match(
    createSource,
    /\{buildErr && \([\s\S]*?<DeploymentErrorMessage[\s\S]*?className="cw-workspace-alert"[\s\S]*?message=\{buildErr\}/,
  );
  assert.doesNotMatch(
    createSource,
    /buildErr \|\| validationMessage|const validationMessage/,
  );
  assert.match(
    createSource,
    /const openPublishPreview = async \([\s\S]*?if \(!requireCompleteDraft\(\)\) \{[\s\S]*?setWorkspaceMode\("build"\);[\s\S]*?return;/,
  );
});

test("debug workspace compares multiple configurations behind one shared input", () => {
  assert.doesNotMatch(createSource, /label: "上下文优化"/);
  assert.doesNotMatch(createSource, /label: "幻觉抑制"/);
  assert.doesNotMatch(createSource, /HarnessOptimizationWorkspace/);
  assert.doesNotMatch(createSource, /workspaceMode === "optimize"/);
  assert.doesNotMatch(createSource, /className="cw-optimization-panel"/);
  assert.match(
    createSource,
    /function DebugComparisonWorkspace[\s\S]*?aria-label="A\/B 调试工作台"/,
  );
  assert.match(createSource, /type DebugWorkspaceView = "intro" \| "config" \| "results"/);
  assert.match(
    createSource,
    /function debugWorkspaceView[\s\S]*?variant\.configOpen[\s\S]*?variants\.length > 1 \|\|[\s\S]*?variant\.phase === "error" \|\| variant\.messages\.length > 0[\s\S]*?return "intro"/,
  );
  assert.match(createSource, /className="cw-debug-intro"/);
  assert.match(createSource, /className="cw-ab-config-grid"/);
  assert.match(createSource, /className="cw-ab-results-grid"/);
  assert.match(createSource, /const DEBUG_SUGGESTED_QUESTIONS = \[/);
  assert.match(createSource, /请用一句话介绍你能帮我完成哪些任务/);
  assert.match(createSource, /帮我处理一个典型任务，并说明关键步骤/);
  assert.match(createSource, /如果信息不足，请先向我提问再继续/);
  assert.match(createSource, /const renderComposer = \(compact: boolean\)/);
  assert.doesNotMatch(createSource, /快速调试|同一条输入将同时发送到全部对照组/);
  assert.doesNotMatch(createSource, /<legend>优化选项/);
  assert.doesNotMatch(createSource, /className="cw-ab-optimization-checkbox"/);
  assert.match(createSource, /const startDebugVariant = async \(id: string\)/);
  assert.match(
    createSource,
    /const completeDebugVariantConfig = \(id: string\) => \{[\s\S]*?void startDebugVariant\(id\);/,
  );
  assert.match(
    createSource,
    /workspaceMode !== "validate" \|\| !debugEnabled[\s\S]*?startDebugVariantRef\.current\?\.\("baseline"\)/,
  );
  assert.match(
    createSource,
    /className="cw-ab-remove"[\s\S]*?aria-label=\{`删除\$\{variant\.name\}`\}[\s\S]*?onClick=\{\(\) => onRemoveVariant\(variant\.id\)\}/,
  );
  assert.match(
    createSource,
    /const removeDebugVariant = async \(id: string\) => \{[\s\S]*?if \(id === "baseline"\) return;[\s\S]*?await cleanupDebugVariantRun\(id\);[\s\S]*?current\.filter\(\(variant\) => variant\.id !== id\)[\s\S]*?setSelectedVariantId\("baseline"\)/,
  );
  assert.match(createSource, /targets\.map\(async \(variant\)/);
  assert.match(
    createSource,
    /modelName: variant\.modelName \|\| providerDraft\.modelName/,
  );
  assert.match(createSource, /if \(current\.length >= 2\) return current/);
  assert.doesNotMatch(createSource, /name="debug-release-variant"|发布候选/);
  assert.match(createSource, /<Blocks blocks=\{message\.blocks\} onAction=\{\(\) => \{\}\} \/>/);
  assert.match(createSource, /className="cw-ab-verdict"/);
  assert.match(
    createSource,
    /function debugVariantChangeLabel[\s\S]*?"提示词"[\s\S]*?"模型"[\s\S]*?"描述"[\s\S]*?changes\.length/,
  );
  assert.doesNotMatch(
    createSource,
    /function debugVariantChangeLabel[\s\S]*?"优化选项"[\s\S]*?changes\.length/,
  );
  assert.doesNotMatch(
    createSource,
    /1\.8s|2\.3s|本轮裁判推荐|来源更完整，结论更可信/,
  );
  assert.doesNotMatch(createSource, /下一步：部署发布|>部署发布</);
  assert.doesNotMatch(createSource, />验证中心</);
  assert.doesNotMatch(createSource, /className="cw-debug-deploy"/);
  assert.doesNotMatch(createStyles, /\.cw-debug-next/);
  assert.match(
    createStyles,
    /\.cw-ab-config-grid,[\s\S]*?\.cw-ab-results-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(var\(--cw-ab-column-count\), minmax\(0, 1fr\)\)/,
  );
  assert.match(
    createSource,
    /--cw-ab-column-count": variants\.length/,
  );
  assert.match(
    createStyles,
    /\.cw-root\.is-validate\s*\{[\s\S]*?--cw-workspace-width:\s*100%/,
  );
  assert.match(
    createStyles,
    /\.cw-validation-workspace\s*\{[\s\S]*?--cw-validation-content-width:\s*471px/,
  );
  assert.match(
    createSource,
    /"--cw-validation-content-width": `\$\{Math\.max\([\s\S]*?debugVariants\.length,[\s\S]*?\) \* 471\}px`/,
  );
  assert.match(
    createStyles,
    /\.cw-validation-workspace\.is-intro \.cw-validation-canvas,\s*\.cw-validation-workspace\.is-config \.cw-validation-canvas,\s*\.cw-validation-workspace\.is-results \.cw-validation-canvas\s*\{[\s\S]*?flex:\s*1 1 auto/,
  );
  assert.match(
    createStyles,
    /\.cw-validation-workspace\.is-intro \.cw-validation-content,\s*\.cw-validation-workspace\.is-config \.cw-validation-content,\s*\.cw-validation-workspace\.is-results \.cw-validation-content\s*\{[\s\S]*?width:\s*min\(100%, var\(--cw-validation-content-width\)\);[\s\S]*?flex:\s*0 0 min\(100%, var\(--cw-validation-content-width\)\)/,
  );
  assert.match(
    createStyles,
    /\.cw-validation-canvas-content > \.abc-root\s*\{[\s\S]*?min-width:\s*0;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width: 700px\)[\s\S]*?\.cw-ab-config-grid,\s*\.cw-ab-results-grid\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-result-column\s*\{[\s\S]*?flex:\s*1 0 50%;[\s\S]*?min-height:\s*220px;/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-workspace\.is-intro\s*\{[\s\S]*?grid-template-rows:\s*minmax\(0, 1fr\) auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-composer\s*\{[\s\S]*?min-height:\s*120px;[\s\S]*?border-radius:\s*24px/,
  );
  assert.doesNotMatch(
    createSource,
    /<div className="cw-ab-grid">[\s\S]*?className="cw-ab-add"/,
  );
  assert.doesNotMatch(createStyles, /\.cw-ab-head|\.cw-ab-overlay/);
});

test("narrow workbench keeps the canvas and configuration stacked without page scrolling", () => {
  assert.match(
    appStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.sidebar\s*\{[\s\S]*?width:\s*204px;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.cw-editor\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?overflow-y:\s*hidden;[\s\S]*?\.cw-detail\s*\{[\s\S]*?width:\s*100%;[\s\S]*?height:\s*auto;[\s\S]*?min-height:\s*0;/,
  );
  assert.match(
    createStyles,
    /\.cw-agent-type-options\s*\{[\s\S]*?grid-template-columns:\s*repeat\(auto-fit, minmax\(150px, 1fr\)\)/,
  );
  assert.match(
    createStyles,
    /\.cw-env-fields\s*\{[\s\S]*?grid-template-columns:\s*repeat\(\s*auto-fit,[\s\S]*?minmax\(min\(100%,\s*280px\),\s*1fr\)/,
  );
  assert.match(
    createStyles,
    /\.cw-env-field-label\s*\{[\s\S]*?overflow-wrap:\s*anywhere;/,
  );
});

test("debug workspace motion preserves direction, column continuity, and reduced motion", () => {
  assert.match(
    createSource,
    /function DebugComparisonWorkspace[\s\S]*?const reduceMotion = useReducedMotion\(\)/,
  );
  assert.match(
    createSource,
    /viewOrder\[view\] >= viewOrder\[previousViewRef\.current\] \? 1 : -1/,
  );
  assert.match(
    createSource,
    /<AnimatePresence initial=\{false\} mode="popLayout" custom=\{viewDirection\}>[\s\S]*?key=\{enabled \? view : "disabled"\}[\s\S]*?variants=\{viewMotion\}/,
  );
  assert.match(
    createSource,
    /initial: \(direction: number\)[\s\S]*?x: reduceMotion \? 0 : direction \* 18[\s\S]*?exit: \(direction: number\)[\s\S]*?direction \* -10/,
  );
  assert.match(
    createSource,
    /<AnimatePresence mode="popLayout">[\s\S]*?<motion\.section[\s\S]*?\.\.\.columnMotion\(variantIndex\)/,
  );
  assert.match(
    createSource,
    /className="cw-ab-conversation"[\s\S]*?variantIndex \* DEBUG_COLUMN_STAGGER_SECONDS/,
  );
  assert.match(
    createSource,
    /<motion\.button[\s\S]*?index \* DEBUG_COLUMN_STAGGER_SECONDS[\s\S]*?onOpenTrace\(variant\.id\)/,
  );
  assert.match(
    createSource,
    /layout: reduceMotion \? false : true/,
  );

  const viewEnter = Number(
    createSource.match(/const DEBUG_VIEW_ENTER_SECONDS = ([\d.]+);/)?.[1],
  );
  const viewExit = Number(
    createSource.match(/const DEBUG_VIEW_EXIT_SECONDS = ([\d.]+);/)?.[1],
  );
  const columnEnter = Number(
    createSource.match(/const DEBUG_COLUMN_ENTER_SECONDS = ([\d.]+);/)?.[1],
  );
  const columnExit = Number(
    createSource.match(/const DEBUG_COLUMN_EXIT_SECONDS = ([\d.]+);/)?.[1],
  );
  assert.ok(viewExit < viewEnter, "debug view exit should be faster than enter");
  assert.ok(
    columnExit < columnEnter,
    "debug column exit should be faster than enter",
  );
  assert.match(
    createSource,
    /duration: reduceMotion \? 0 : DEBUG_VIEW_ENTER_SECONDS[\s\S]*?duration: reduceMotion \? 0 : DEBUG_VIEW_EXIT_SECONDS/,
  );
  assert.match(
    createSource,
    /const columnMotion = \(index: number\)[\s\S]*?duration: reduceMotion \? 0 : DEBUG_COLUMN_ENTER_SECONDS[\s\S]*?duration: reduceMotion \? 0 : DEBUG_COLUMN_EXIT_SECONDS/,
  );
  assert.match(
    createSource,
    /const workspaceViewMotion = \{[\s\S]*?duration: reduceMotion \? 0 : WORKSPACE_VIEW_ENTER_SECONDS[\s\S]*?duration: reduceMotion \? 0 : WORKSPACE_VIEW_EXIT_SECONDS/,
  );
  assert.match(
    createSource,
    /className="cw-validation-canvas-content"[\s\S]*?duration: reduceMotion \? 0 : DEBUG_COLUMN_ENTER_SECONDS/,
  );
  assert.match(
    createSource,
    /<AnimatePresence initial=\{false\} mode="popLayout">[\s\S]*?key="build-workspace"[\s\S]*?key="validate-workspace"[\s\S]*?key="publish-workspace"/,
  );
});

test("the configuration drawer scrolls independently beside the canvas", () => {
  assert.match(
    createStyles,
    /\.cw-editor\s*\{[\s\S]*?flex-direction:\s*row;[\s\S]*?overflow:\s*hidden;/,
  );
  assert.match(
    createStyles,
    /\.cw-editor > \.abc-root\s*\{[\s\S]*?flex:\s*1 1 auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-detail-scroll\s*\{[\s\S]*?flex:\s*1;[\s\S]*?min-width:\s*0;[\s\S]*?overflow-x:\s*hidden;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-detail-inner\s*\{[\s\S]*?width:\s*100%;[\s\S]*?min-width:\s*0;/,
  );
  assert.match(
    createStyles,
    /\.cw-lower\s*\{[\s\S]*?width:\s*100%;[\s\S]*?min-width:\s*0;/,
  );
});

test("custom model connection settings stay visible without a disclosure", () => {
  assert.doesNotMatch(createSource, /modelAdvancedOpen/);
  assert.match(
    createSource,
    /modelSource === "ark"[\s\S]*?提供商[\s\S]*?API Base[\s\S]*?API Key/,
  );
  assert.doesNotMatch(createSource, /服务商 Provider/);
});

test("built-in tools adapt columns and scroll after six rows", () => {
  assert.match(createSource, /items=\{createBuiltinTools\}[\s\S]*?scrollRows=\{6\}/);
  assert.match(
    catalogSource,
    /HIDDEN_CREATE_TOOL_IDS = new Set\(\[[\s\S]*?"link_reader"[\s\S]*?"web_scraper"[\s\S]*?"image_edit"[\s\S]*?"text_to_speech"[\s\S]*?"vesearch"/,
  );
  assert.match(
    catalogSource,
    /BYTEPLUS_HIDDEN_CREATE_TOOL_IDS = new Set\(\[[\s\S]*?"web_search"[\s\S]*?"parallel_web_search"/,
  );
  assert.match(
    catalogSource,
    /cloudProvider === "byteplus"[\s\S]*?BYTEPLUS_HIDDEN_CREATE_TOOL_IDS[\s\S]*?return CREATE_BUILTIN_TOOLS\.filter\(\(tool\) => !hidden\.has\(tool\.id\)\)/,
  );
  assert.match(
    createStyles,
    /\.cw-tools-list-shell\s*\{[\s\S]*?container-type:\s*inline-size;/,
  );
  assert.match(
    createStyles,
    /\.cw-checklist-tools\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  );
  assert.match(
    createStyles,
    /--cw-checklist-row-height:\s*40px;[\s\S]*?grid-auto-rows:\s*minmax\(var\(--cw-checklist-row-height\),\s*auto\);/,
  );
  assert.match(createSource, /scrollRows \* 40 \+ \(scrollRows - 1\) \* 8/);
  assert.match(
    createStyles,
    /@container \(max-width:\s*575px\)\s*\{[\s\S]*?\.cw-checklist-tools\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  );
  assert.match(
    createStyles,
    /\.cw-checklist-tools\s*\{[\s\S]*?max-height:\s*var\(--cw-checklist-max-height\);[\s\S]*?overflow-y:\s*auto;/,
  );
});

test("MCP tools stay directly visible and align with their field label", () => {
  assert.doesNotMatch(createSource, /moreToolTypesOpen|更多类型工具/);
  assert.match(
    createSource,
    /className="cw-field cw-mcp-field"[\s\S]*?<label className="cw-label cw-form-section-title">\s*MCP 工具\s*<\/label>[\s\S]*?<McpToolEditor/,
  );
  assert.match(
    createStyles,
    /\.cw-mcp-field\s*\{[\s\S]*?align-items:\s*center/,
  );
});

test("capability sections share one dashed divider and spacing rhythm", () => {
  assert.match(
    createSource,
    /className="cw-field cw-mcp-field"[\s\S]*?<Section meta=\{metaOf\("skills"\)\}>[\s\S]*?<Section meta=\{metaOf\("knowledge"\)\}>/,
  );
  assert.match(
    createSource,
    /className="cw-capability-memory-group"[\s\S]*?title="短期记忆"[\s\S]*?className="cw-capability-memory-group"[\s\S]*?title="长期记忆"/,
  );
  assert.match(
    createSource,
    /className="cw-label cw-form-section-title">\s*内置工具[\s\S]*?className="cw-label cw-form-section-title">\s*MCP 工具[\s\S]*?className="cw-label cw-form-section-title">\s*技能/,
  );
  assert.match(
    createSource,
    /title="知识库"[\s\S]*?sectionTitle[\s\S]*?title="短期记忆"[\s\S]*?sectionTitle[\s\S]*?title="长期记忆"[\s\S]*?sectionTitle/,
  );
  assert.match(
    createStyles,
    /--cw-capability-section-space:\s*24px;[\s\S]*?--cw-capability-section-divider:\s*1px dashed hsl\(var\(--border\) \/ 0\.72\);/,
  );
  assert.match(
    createStyles,
    /\.cw-section-skills,[\s\S]*?\.cw-section-knowledge,[\s\S]*?\.cw-section-memory,[\s\S]*?\.cw-capabilities-form[\s\S]*?> \.cw-field[\s\S]*?\+ \.cw-field,[\s\S]*?\.cw-capability-memory-group[\s\S]*?\+ \.cw-capability-memory-group\s*\{[\s\S]*?margin-top:\s*var\(--cw-capability-section-space\);[\s\S]*?padding-top:\s*var\(--cw-capability-section-space\);[\s\S]*?border-top:\s*var\(--cw-capability-section-divider\) !important;/,
  );
  assert.match(createSource, /<span className="cw-switch-knob" \/>/);
  assert.doesNotMatch(
    createSource,
    /<motion\.span\s+className="cw-switch-knob"/,
  );
  assert.match(
    createStyles,
    /\.cw-switch-knob\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?transform:\s*translateX\(0\);[\s\S]*?transition:\s*transform 0\.18s ease-out;/,
  );
  assert.match(
    createStyles,
    /\.cw-toggle\.is-on \.cw-switch-knob\s*\{[\s\S]*?transform:\s*translateX\(var\(--cw-switch-knob-travel\)\);/,
  );
});

test("leaving debug confirms and cleans every temporary environment", () => {
  assert.match(
    createSource,
    /const confirmLeaveDebug = async \(\) => \{/,
  );
  assert.match(
    createSource,
    /离开调试页面后，当前环境将被清理。您可以通过重新启动环境进行新的测试。/,
  );
  assert.match(
    createSource,
    /await cleanupDebugRuns\(\);/,
  );
  assert.match(
    createSource,
    /current\.map\(\(variant\) => \(\{[\s\S]*?phase: "idle"/,
  );
  assert.match(
    createSource,
    /const debugRunPending = debugVariants\.some[\s\S]*?variant\.phase === "starting" \|\| variant\.phase === "sending"/,
  );
  assert.match(
    createSource,
    /const cleanupDebugRuns = async \(\) => \{[\s\S]*?debugRunGenerationRef\.current \+= 1/,
  );
  assert.match(
    createSource,
    /if \(runGeneration !== debugRunGenerationRef\.current\)[\s\S]*?deleteGeneratedAgentTestRun\(createdRun\.runId\)/,
  );
  assert.match(createSource, /if \(!\(await confirmLeaveDebug\(\)\)\) return;/);
});

test("chat and configuration drawers use mirrored anchored reveals", () => {
  assert.match(createSource, /const reduceMotion = useReducedMotion\(\)/);
  assert.match(
    createSource,
    /<AnimatePresence initial=\{false\} mode="popLayout">[\s\S]*?key="builder-chat"[\s\S]*?key="builder-chat-trigger"/,
  );
  const chatMotion = createSource.match(
    /className="cw-builder-chat-motion"[\s\S]*?<AgentBuilderChatPanel/,
  )?.[0] ?? "";
  assert.doesNotMatch(chatMotion, /\bx:/);
  assert.match(
    createSource,
    /className="cw-builder-chat-motion"[\s\S]*?clipPath: "inset\(0 100% 0 0 round 16px\)"[\s\S]*?animate=\{\{[\s\S]*?opacity: 1,[\s\S]*?clipPath: "inset\(0 0% 0 0 round 16px\)"[\s\S]*?exit=\{\{[\s\S]*?opacity: 0,[\s\S]*?clipPath: reduceMotion[\s\S]*?"inset\(0 100% 0 0 round 16px\)"[\s\S]*?pointerEvents: "none",[\s\S]*?duration: reduceMotion \? 0 : BUILDER_PANEL_SECONDS,[\s\S]*?ease: BUILDER_PANEL_EASE/,
  );
  assert.match(
    createSource,
    /className="cw-open-chat-motion"[\s\S]*?initial=\{reduceMotion \? false : \{ opacity: 0 \}\}[\s\S]*?animate=\{\{ opacity: 1 \}\}[\s\S]*?exit=\{\{ opacity: 0 \}\}[\s\S]*?duration: reduceMotion \? 0 : 0\.16/,
  );
  const triggerMotion = createSource.match(
    /className="cw-open-chat-motion"[\s\S]*?<\/motion\.div>/,
  )?.[0] ?? "";
  assert.doesNotMatch(triggerMotion, /\bx:/);
  assert.match(
    createSource,
    /className="cw-canvas-motion"[\s\S]*?layout=\{reduceMotion \? false : "position"\}/,
  );
});

test("configuration drawer mirrors chat without leaving an interactive layout slot", () => {
  assert.match(
    createSource,
    /<AnimatePresence initial=\{false\} mode="popLayout">[\s\S]*?key="builder-config"[\s\S]*?className=\{`cw-detail is-\$\{configTab\}`\}/,
  );
  assert.match(
    createSource,
    /key="builder-config"[\s\S]*?clipPath: "inset\(0 0 0 100% round 16px\)"[\s\S]*?animate=\{\{[\s\S]*?opacity: 1,[\s\S]*?clipPath: "inset\(0 0 0 0% round 16px\)"[\s\S]*?exit=\{\{[\s\S]*?opacity: 0,[\s\S]*?clipPath: reduceMotion[\s\S]*?"inset\(0 0 0 100% round 16px\)"[\s\S]*?pointerEvents: "none",[\s\S]*?duration: reduceMotion \? 0 : BUILDER_PANEL_SECONDS,[\s\S]*?ease: BUILDER_PANEL_EASE/,
  );
  assert.doesNotMatch(
    createSource,
    /\{builderPanel === "config" && \(\s*<div className=\{`cw-detail/,
  );
  assert.match(
    createStyles,
    /\.cw-editor\s*\{[\s\S]*?--cw-builder-panel-inset:\s*8px;[\s\S]*?padding:\s*var\(--cw-builder-panel-inset\);/,
  );
  assert.match(
    createSource,
    /className="cw-canvas-motion"[\s\S]*?layout=\{reduceMotion \? false : "position"\}/,
  );
});

test("chat and configuration panels share equal visible header and bottom spacing", () => {
  assert.match(
    createStyles,
    /\.cw-editor\s*\{[\s\S]*?--cw-builder-panel-inset:\s*8px;[\s\S]*?--cw-builder-header-action-height:\s*36px;[\s\S]*?--cw-builder-header-edge-space:\s*calc\([\s\S]*?var\(--cw-workbench-toolbar-height\)[\s\S]*?var\(--cw-builder-header-action-height\)[\s\S]*?\/ 2[\s\S]*?\);/,
  );
  assert.match(
    createStyles,
    /\.cw-editor:has\(> \.cw-builder-chat-motion\)\s*\{[\s\S]*?padding:\s*var\(--cw-builder-panel-inset\);/,
  );
  assert.match(
    createStyles,
    /\.cw-open-chat-motion\s*\{[\s\S]*?top:\s*var\(--cw-builder-panel-inset\);/,
  );
  assert.doesNotMatch(createStyles, /margin-top:\s*calc\(-1 \* var\(--cw-builder-header-edge-space\)\)/);
});

test("debug empty state reuses the current site logo", () => {
  assert.doesNotMatch(createSource, /DebugWorkspaceMarkIcon/);
  assert.match(createSource, /<img src=\{siteLogoUrl\} alt="" \/>[\s\S]*?<h2>调试你的 Agent<\/h2>/);
  assert.match(
    createStyles,
    /\.cw-debug-intro-title > span\s*\{[\s\S]*?width:\s*44px;[\s\S]*?height:\s*43px/,
  );
  assert.match(
    createStyles,
    /\.cw-debug-intro-title img\s*\{[\s\S]*?width:\s*44px;[\s\S]*?height:\s*43px/,
  );
});

test("root Agent exposes a confirmed custom clear action", () => {
  assert.match(createSource, /function ClearAgentIcon/);
  assert.match(createSource, /aria-label="清空根 Agent"/);
  assert.match(createSource, /window\.confirm\("清空根 Agent/);
  assert.match(createSource, /setDraft\(emptyDraft\(cloudProvider\)\)/);
});

test("skill sources open in a fixed-height dialog above a six-row selected list", () => {
  assert.doesNotMatch(
    createSource,
    /从 Skill Hub、本地文件或 AgentKit SkillSpace 添加技能/,
  );
  assert.match(createSource, /label: "AgentKit Skills 中心"/);
  assert.doesNotMatch(createSource, /label: "SkillSpace"/);
  assert.match(createSource, /label: "火山 Find Skill 技能广场"/);
  assert.match(skillHubSource, /const SEARCH_BASE = "\/harness\/skills\/findskill"/);
  assert.match(skillHubSource, /const DOWNLOAD_BASE = "\/skillhub\/v1\/skills"/);
  assert.match(createSource, /function AgentKitSkillsIcon/);
  assert.match(
    createSource,
    /id: "skillspace", label: "AgentKit Skills 中心", icon: AgentKitSkillsIcon/,
  );
  assert.match(
    createSource,
    /\{ id: "local", label: "本地文件"[\s\S]*?\{ id: "skillspace", label: "AgentKit Skills 中心"[\s\S]*?\{ id: "skillhub", label: "火山 Find Skill 技能广场"/,
  );
  assert.match(createSource, /useState<SkillSource>\("local"\)/);
  assert.match(
    createSource,
    /className="cw-skill-add"[\s\S]*?<span>添加 Skill<\/span>/,
  );
  assert.match(createSource, /role="dialog"[\s\S]*?aria-modal="true"/);
  assert.match(createSource, /id="cw-skill-dialog-title">添加 Skill<\/h3>/);
  assert.match(
    createSource,
    /className="cw-skill-sourcetabs"[\s\S]*?role="tablist"/,
  );
  assert.match(createSource, /className="cw-skill-tab-slider" aria-hidden/);
  assert.match(createSource, /role="tabpanel"/);
  assert.match(
    createSource,
    /\{selected\.length > 0 && \([\s\S]*?className="cw-selected-skill-list"[\s\S]*?role="dialog"/,
  );
  assert.doesNotMatch(createSource, /function SkillPill/);
  assert.match(
    createStyles,
    /\.cw-skill-results\s*\{[\s\S]*?max-height:\s*472px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-skill-tab-slider\s*\{[\s\S]*?transform:\s*translateX\(var\(--cw-active-skill-tab-offset\)\);/,
  );
  assert.match(
    createStyles,
    /\.cw-skill-dialog\s*\{[\s\S]*?height:\s*min\(640px, calc\(100dvh - 40px\)\);/,
  );
  assert.match(
    createStyles,
    /\.cw-selected-skill-list\s*\{[\s\S]*?max-height:\s*347px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-skill-add\s*\{[\s\S]*?justify-content:\s*center;[\s\S]*?min-height:\s*40px;[\s\S]*?padding:\s*6px 10px;[\s\S]*?border:\s*1px dashed[\s\S]*?border-radius:\s*10px;[\s\S]*?background:\s*transparent;/,
  );
});

test("local Skill folders and ZIP archives support drag and drop", () => {
  assert.doesNotMatch(localPickerSource, /上传文件夹|上传 \.zip/);
  assert.match(localPickerSource, /拖入文件夹或 ZIP，自动识别 Skill/);
  assert.match(localPickerSource, /item\.webkitGetAsEntry\?\.\(\)/);
  assert.match(localPickerSource, /collectDroppedFiles/);
  assert.match(localPickerSource, /onDragEnter=\{onDragEnter\}/);
  assert.match(
    localPickerSource,
    /onDrop=\{\(event\) => void onDrop\(event\)\}/,
  );
  assert.match(localPickerSource, /readZipSkills\(dropped\[0\]\.file\)/);
  assert.match(localPickerSource, /readFolderSkills\(dropped\.map/);
  assert.match(localSkillSource, /function readSkillMdMetadata/);
  assert.match(localSkillSource, /function safeSkillFolder/);
  assert.doesNotMatch(localSkillSource, /function validateName/);
  assert.doesNotMatch(localSkillSource, /function validateDescription/);
  assert.match(
    createStyles,
    /\.cw-local-dropzone\.is-dragging\s*\{[\s\S]*?border-color:/,
  );
});

test("Skill picker states fill the dialog without clipping content", () => {
  assert.match(
    createStyles,
    /\.cw-local\s*\{[\s\S]*?height:\s*100%;[\s\S]*?display:\s*flex;[\s\S]*?flex-direction:\s*column;/,
  );
  assert.match(
    createStyles,
    /\.cw-local-dropzone\s*\{[\s\S]*?flex:\s*1;[\s\S]*?justify-content:\s*center;/,
  );
  assert.match(skillSpacePickerSource, /className="cw-empty-line cw-skill-loading"/);
  assert.match(skillHubPickerSource, /className="cw-empty-line cw-skill-loading"/);
  assert.match(
    createStyles,
    /\.cw-skill-loading\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?justify-content:\s*center;[\s\S]*?white-space:\s*nowrap;/,
  );
  assert.doesNotMatch(skillSpacePickerSource, /\[\$\{s\.region\}\]/);
  assert.match(skillSpacePickerSource, /className="cw-skillspace-region-label"/);
  assert.match(
    createStyles,
    /\.cw-skill-input:focus[\s\S]*?background:\s*hsl\(var\(--background\)\);[\s\S]*?box-shadow:\s*none;/,
  );
  assert.doesNotMatch(
    createStyles,
    /\.cw-skill-result\s*\{[^}]*max-height:\s*72px;/,
  );
  assert.doesNotMatch(
    createStyles,
    /\.cw-skill-result\s*\{[^}]*overflow:\s*hidden;/,
  );
  assert.match(
    createStyles,
    /\.cw-skill-result\s*\{[^}]*flex-shrink:\s*0;/,
  );
});

test("nested Agent forms omit root-only memory configuration", () => {
  assert.match(createSource, /const isRootAgent = safePath\.length === 0;/);
  assert.match(
    createSource,
    /\{isRootAgent && \(\s*<Section meta=\{metaOf\("memory"\)\}>/,
  );
});

test("remote Agent configures only the AgentKit center", () => {
  assert.match(createSource, /llm: "智能体"/);
  assert.match(createSource, /sequential: "分步协作"/);
  assert.match(createSource, /parallel: "同时处理"/);
  assert.match(createSource, /loop: "循环执行"/);
  assert.match(createSource, /a2a: "远程智能体"/);
  assert.match(createSource, /<A2aSpaceSelect/);
  assert.match(createSource, /请选择 AgentKit 智能体中心/);
  assert.doesNotMatch(createSource, /AgentKit 智能体中心 ID 为必填项/);
  assert.match(createSource, /A2A_REGISTRY_RUNTIME_ENV/);
  assert.doesNotMatch(
    createSource,
    /role="option"[\s\S]{0,200}>\s*请选择智能体中心\s*<\/button>/,
  );
  assert.match(
    createSource,
    /aria-expanded=\{a2aRegistryAdvancedOpen\}[\s\S]*?<span>更多选项<\/span>[\s\S]*?\{a2aRegistryAdvancedOpen && \([\s\S]*?<RuntimeEnvFields/,
  );
  assert.match(
    createSource,
    /item\.key !== A2A_REGISTRY_SPACE_ENV_KEY/,
  );
  assert.match(
    createSource,
    /远程 Agent 的名称、描述和能力来自中心返回的\s*Agent Card/,
  );
  assert.match(
    createSource,
    /if \(agentType === "a2a"\)[\s\S]*?a2aRegistry:[\s\S]*?enabled: true/,
  );
  assert.match(
    createSource,
    /if \(isRootAgent && agentType === "a2a"\) return;/,
  );
  assert.match(createSource, /disabled=\{remoteTypeDisabled\}/);
  assert.match(createSource, /远程智能体只能作为子步骤使用/);
  assert.match(
    createSource,
    /className="cw-agent-type-disabled-hint"[\s\S]*?role="tooltip"/,
  );
  assert.match(
    createStyles,
    /\.cw-agent-type-option\.is-disabled:hover \.cw-agent-type-disabled-hint/,
  );
  assert.match(
    createStyles,
    /\.cw-agent-type-disabled-hint\s*\{[\s\S]*?top:\s*calc\(100% \+ 17px\)/,
  );
  assert.match(
    createSource,
    /\{!a2a && \(\s*<>[\s\S]*?<label[\s\S]*?className="cw-label cw-form-section-title"[\s\S]*?htmlFor="cw-agent-name"[\s\S]*?>\s*名称/,
  );
  assert.match(
    createSource,
    /if \(isRoot\) return "远程 Agent 只能作为子 Agent";/,
  );
  assert.doesNotMatch(createSource, /Agent Card 地址|远程 Agent 添加方式/);
  assert.doesNotMatch(createSource, /metaOf\("a2aCenter"\)/);
});

test("memory is a directly visible configuration section", () => {
  assert.match(
    createSource,
    /<Section meta=\{metaOf\("memory"\)\}>[\s\S]*?title="短期记忆"[\s\S]*?title="长期记忆"/,
  );
  assert.match(createSource, /desc="存储单会话上下文"/);
  assert.match(createSource, /desc="存储跨会话上下文，通常使用向量化检索"/);
  assert.match(
    createSource,
    /showDescription && <span className="cw-toggle-help">\{desc\}<\/span>/,
  );
  assert.match(
    createSource,
    /title="短期记忆"[\s\S]*?desc="存储单会话上下文"[\s\S]*?showDescription[\s\S]*?title="长期记忆"[\s\S]*?desc="存储跨会话上下文，通常使用向量化检索"[\s\S]*?showDescription/,
  );
  assert.match(
    createStyles,
    /\.cw-toggle\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\) auto;/,
  );
  assert.doesNotMatch(createSource, /advancedConfigOpen|cw-advanced-disclosure/);
  assert.doesNotMatch(createSource, /<span>观测<\/span>/);
  assert.doesNotMatch(createSource, /观测 \/ Tracing/);
  assert.doesNotMatch(createSource, /Tracing 导出器/);
  assert.doesNotMatch(createSource, /<span>观测与呈现<\/span>/);
  assert.doesNotMatch(
    createStyles,
    /\.cw-advanced-group \+ \.cw-advanced-group\s*\{[^}]*border-top:/,
  );
  assert.match(createSource, /metaOf\("memory"\)/);
  assert.doesNotMatch(createSource, /metaOf\("tracing"\)/);
  assert.doesNotMatch(createSource, /A2UI|enableA2ui/);
  assert.doesNotMatch(generatedAgentConfigSources, /A2UI|enableA2ui/);
});

test("A2A registry YAML export materializes default optional settings", () => {
  assert.match(
    configYamlSource,
    /import \{ A2A_REGISTRY_DEFAULTS \} from "\.\/veadkCatalog";/,
  );
  assert.match(
    configYamlSource,
    /registry\.registryTopK\s*=\s*draft\.a2aRegistry\.registryTopK\?\.trim\(\) \|\| A2A_REGISTRY_DEFAULTS\.topK;/,
  );
  assert.match(
    configYamlSource,
    /registry\.registryRegion\s*=\s*draft\.a2aRegistry\.registryRegion\?\.trim\(\) \|\| A2A_REGISTRY_DEFAULTS\.region;/,
  );
  assert.match(
    configYamlSource,
    /registry\.registryEndpoint\s*=\s*draft\.a2aRegistry\.registryEndpoint\?\.trim\(\) \|\|\s*A2A_REGISTRY_DEFAULTS\.endpoint;/,
  );
  assert.match(
    configYamlSource,
    /if \(draft\.agentType === "a2a"\)[\s\S]*?o\.a2aRegistry = registry;[\s\S]*?return o;/,
  );
});
