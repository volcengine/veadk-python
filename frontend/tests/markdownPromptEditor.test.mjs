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

test("narrow workbench stacks sections instead of squeezing the form", () => {
  assert.match(
    appStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.sidebar\s*\{[\s\S]*?width:\s*204px;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*1080px\)\s*\{[\s\S]*?\.cw-detail\s*\{[\s\S]*?height:\s*min\(720px,\s*calc\(100dvh\s*-\s*120px\)\);[\s\S]*?\.cw-debug\s*\{[\s\S]*?flex:\s*0\s+0\s+100%;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.cw-editor\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?\.cw-tree\s*\{[\s\S]*?width:\s*100%;[\s\S]*?\.cw-detail\s*\{[\s\S]*?width:\s*100%;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*700px\)\s*\{[\s\S]*?\.cw-typeradio-item\s*\{[\s\S]*?padding-inline:\s*6px;/,
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

test("debug panel can collapse without clearing its external run state", () => {
  assert.match(
    createSource,
    /const \[collapsed, setCollapsed\] = useState\(false\)/,
  );
  assert.match(createSource, /aria-label="收起调试栏"/);
  assert.match(createSource, /aria-label="展开调试栏"/);
  assert.match(
    createSource,
    /className="cw-debug-expand"[\s\S]*?<DebugConsoleIcon className="cw-i" \/>[\s\S]*?<\/button>/,
  );
  assert.doesNotMatch(createSource, /ChevronLeft/);
  assert.match(
    createStyles,
    /\.cw-debug-expand\s*\{[\s\S]*?width:\s*34px;[\s\S]*?height:\s*34px;/,
  );
  assert.match(
    createStyles,
    /\.cw-debug\s*\{[\s\S]*?transition:[\s\S]*?width 0\.22s[\s\S]*?flex-basis 0\.22s/,
  );
  assert.match(createStyles, /@keyframes cw-debug-content-in/);
  assert.match(
    createStyles,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.cw-debug\s*\{\s*transition:\s*none;/,
  );
  assert.match(
    createStyles,
    /\.cw-debug\.is-collapsed\s*\{[\s\S]*?width:\s*48px;/,
  );
});

test("debug environment uses a dedicated hand-drawn run icon", () => {
  assert.match(createSource, /function DebugRunIcon/);
  assert.match(
    createSource,
    /<DebugRunIcon className="cw-i cw-debug-run-icon" \/>[\s\S]*?启动调试环境/,
  );
  assert.doesNotMatch(createSource, /<Bug className="cw-i" \/>/);
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
  assert.match(createSource, /llm: "LLM 智能体"/);
  assert.match(createSource, /sequential: "顺序型智能体"/);
  assert.match(createSource, /parallel: "并行型智能体"/);
  assert.match(createSource, /loop: "循环型智能体"/);
  assert.match(createSource, /a2a: "远程智能体"/);
  assert.match(createSource, /<wbr \/>/);
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
  assert.match(createSource, /远程 Agent 仅可作为子 Agent/);
  assert.match(
    createSource,
    /className="cw-typeradio-disabled-hint"[\s\S]*?role="tooltip"/,
  );
  assert.match(
    createStyles,
    /\.cw-typeradio-item\.is-disabled:hover \.cw-typeradio-disabled-hint/,
  );
  assert.match(
    createStyles,
    /\.cw-typeradio-disabled-hint\s*\{[\s\S]*?top:\s*calc\(100% \+ 17px\)/,
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
