import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const customCreateStyles = readFileSync(
  new URL("../src/create/CustomCreate.css", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);
const modelSource = readFileSync(
  new URL("../src/create/modelSource.ts", import.meta.url),
  "utf8",
);
const cloudProviderSource = readFileSync(
  new URL("../src/adk/cloudProvider.ts", import.meta.url),
  "utf8",
);

test("model configuration switches between ModelArk and custom fields", () => {
  assert.match(
    customCreateSource,
    /const modelSourceOptions = useMemo<[\s\S]*?SelectOption<ModelSource \| "gateway">\[\]/,
  );
  assert.match(customCreateSource, /value: "ark"/);
  assert.match(customCreateSource, /value: "custom"/);
  assert.match(customCreateSource, /value: "gateway"/);
  assert.match(customCreateSource, /label: "模型网关（待上线）"/);
  assert.match(customCreateSource, /disabled: true/);
  assert.match(
    customCreateSource,
    /htmlFor="cw-model-source"[\s\S]*?<Select[\s\S]*?id="cw-model-source"[\s\S]*?options=\{modelSourceOptions\}/,
  );
  assert.match(customCreateSource, /modelSource === "ark" \? \(/);
  assert.match(customCreateSource, /<ModelOptionSelect/);
  assert.match(
    customCreateSource,
    /className="cw-form-section-title cw-model-section-title"/,
  );
  assert.equal(
    customCreateSource.match(/className="cw-label cw-form-section-title"/g)
      ?.length,
    3,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail\.is-basic \.cw-section:nth-child\(3\) \.cw-model-form \{ order: 2; \}/,
  );
  assert.match(customCreateSource, /提供商/);
  assert.match(customCreateSource, /API Base/);
  assert.match(
    customCreateSource,
    /htmlFor="cw-custom-model-provider"[\s\S]*?提供商[\s\S]*?<div className="cw-model-provider-control">[\s\S]*?<Input[\s\S]*?id="cw-custom-model-provider"[\s\S]*?<a[\s\S]*?className="cw-model-provider-help"[\s\S]*?LiteLLM 支持列表/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-model-provider-control\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?gap:\s*6px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-model-config-row,\s*\.cw-detail \.cw-model-picker-field\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/,
  );
});

test("Agent configuration form uses Apps SDK form controls with associated labels", () => {
  assert.doesNotMatch(customCreateSource, /cw-basic-section-title/);
  assert.doesNotMatch(customCreateSource, /const agentTypeOptions =/);
  assert.doesNotMatch(customCreateSource, /htmlFor="cw-agent-type"/);
  assert.doesNotMatch(customCreateSource, /id="cw-agent-type"/);
  assert.doesNotMatch(customCreateSource, /cw-basic-category-field/);
  assert.match(
    customCreateSource,
    /@openai\/apps-sdk-ui\/components\/Input/,
  );
  assert.match(
    customCreateSource,
    /@openai\/apps-sdk-ui\/components\/Textarea/,
  );
  assert.match(
    customCreateSource,
    /@openai\/apps-sdk-ui\/components\/Select/,
  );
  assert.match(
    customCreateSource,
    /htmlFor="cw-agent-name"[\s\S]*?<Input[\s\S]*?id="cw-agent-name"/,
  );
  assert.match(
    customCreateSource,
    /htmlFor="cw-agent-description"[\s\S]*?<Textarea[\s\S]*?id="cw-agent-description"/,
  );
  assert.match(
    customCreateSource,
    /className="cw-field cw-model-config-row cw-basic-name-field"/,
  );
  assert.match(
    customCreateSource,
    /className="cw-field cw-model-config-row cw-basic-description-field"/,
  );
  assert.match(
    customCreateSource,
    /className="cw-field cw-model-config-row cw-basic-prompt-field"/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-model-config-row,\s*\.cw-detail \.cw-model-picker-field\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\);[\s\S]*?align-items:\s*start;[\s\S]*?row-gap:\s*8px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-field\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\);[\s\S]*?align-items:\s*start;[\s\S]*?row-gap:\s*8px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-field > \.cw-label,[\s\S]*?\.cw-detail \.cw-field > :not\(\.cw-label\):not\(\.cw-remote-center-head\)\s*\{[\s\S]*?grid-column:\s*1;/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /这是一个协作容器，本身不生成回答/,
  );
  assert.match(
    customCreateSource,
    /function BackendSelect[\s\S]*?return \([\s\S]*?<Select/,
  );
  assert.match(
    customCreateSource,
    /function A2aSpaceSelect[\s\S]*?<Select[\s\S]*?id="cw-a2a-space"/,
  );
  assert.match(
    customCreateSource,
    /function ResourcePicker<T extends ResourcePickerItem>[\s\S]*?<Select[\s\S]*?id=\{`cw-resource-picker-/,
  );
  assert.match(
    customCreateSource,
    /function VikingKnowledgebaseSelect[\s\S]*?<ResourcePicker/,
  );
  assert.match(
    customCreateSource,
    /function VikingMemorySelect[\s\S]*?<ResourcePicker/,
  );
  assert.match(
    customCreateSource,
    /className="cw-mcp-transport"[\s\S]*?<RadioGroup\.Item[\s\S]*?value="http"/,
  );
  assert.doesNotMatch(customCreateSource, /className=(?:"|\{`)[^\n]*cw-input/);
  assert.doesNotMatch(customCreateSource, /className=(?:"|\{`)[^\n]*cw-textarea/);
  assert.doesNotMatch(customCreateStyles, /\.cw-a2a-space-trigger/);
  assert.doesNotMatch(customCreateStyles, /\.cw-a2a-space-option/);
  assert.doesNotMatch(
    customCreateStyles,
    /--select-control-font-weight/,
  );
});

test("ModelArk picker exposes search, status, loading, empty and retry states", () => {
  assert.match(clientSource, /`\/web\/model-options\$\{query/);
  assert.match(clientSource, /params\.set\("refresh", "true"\)/);
  assert.match(clientSource, /`\/web\/model-api-keys\$\{refresh/);
  assert.doesNotMatch(customCreateSource, /<select[\s\S]*cw-model-key-select/);
  assert.match(
    customCreateSource,
    /@openai\/apps-sdk-ui\/components\/Select/,
  );
  assert.doesNotMatch(customCreateSource, /function CatalogSelect/);
  assert.match(customCreateSource, /id="cw-model-api-key"[\s\S]*?options=\{apiKeyOptions\}/);
  assert.match(customCreateSource, /id="cw-model-name-select"[\s\S]*?options=\{modelOptions\}/);
  assert.match(customCreateSource, /searchPlaceholder="搜索 API Key 名称"/);
  assert.match(
    customCreateSource,
    /response\.keys\.find\(\(key\) => key\.name === apiKeyName\)/,
  );
  assert.match(customCreateSource, /暂无可用 API Key/);
  assert.match(customCreateSource, /searchPredicate=\{catalogSearchPredicate\}/);
  assert.match(
    customCreateSource,
    /searchPlaceholder="搜索名称、Model ID 或服务商"/,
  );
  assert.match(customCreateSource, /OptionView=\{ModelCatalogOptionView\}/);
  assert.match(customCreateSource, /option\.kind === "activation"/);
  assert.match(customCreateSource, /model\.lifecycleStatus === "Retiring"/);
  assert.match(customCreateSource, /即将下线/);
  assert.match(
    customCreateSource,
    /id="cw-model-name-select"[\s\S]*?loading=\{loading\}[\s\S]*?loadingPlaceholder="正在刷新模型列表…"/,
  );
  assert.doesNotMatch(customCreateSource, />\s*正在加载模型列表…\s*</);
  assert.match(customCreateSource, /当前账号下暂无可配置模型/);
  assert.doesNotMatch(customCreateSource, /刷新 API Key 和模型列表/);
  assert.match(customCreateStyles, /\.cw-model-status\.is-available/);
  assert.match(customCreateSource, /disabled: !selectable && !activationRequired/);
  assert.match(customCreateStyles, /\.cw-model-picker-stack/);
  assert.match(customCreateStyles, /\.cw-model-picker-field/);
  assert.match(customCreateStyles, /\.cw-model-picker-label/);
  assert.match(
    customCreateSource,
    /htmlFor="cw-model-source"[\s\S]{0,120}>\s*来源\s*<\/label>/,
  );
  assert.match(
    customCreateSource,
    /htmlFor="cw-model-api-key"[\s\S]{0,120}>\s*API Key\s*<\/label>/,
  );
  assert.match(
    customCreateSource,
    /htmlFor="cw-model-name-select"[\s\S]{0,120}>\s*模型名称\s*<\/label>/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-label,\s*\.cw-detail \.cw-model-picker-label\s*\{[\s\S]*?font-size:\s*var\(--cw-detail-control-font-size\);[\s\S]*?font-weight:\s*400;[\s\S]*?line-height:\s*22px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-model-config-row > \.cw-label,\s*\.cw-detail \.cw-model-picker-field > \.cw-model-picker-label\s*\{[\s\S]*?grid-column:\s*1;[\s\S]*?align-self:\s*start;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-model-config-row,\s*\.cw-detail \.cw-model-picker-field\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\);/,
  );
  assert.doesNotMatch(
    customCreateStyles,
    /@media \(max-width: 1120px\)\s*\{\s*\.cw-detail \.cw-model-picker-field\s*\{/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail\s*\{[\s\S]*?--cw-detail-section-font-size:\s*14px;[\s\S]*?--cw-detail-control-font-size:\s*13px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-agent-config-select-trigger\s*\{\s*font-size:\s*var\(--cw-detail-control-font-size\);\s*font-weight:\s*400;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-agent-config-select-option,\s*\.cw-agent-config-select-option\[data-selected\]\s*\{\s*font-size:\s*13px;\s*font-weight:\s*400;/,
  );
  assert.equal(
    customCreateSource.match(/triggerClassName="cw-agent-config-select-trigger"/g)?.length,
    6,
  );
  assert.equal(
    customCreateSource.match(/optionClassName="cw-agent-config-select-option"/g)?.length,
    6,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail \.cw-field input:not\(\.sr-only\),\s*\.cw-detail \.cw-field textarea\s*\{\s*font-size:\s*var\(--cw-detail-control-font-size\);\s*font-weight:\s*400;/,
  );
  assert.doesNotMatch(
    customCreateStyles,
    /\.cw-section:has\(\.cw-a2a-space-picker\)\s*\{\s*overflow:\s*visible/,
  );
  assert.match(customCreateSource, /loadingPlaceholder="正在刷新模型列表…"/);
  assert.match(customCreateSource, /\? selectedModel\.displayName/);
  assert.match(
    customCreateSource,
    /value: model\.id,\s*label: model\.displayName,/,
  );
  assert.match(
    customCreateSource,
    /searchTerms:\s*\[\s*model\.displayName,\s*model\.id,/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /label: `\$\{model\.displayName\} \(\$\{model\.id\}\)`/,
  );
});

test("ModelArk picker reloads models by API Key without exposing internal Key IDs", () => {
  assert.match(
    customCreateSource,
    /const \[keySelectionRevision, setKeySelectionRevision\]/,
  );
  assert.match(
    customCreateSource,
    /refresh: keySelectionRevision > 0/,
  );
  const modelPicker =
    customCreateSource.match(
      /function ModelOptionSelect[\s\S]*?function A2aSpaceSelect/,
    )?.[0] ?? "";
  assert.doesNotMatch(modelPicker, /reloadKey|刷新 API Key 和模型列表/);
  assert.match(customCreateSource, /setModelsApiKeyId\(null\)/);
  assert.match(customCreateSource, /searchPlaceholder="搜索 API Key 名称"/);
  assert.doesNotMatch(customCreateSource, /搜索 API Key 名称或 ID/);
  assert.doesNotMatch(customCreateSource, /<small>\{key\.id\}<\/small>/);
  assert.doesNotMatch(
    customCreateSource,
    /`\$\{selectedApiKey\.name\} \(\$\{selectedApiKey\.id\}\)`/,
  );
});

test("selecting a ModelArk model updates only the model name", () => {
  const picker = customCreateSource.match(/<ModelOptionSelect[\s\S]*?\/>/)?.[0] ?? "";
  assert.match(picker, /onChange=\{\(modelName\) =>\s*patch\(\{ modelName \}\)\s*\}/);
  assert.doesNotMatch(picker, /modelProvider/);
});

test("selected ModelArk API Key is resolved only by the Studio server", () => {
  assert.match(clientSource, /export async function revealModelApiKey/);
  assert.doesNotMatch(customCreateSource, /getModelApiKeyValue\(/);
  assert.doesNotMatch(customCreateSource, /revealModelApiKey\(/);
  assert.doesNotMatch(customCreateSource, /arkModelApiKeyValue/);
  assert.match(customCreateSource, /MODEL_AGENT_API_KEY/);
  assert.match(customCreateSource, /secret: true/);
  assert.match(customCreateSource, /readOnly: true/);
  assert.match(customCreateSource, /serverManaged: true/);
});

test("unactivated models link to the provider activation console", () => {
  assert.match(
    cloudProviderSource,
    /export function modelActivationConsoleUrl/,
  );
  assert.match(
    cloudProviderSource,
    /https:\/\/console\.volcengine\.com\/ark\/region:ark\+cn-beijing\/openManagement/,
  );
  assert.match(
    cloudProviderSource,
    /https:\/\/console\.byteplus\.com\/ark\/region:ark\+ap-southeast-1\/openManagement/,
  );
  assert.match(
    customCreateSource,
    /modelActivationConsoleUrl\(cloudProvider\)/,
  );
  assert.match(customCreateSource, /window\.open\(/);
  assert.match(customCreateSource, /"_blank"/);
  assert.match(customCreateSource, /"noopener,noreferrer"/);
  assert.match(customCreateSource, /未开通，去开通/);
  assert.match(
    customCreateSource,
    /kind: activationRequired \? "activation" : "model"/,
  );
  assert.match(customCreateSource, /option\.kind === "activation"/);
});

test("custom model fields stay visible and link to LiteLLM providers", () => {
  assert.doesNotMatch(customCreateSource, /cw-model-more-options/);
  assert.match(
    customCreateSource,
    /https:\/\/docs\.litellm\.ai\/docs\/providers/,
  );
  assert.match(customCreateSource, /type="password"/);
  assert.doesNotMatch(
    customCreateSource,
    /id="cw-custom-model-api-base"[\s\S]{0,300}placeholder=/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /id="cw-custom-model-api-key"[\s\S]{0,500}placeholder=/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /<label className="cw-label">模型名称<\/label>[\s\S]{0,300}placeholder=/,
  );
  assert.doesNotMatch(customCreateSource, /留空或使用当前云的官方 Ark 地址时/);
});

test("a newly selected custom model starts empty without changing saved custom drafts", () => {
  assert.match(
    customCreateSource,
    /source === "custom" && modelSource === "ark"[\s\S]*?\? ""/,
  );
  assert.match(
    customCreateSource,
    /htmlFor="cw-custom-model-name"[\s\S]{0,260}<Input[\s\S]{0,260}value=\{node\.modelName \?\? ""\}/,
  );
  assert.match(
    customCreateSource,
    /source === "ark" && !node\.modelName\?\.trim\(\)[\s\S]*?defaultModelName\(cloudProvider\)/,
  );
});

test("configuration fields collapse to one column on narrow screens", () => {
  assert.match(
    customCreateStyles,
    /@media \(max-width: 700px\)[\s\S]*\.cw-field \{[\s\S]*grid-template-columns: minmax\(0, 1fr\)/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-field > :not\(\.cw-label\):not\(\.cw-remote-center-head\)[\s\S]*grid-column: 1/,
  );
});

test("create cards use borders without black drop shadows", () => {
  assert.match(
    customCreateStyles,
    /\.cw-section\s*\{[\s\S]*?box-shadow:\s*none;/,
  );
});

test("inactive custom endpoint fields are excluded from generated configuration", () => {
  assert.match(
    modelSource,
    /modelProvider: source === "ark" \? "" : draft\.modelProvider/,
  );
  assert.match(
    modelSource,
    /modelApiBase: source === "ark" \? "" : draft\.modelApiBase/,
  );
  assert.match(configYamlSource, /if \(draft\.modelSource !== "ark"\)/);
});
