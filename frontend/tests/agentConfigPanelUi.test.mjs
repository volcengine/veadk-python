import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panelSource = readFileSync(
  new URL("../src/ui/AgentConfigPanel.tsx", import.meta.url),
  "utf8",
);
const panelStyles = readFileSync(
  new URL("../src/ui/AgentConfigPanel.css", import.meta.url),
  "utf8",
);
const modelFieldsSource = readFileSync(
  new URL("../src/ui/AgentModelConfigFields.tsx", import.meta.url),
  "utf8",
);
const debugPanelSource = readFileSync(
  new URL("../src/ui/AgentDebugConfigPanel.tsx", import.meta.url),
  "utf8",
);
const storageDialogSource = readFileSync(
  new URL("../src/ui/AgentStorageConfigDialog.tsx", import.meta.url),
  "utf8",
);
const storageDialogStyles = readFileSync(
  new URL("../src/ui/AgentStorageConfigDialog.css", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/create/CreateWorkspace.tsx", import.meta.url),
  "utf8",
);

test("shared model configuration uses native Apps SDK controls", () => {
  assert.match(
    modelFieldsSource,
    /import \{ Select, type Option \} from "@openai\/apps-sdk-ui\/components\/Select"/,
  );
  assert.match(
    modelFieldsSource,
    /import \{ Input \} from "@openai\/apps-sdk-ui\/components\/Input"/,
  );
  assert.doesNotMatch(modelFieldsSource, /components\/(?:Menu|SelectControl)/);
  assert.match(
    modelFieldsSource,
    /<Select[\s\S]*?id=\{fieldId\("category"\)\}[\s\S]*?options=\{MODEL_CATEGORY_OPTIONS\}[\s\S]*?size="md"[\s\S]*?pill=\{false\}/,
  );
  assert.match(
    panelSource,
    /<AgentModelConfigFields[\s\S]*?idPrefix="agent-config"/,
  );
  assert.match(
    debugPanelSource,
    /<AgentModelConfigFields[\s\S]*?idPrefix=\{idPrefix\}/,
  );
});

test("basic information groups definition fields before model configuration", () => {
  const nameIndex = panelSource.indexOf('htmlFor="agent-config-name"');
  const definitionIndex = panelSource.indexOf(">定义</h3>");
  const descriptionIndex = panelSource.indexOf(
    'htmlFor="agent-config-description"',
  );
  const systemPromptIndex = panelSource.indexOf(
    'htmlFor="agent-config-system-prompt"',
  );
  const modelIndex = panelSource.indexOf(">模型配置</h3>");

  assert.ok(nameIndex >= 0);
  assert.ok(definitionIndex > nameIndex);
  assert.ok(descriptionIndex > definitionIndex);
  assert.ok(systemPromptIndex > descriptionIndex);
  assert.ok(modelIndex > systemPromptIndex);
  assert.match(
    panelSource,
    /aria-labelledby="agent-config-definition-heading"[\s\S]*?<h3 id="agent-config-definition-heading">定义<\/h3>/,
  );
});

test("agent name is controlled by the workspace and shared by header and input", () => {
  assert.match(panelSource, /agentName: string/);
  assert.match(panelSource, /onAgentNameChange: \(value: string\) => void/);
  assert.match(panelSource, /<h2>\{agentName\}<\/h2>/);
  assert.match(
    panelSource,
    /id="agent-config-name"[\s\S]*?value=\{agentName\}[\s\S]*?onAgentNameChange\(event\.target\.value\)/,
  );
  assert.doesNotMatch(panelSource, /useState\(title\)/);
});

test("model configuration fields use the shared horizontal field row", () => {
  for (const fieldSuffix of [
    "category",
    "custom-provider",
    "custom-model-name",
    "custom-base-url",
    "custom-api-key",
    "volcano-api-key",
    "volcano-model-name",
  ]) {
    assert.match(
      modelFieldsSource,
      new RegExp(`fieldId\\("${fieldSuffix}"\\)`),
    );
  }
  assert.match(
    panelStyles,
    /\.agent-config-panel__field\s*\{[\s\S]*?grid-template-columns:\s*72px minmax\(0, 1fr\)/,
  );
});

test("panel CSS does not restyle Apps SDK control internals", () => {
  assert.doesNotMatch(
    panelStyles,
    /\.agent-config-panel__(?:control|select-control)\s+(?:input|textarea|span)/,
  );
  assert.doesNotMatch(panelStyles, /\.agent-config-panel__select-option/);
});

test("capability tools use the native Apps SDK Checkbox", () => {
  assert.match(
    panelSource,
    /import \{ Checkbox \} from "@openai\/apps-sdk-ui\/components\/Checkbox"/,
  );
  assert.match(panelSource, /const AGENT_TOOL_COLUMNS/);
  assert.equal((panelSource.match(/label: "并行联网搜索"/g) ?? []).length, 2);
  assert.equal((panelSource.match(/label: "网页读取"/g) ?? []).length, 2);
  assert.equal((panelSource.match(/label: "图像生成"/g) ?? []).length, 2);
  assert.match(
    panelSource,
    /<Checkbox[\s\S]*?className="agent-config-panel__tool-checkbox"[\s\S]*?onCheckedChange=/,
  );
});

test("capability tools preserve the Figma grid and match basic field titles", () => {
  assert.match(
    panelSource,
    /className="agent-config-panel__tools-field"[\s\S]*?className="agent-config-panel__field-label"[\s\S]*?工具[\s\S]*?className="agent-config-panel__tool-grid"/,
  );
  assert.doesNotMatch(panelSource, /agent-config-tools-heading|tool-title/);
  assert.match(
    panelStyles,
    /\.agent-config-panel__tool-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)[\s\S]*?column-gap:\s*8px/,
  );
  assert.match(
    panelStyles,
    /\.agent-config-panel__tool-column\s*\{[\s\S]*?row-gap:\s*12px/,
  );
  assert.match(
    panelStyles,
    /\.agent-config-panel__stacked-field label,\s*\.agent-config-panel__field-label\s*\{[\s\S]*?color:\s*hsl\(var\(--foreground\)\)[\s\S]*?font-size:\s*13px/,
  );
  assert.match(
    panelStyles,
    /\.agent-config-panel__tool-checkbox\s*>\s*button\[role="checkbox"\]\s*\{[\s\S]*?width:\s*16px[\s\S]*?height:\s*16px[\s\S]*?border-width:\s*0\.5px/,
  );
  assert.match(
    panelStyles,
    /button\[role="checkbox"\]\[data-state="unchecked"\]\s*\{[\s\S]*?border-color:\s*#b8b7c3/,
  );
});

test("capability MCP and skill groups use the Figma tag states", () => {
  assert.match(
    panelSource,
    /import \{ Grid, XXs \} from "@openai\/apps-sdk-ui\/components\/Icon"/,
  );
  assert.doesNotMatch(panelSource, /Plus14px/);
  assert.match(
    panelSource,
    /className="agent-config-panel__add-icon"[\s\S]*?viewBox="0 0 16 16"[\s\S]*?M7\.5 13\.3334V8\.5/,
  );
  assert.match(
    panelSource,
    /className="agent-config-panel__field-label">MCP<\/span>[\s\S]*?selectedMcps\.map/,
  );
  assert.match(
    panelSource,
    /className="agent-config-panel__field-label">技能<\/span>[\s\S]*?selectedSkills\.map/,
  );
  assert.match(
    panelSource,
    /<CapabilityAddButton[\s\S]*?label=" MCP"[\s\S]*?<CapabilityAddButton[\s\S]*?label="技能"/,
  );
  assert.match(
    panelStyles,
    /\.agent-config-panel__capability-chip,[\s\S]*?\.agent-config-panel__capability-add\s*\{[\s\S]*?height:\s*26px[\s\S]*?padding:\s*2px 8px[\s\S]*?border-radius:\s*8px[\s\S]*?font-size:\s*12px/,
  );
  assert.match(
    panelStyles,
    /\.agent-config-panel__capability-list\s*\{[\s\S]*?flex-wrap:\s*wrap[\s\S]*?gap:\s*6px/,
  );
});

test("knowledge and memory capabilities use independent native switches", () => {
  assert.match(
    panelSource,
    /import \{ Switch \} from "@openai\/apps-sdk-ui\/components\/Switch"/,
  );
  for (const capability of [
    "knowledgeBase",
    "shortTermMemory",
    "longTermMemory",
  ]) {
    assert.match(storageDialogSource, new RegExp(capability));
  }
  assert.match(
    panelSource,
    /className="agent-config-panel__storage-toggle-row"[\s\S]*?<Switch/,
  );
  assert.match(
    panelStyles,
    /\.agent-config-panel__storage-toggle-row\s*\{[\s\S]*?justify-content:\s*space-between/,
  );
  assert.match(
    workspaceSource,
    /storageCapabilities:\s*createDefaultAgentStorageCapabilities\(\)/,
  );
});

test("storage dialog and configured card preserve the Figma geometry", () => {
  assert.match(storageDialogSource, /createPortal/);
  assert.match(storageDialogSource, /role="dialog"/);
  assert.match(storageDialogSource, /role="radiogroup"/);
  assert.match(storageDialogSource, /平台托管存储/);
  assert.match(storageDialogSource, /企业数据库/);
  assert.match(storageDialogSource, /本地存储/);
  assert.match(storageDialogSource, /<Select[\s\S]*?size="md"/);
  assert.match(
    storageDialogStyles,
    /\.agent-storage-dialog\s*\{[\s\S]*?width:\s*520px[\s\S]*?border-radius:\s*16px/,
  );
  assert.match(
    storageDialogStyles,
    /\.agent-storage-dialog__option\s*\{[\s\S]*?height:\s*70px[\s\S]*?padding:\s*12px[\s\S]*?border-radius:\s*12px/,
  );
  assert.match(
    storageDialogStyles,
    /\.agent-storage-card\s*\{[\s\S]*?height:\s*70px[\s\S]*?padding:\s*12px[\s\S]*?border-radius:\s*12px/,
  );
});

test("storage dialog titles vary while the shared contents stay identical", () => {
  assert.match(
    storageDialogSource,
    /knowledgeBase:\s*\{ label: "知识库", dialogTitle: "知识库配置" \}/,
  );
  assert.match(
    storageDialogSource,
    /shortTermMemory:\s*\{ label: "短期记忆", dialogTitle: "短期记忆存储" \}/,
  );
  assert.match(
    storageDialogSource,
    /longTermMemory:\s*\{ label: "长期记忆", dialogTitle: "长期记忆存储" \}/,
  );
  assert.match(
    panelSource,
    /AGENT_STORAGE_CAPABILITY_LABELS\[activeStorageCapability\]\.dialogTitle/,
  );
});
