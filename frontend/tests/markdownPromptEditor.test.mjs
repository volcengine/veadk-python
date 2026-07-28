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
const localPickerSource = readFileSync(
  new URL("../src/create/LocalPicker.tsx", import.meta.url),
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
});

test("description remains a plain text field", () => {
  assert.match(
    createSource,
    /<textarea[\s\S]*?value=\{node\.description\}[\s\S]*?patch\(\{ description:/,
  );
});

test("compact component descriptions omit terminal periods", () => {
  assert.match(displayTextSource, /replace\(\/\[。\.\]\+\$\//);
  assert.match(createSource, /displayDescription\(it\.desc\)/);
  assert.match(createSource, /displayDescription\(desc\)/);
});

test("long form content scrolls inside bounded editors", () => {
  assert.match(
    createStyles,
    /\.cw-markdown-editor:not\(\.mdxeditor-popup-container\)/,
  );
  assert.doesNotMatch(createStyles, /(?:^|,)\s*\.cw-markdown-editor\s*\{/m);
  assert.match(
    createStyles,
    /\.cw-textarea-sm\s*\{[\s\S]*?max-height:\s*160px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-markdown-content\s*\{[\s\S]*?max-height:\s*360px;[\s\S]*?overflow-y:\s*auto;/,
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

test("form step rail aligns to the right edge of the detail area", () => {
  assert.match(
    createStyles,
    /\.cw-rail\s*\{[\s\S]*?width:\s*32px;[\s\S]*?margin-left:\s*auto;/,
  );
});

test("workspace title follows the original named agent inside an anonymous root sequence", () => {
  assert.match(
    createSource,
    /function workspaceAgentName\(draft: AgentDraft\): string \{[\s\S]*?if \(rootName\) return rootName;[\s\S]*?draft\.agentType !== "sequential"[\s\S]*?draft\.subAgents\.find\(\(agent\) => agent\.name\.trim\(\)\)/,
  );
  assert.match(createSource, /agentName=\{workspaceAgentName\(draft\)\}/);
});

test("workspace lifecycle header is one rounded glass bar with text-only step sliders", () => {
  const headerRule = createStyles.match(/\.cw-workspace-header\s*\{[^}]*\}/)?.[0] ?? "";
  const stepperRule = createStyles.match(/\.cw-workspace-stepper\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(headerRule, /min-height:\s*56px/);
  assert.match(headerRule, /border-radius:\s*16px/);
  assert.match(headerRule, /background:\s*rgba\(246, 246, 248, 0\.82\)/);
  assert.match(headerRule, /backdrop-filter:\s*blur\(7px\)/);
  assert.match(headerRule, /border:\s*0/);
  assert.match(headerRule, /box-shadow:\s*none/);
  assert.match(stepperRule, /display:\s*flex/);
  assert.match(stepperRule, /gap:\s*12px/);
  assert.doesNotMatch(stepperRule, /background:/);
  assert.match(
    createStyles,
    /\.cw-workspace-stepper button\s*\{[\s\S]*?min-width:\s*124px;[\s\S]*?border-radius:\s*10px;[\s\S]*?background:\s*rgba\(237, 237, 241, 0\.78\)/,
  );
  assert.match(createStyles, /\.cw-workspace-stepper button\.is-active\s*\{[\s\S]*?background:\s*rgba\(218, 218, 224, 0\.86\);[\s\S]*?box-shadow:\s*none/);
  assert.match(createStyles, /\.cw-workspace-stepper button > strong\s*\{[\s\S]*?font-size:\s*14px/);
  assert.doesNotMatch(createSource, /cw-workspace-step-marker/);
});

test("debug comparison configuration explains duplicate disabled actions", () => {
  assert.match(
    createSource,
    /className=\{`cw-ab-config-done-wrap\$\{disabledReason \? " is-disabled" : ""\}`\}[\s\S]*?className="cw-ab-config-done"[\s\S]*?disabled=\{[\s\S]*?configurationUnavailable[\s\S]*?className="cw-ab-config-done-tip" role="tooltip"/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-config-done:disabled\s*\{[\s\S]*?background:[\s\S]*?color:[\s\S]*?cursor:\s*not-allowed/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-config-done-wrap\.is-disabled:hover \.cw-ab-config-done-tip/,
  );
});

test("debug variants configure and deploy their own model, description, and prompt", () => {
  assert.match(
    createSource,
    /interface DebugVariant \{[\s\S]*?modelName: string;[\s\S]*?description: string;[\s\S]*?instruction: string;/,
  );
  assert.match(
    createSource,
    /<span>描述<\/span>[\s\S]*?value=\{variant\.description\}[\s\S]*?<span>系统提示词<\/span>[\s\S]*?value=\{variant\.instruction\}/,
  );
  assert.match(
    createSource,
    /const releaseDraft = releaseVariant[\s\S]*?modelName: releaseVariant\.modelName \|\| draft\.modelName,[\s\S]*?description: releaseVariant\.description,[\s\S]*?instruction: releaseVariant\.instruction/,
  );
  assert.match(
    createSource,
    /const variantDraft: AgentDraft = \{[\s\S]*?description: variant\.description,[\s\S]*?instruction: variant\.instruction/,
  );
  assert.match(
    createSource,
    /function debugVariantConfigurationKey[\s\S]*?modelName: variant\.modelName\.trim\(\)[\s\S]*?description: variant\.description\.trim\(\)[\s\S]*?instruction: variant\.instruction\.trim\(\)/,
  );
});

test("debug comparison highlights the test configuration entry", () => {
  assert.match(
    createStyles,
    /\.cw-ab-config-trigger\s*\{[\s\S]*?background:\s*hsl\(45 92% 90%\);[\s\S]*?color:\s*hsl\(37 70% 30%\)/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-config-trigger:hover:not\(:disabled\)\s*\{[\s\S]*?background:\s*hsl\(44 88% 84%\)/,
  );
});

test("debug comparison keeps equal spacing above cards and composer", () => {
  assert.match(
    createStyles,
    /\.cw-ab-stage\s*\{[\s\S]*?padding:\s*8px var\(--cw-workspace-gutter\)/,
  );
});

test("agent type is a form section with radio choices", () => {
  assert.match(createSource, /<Section meta=\{metaOf\("type"\)\}>/);
  assert.match(createSource, /role="radiogroup" aria-label="Agent 类型"/);
  assert.match(createSource, /type="radio"[\s\S]*?className="cw-agent-type-radio"/);
  assert.match(createStyles, /\.cw-agent-type-options\s*\{[\s\S]*?display:\s*grid/);
  assert.match(createStyles, /\.cw-agent-type-option\.is-on\s*\{/);
  assert.doesNotMatch(createSource, /cw-typebar|cw-typeradio/);
});

test("build workspace has a validated primary path into debugging", () => {
  assert.match(
    createSource,
    /const openValidation = \(\) => \{[\s\S]*?if \(!requireCompleteDraft\(\)\) return;[\s\S]*?setWorkspaceMode\("validate"\);/,
  );
  assert.match(
    createSource,
    /className="cw-build-next studio-update-action"[\s\S]*?onClick=\{openValidation\}[\s\S]*?>开始调试</,
  );
  assert.match(
    createStyles,
    /\.cw-build-next\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?left:\s*50%;[\s\S]*?transform:\s*translateX\(-50%\);/,
  );
  assert.match(
    createStyles,
    /\.cw-build-next\.studio-update-action\s*\{[\s\S]*?background:\s*#111;[\s\S]*?color:\s*#fff;/,
  );
  assert.match(
    createStyles,
    /\.cw-build-next\.studio-update-action:not\(:disabled\):hover\s*\{[\s\S]*?background:\s*#29292b;[\s\S]*?box-shadow:\s*0 7px 18px hsl\(0 0% 0% \/ 0\.16\);[\s\S]*?transform:\s*translateX\(-50%\);/,
  );
  assert.doesNotMatch(createSource, /下一步：开始调试|<ArrowRight/);
});

test("debug workspace compares multiple configurations behind one shared input", () => {
  assert.match(createSource, /label: "上下文优化"/);
  assert.match(createSource, /label: "幻觉抑制"/);
  assert.doesNotMatch(createSource, /className="cw-optimization-panel"/);
  assert.match(
    createSource,
    /function DebugComparisonWorkspace[\s\S]*?aria-label="A\/B 调试工作台"/,
  );
  assert.match(createSource, /className="cw-ab-add"[\s\S]*?添加对照组/);
  assert.doesNotMatch(createSource, /快速调试|同一条输入将同时发送到全部对照组/);
  assert.match(createSource, /className="cw-ab-config-trigger"[\s\S]*?测试配置/);
  assert.match(createSource, /cw-ab-card-inner\$\{variant\.configOpen \? " is-flipped" : ""\}/);
  assert.match(createSource, /checked=\{variant\.optimizations\.includes\(item\.id\)\}/);
  assert.match(createSource, /className="cw-ab-optimizations-disabled"[\s\S]*?<em>待开放<\/em>/);
  assert.match(createSource, /const startDebugVariant = async \(id: string\)/);
  assert.match(
    createSource,
    /const completeDebugVariantConfig = \(id: string\) => \{[\s\S]*?if \(id === "baseline"\)[\s\S]*?void startDebugVariant\(id\);/,
  );
  assert.match(createSource, /完成并启动/);
  assert.match(createSource, /targets\.map\(async \(variant\)/);
  assert.match(createSource, /modelName: variant\.modelName \|\| draft\.modelName/);
  assert.match(createSource, /variants\.length < 3/);
  assert.doesNotMatch(createSource, /name="debug-release-variant"|发布候选/);
  assert.match(
    createSource,
    /className="cw-ab-deploy"[\s\S]*?onClick=\{\(\) => onDeployVariant\(variant\.id\)\}[\s\S]*?部署该配置/,
  );
  assert.doesNotMatch(createSource, /下一步：部署发布|>部署发布</);
  assert.doesNotMatch(createSource, />验证中心</);
  assert.doesNotMatch(createSource, /className="cw-debug-deploy"/);
  assert.doesNotMatch(createStyles, /\.cw-debug-next/);
  assert.match(createStyles, /\.cw-ab-deploy\s*\{[\s\S]*?background:\s*#111;[\s\S]*?color:\s*#fff;/);
  assert.match(createStyles, /\.cw-ab-card-face\s*\{[\s\S]*?border:\s*1px dashed/);
  assert.match(
    createStyles,
    /\.cw-ab-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/,
  );
  assert.match(createStyles, /\.cw-ab-card-inner\.is-flipped\s*\{[\s\S]*?rotateY\(180deg\)/);
  assert.match(createStyles, /\.cw-ab-config\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(
    createStyles,
    /\.cw-ab-workspace\s*\{[\s\S]*?display:\s*grid;[\s\S]*?grid-template-rows:\s*minmax\(0, 1fr\) auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-ab-composer\s*\{[\s\S]*?position:\s*relative;[\s\S]*?min-width:\s*0;/,
  );
  assert.doesNotMatch(createStyles, /\.cw-ab-head|\.cw-ab-overlay/);
});

test("narrow workbench stacks sections instead of squeezing the form", () => {
  assert.match(
    appStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.sidebar\s*\{[\s\S]*?width:\s*204px;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.cw-editor\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?\.cw-tree\s*\{[\s\S]*?width:\s*100%;[\s\S]*?\.cw-detail\s*\{[\s\S]*?width:\s*100%;[\s\S]*?height:\s*min\(720px,\s*calc\(100dvh\s*-\s*120px\)\);/,
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

test("advanced model connection settings use an accessible disclosure", () => {
  assert.match(createSource, /aria-expanded=\{modelAdvancedOpen\}/);
  assert.match(createSource, /aria-controls=\{modelAdvancedId\}/);
  assert.match(createSource, /<span>更多选项<\/span>/);
  assert.match(
    createSource,
    /\{modelAdvancedOpen && \([\s\S]*?服务商 Provider[\s\S]*?API Base/,
  );
  assert.match(
    createStyles,
    /\.cw-more-options-chevron\.is-open\s*\{[\s\S]*?transform:\s*rotate\(90deg\);/,
  );
});

test("built-in tools adapt columns and scroll after six rows", () => {
  assert.match(createSource, /items=\{BUILTIN_TOOLS\}[\s\S]*?scrollRows=\{6\}/);
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
    /--cw-checklist-row-height:\s*65px;[\s\S]*?grid-auto-rows:\s*minmax\(var\(--cw-checklist-row-height\),\s*auto\);/,
  );
  assert.match(createSource, /scrollRows \* 65 \+ \(scrollRows - 1\) \* 8/);
  assert.match(
    createStyles,
    /@container \(max-width:\s*575px\)\s*\{[\s\S]*?\.cw-checklist-tools\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  );
  assert.match(
    createStyles,
    /\.cw-checklist-tools\s*\{[\s\S]*?max-height:\s*var\(--cw-checklist-max-height\);[\s\S]*?overflow-y:\s*auto;/,
  );
});

test("MCP tools live under an accessible more-tool-types disclosure", () => {
  assert.match(createSource, /aria-expanded=\{moreToolTypesOpen\}/);
  assert.match(createSource, /aria-controls=\{moreToolTypesId\}/);
  assert.match(createSource, /<span>更多类型工具<\/span>/);
  assert.match(
    createSource,
    /\{moreToolTypesOpen && \([\s\S]*?<label className="cw-label">MCP 工具<\/label>/,
  );
  assert.match(
    createSource,
    /mcpTools\.length > 0[\s\S]*?已配置 \{mcpTools\.length\}/,
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
  assert.match(createSource, /if \(!\(await confirmLeaveDebug\(\)\)\) return;/);
});

test("debug environment uses a dedicated hand-drawn run icon", () => {
  assert.match(createSource, /function DebugRunIcon/);
  assert.match(
    createSource,
    /<DebugRunIcon className="cw-i cw-debug-run-icon" \/>[\s\S]*?\{startLabel\}/,
  );
  assert.doesNotMatch(createSource, /<Bug className="cw-i" \/>/);
  assert.match(
    createStyles,
    /\.cw-debug-start\s*\{[\s\S]*?background:\s*#111;[\s\S]*?box-shadow:\s*none;[\s\S]*?color:\s*#fff;/,
  );
  assert.match(
    createStyles,
    /\.cw-debug-start:hover:not\(:disabled\)\s*\{[\s\S]*?background:\s*#29292b;[\s\S]*?box-shadow:\s*0 7px 18px hsl\(0 0% 0% \/ 0\.16\);\s*\}/,
  );
});

test("root Agent exposes a confirmed custom clear action", () => {
  assert.match(createSource, /function ClearAgentIcon/);
  assert.match(createSource, /aria-label="清空根 Agent"/);
  assert.match(createSource, /window\.confirm\("清空根 Agent/);
  assert.match(createSource, /setDraft\(emptyDraft\(\)\)/);
});

test("skill sources open in a fixed-height dialog above a six-row selected list", () => {
  assert.doesNotMatch(
    createSource,
    /从 Skill Hub、本地文件或 AgentKit SkillSpace 添加技能/,
  );
  assert.match(createSource, /label: "AgentKit Skills 中心"/);
  assert.doesNotMatch(createSource, /label: "SkillSpace"/);
  assert.match(createSource, /label: "火山 Find Skill 技能广场"/);
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
    /\.cw-skill-add\s*\{[\s\S]*?justify-content:\s*center;[\s\S]*?min-height:\s*52px;[\s\S]*?padding:\s*9px 10px;[\s\S]*?border:\s*1px dashed[\s\S]*?border-radius:\s*10px;[\s\S]*?background:\s*transparent;/,
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

test("nested Agent forms omit root-only advanced configuration", () => {
  assert.match(createSource, /const isRootAgent = safePath\.length === 0;/);
  assert.match(
    createSource,
    /const rootOnlyStepIds: StepId\[\] = isRootAgent \? \["advanced"\] : \[\];/,
  );
  assert.match(createSource, /\.\.\.rootOnlyStepIds/);
  assert.match(
    createSource,
    /\{isRootAgent && \(\s*<section[\s\S]*?data-step-id="advanced"/,
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
    /远程 Agent 的名称、描述和能力来自中心返回的 Agent Card/,
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
  assert.match(createSource, /\{!a2a && \(\s*<>[\s\S]*?Agent 名称/);
  assert.match(
    createSource,
    /if \(isRoot\) return "远程 Agent 只能作为子 Agent";/,
  );
  assert.doesNotMatch(createSource, /Agent Card 地址|远程 Agent 添加方式/);
  assert.doesNotMatch(createSource, /metaOf\("a2aCenter"\)/);
});

test("memory and tracing are grouped under advanced configuration", () => {
  assert.match(createSource, /aria-expanded=\{advancedConfigOpen\}/);
  assert.match(
    createSource,
    /className="cw-advanced-disclosure-title">进阶配置/,
  );
  assert.doesNotMatch(createSource, /cw-advanced-disclosure-desc/);
  assert.match(
    createSource,
    /cw-advanced-disclosure-title">进阶配置<\/span>[\s\S]*?<ChevronRight/,
  );
  assert.match(
    createSource,
    /\{advancedConfigOpen && \([\s\S]*?<span>记忆<\/span>[\s\S]*?<span>观测<\/span>/,
  );
  assert.doesNotMatch(createSource, /<span>观测与呈现<\/span>/);
  assert.doesNotMatch(
    createStyles,
    /\.cw-advanced-group \+ \.cw-advanced-group\s*\{[^}]*border-top:/,
  );
  assert.doesNotMatch(createSource, /metaOf\("memory"\)/);
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
