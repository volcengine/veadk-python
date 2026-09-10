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
const modelFallbackFieldsSource = readFileSync(
  new URL("../src/create/ModelFallbackFields.tsx", import.meta.url),
  "utf8",
);
const newAgentWorkbenchSource = readFileSync(
  new URL("../src/create/NewAgentWorkbench.tsx", import.meta.url),
  "utf8",
);
const modelSource = readFileSync(
  new URL("../src/create/modelSource.ts", import.meta.url),
  "utf8",
);
const modelApiBaseSource = readFileSync(
  new URL("../src/create/modelApiBase.ts", import.meta.url),
  "utf8",
);
const cloudProviderSource = readFileSync(
  new URL("../src/adk/cloudProvider.ts", import.meta.url),
  "utf8",
);

test("model configuration switches between ModelArk and custom fields", () => {
  assert.match(customCreateSource, /<RadioGroup<ModelSource \| "gateway">/);
  assert.match(customCreateSource, /value: "ark" as const/);
  assert.match(customCreateSource, /value: "custom" as const/);
  assert.match(customCreateSource, /value: "gateway" as const/);
  assert.match(customCreateSource, /label: t\("traditional\.model\.gateway"\)/);
  assert.match(customCreateSource, /disabled: true/);
  assert.match(customCreateSource, /t\("traditional\.model\.comingSoon"\)/);
  assert.match(customCreateSource, /modelSource === "ark" \? \(/);
  assert.match(customCreateSource, /<ModelOptionSelect/);
  assert.match(customCreateSource, /t\("traditional\.model\.provider"\)/);
  assert.match(customCreateSource, /API Base/);
  assert.match(
    customCreateStyles,
    /\.cw-model-source-field[\s\S]*align-items: center/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-model-source-options[\s\S]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/,
  );
});

test("ModelArk picker exposes search, status, loading, empty and retry states", () => {
  assert.match(clientSource, /`\/web\/model-options\$\{query/);
  assert.match(clientSource, /params\.set\("refresh", "true"\)/);
  assert.match(clientSource, /`\/web\/model-api-keys\$\{refresh/);
  assert.doesNotMatch(customCreateSource, /<select[\s\S]*cw-model-key-select/);
  assert.match(customCreateSource, /function CatalogSelect/);
  assert.equal(customCreateSource.match(/<CatalogSelect/g)?.length, 3);
  assert.match(customCreateSource, /triggerAriaLabel=\{t\("traditional\.model\.selectApiKey"\)\}/);
  assert.match(customCreateSource, /menuAriaLabel=\{t\("traditional\.model\.apiKeyList"\)\}/);
  assert.match(customCreateSource, /searchPlaceholder=\{t\("traditional\.model\.searchApiKeyName"\)\}/);
  assert.match(
    customCreateSource,
    /response\.keys\.find\(\(key\) => key\.name === apiKeyName\)/,
  );
  assert.match(customCreateSource, /t\("traditional\.model\.noApiKeys"\)/);
  assert.match(customCreateSource, /\["ArrowDown", "ArrowUp", "Home", "End"\]/);
  assert.match(
    customCreateSource,
    /searchPlaceholder=\{t\("traditional\.model\.searchPlaceholder"\)\}/,
  );
  assert.match(customCreateSource, /createPortal\(/);
  assert.match(customCreateSource, /top: menuPosition\.top \?\? "auto"/);
  assert.match(customCreateSource, /bottom: menuPosition\.bottom \?\? "auto"/);
  assert.match(customCreateSource, /model\.lifecycleStatus === "Retiring"/);
  assert.match(customCreateSource, /"traditional\.model\.retiring"/);
  assert.match(customCreateSource, /t\("traditional\.model\.loading"\)/);
  assert.match(customCreateSource, /t\("traditional\.model\.empty"\)/);
  assert.match(customCreateSource, /t\("traditional\.model\.refresh"\)/);
  assert.match(customCreateStyles, /\.cw-model-status\.is-available/);
  assert.match(customCreateStyles, /\.cw-model-option:disabled/);
  assert.match(customCreateStyles, /\.cw-model-picker-stack/);
  assert.match(customCreateStyles, /\.cw-model-picker-field/);
  assert.match(customCreateStyles, /\.cw-model-picker-label/);
  assert.doesNotMatch(
    customCreateStyles,
    /\.cw-section:has\(\.cw-a2a-space-picker\)\s*\{\s*overflow:\s*visible/,
  );
  assert.match(customCreateSource, /const width = Math\.min\(\s*rect\.width,/);
});

test("ModelArk picker refreshes by API Key without exposing internal Key IDs", () => {
  assert.match(
    customCreateSource,
    /const \[keySelectionRevision, setKeySelectionRevision\]/,
  );
  assert.match(
    customCreateSource,
    /refresh: reloadKey > 0 \|\| keySelectionRevision > 0/,
  );
  assert.match(customCreateSource, /setModelsApiKeyId\(null\)/);
  assert.match(customCreateSource, /searchPlaceholder=\{t\("traditional\.model\.searchApiKeyName"\)\}/);
  assert.doesNotMatch(customCreateSource, /搜索 API Key 名称或 ID/);
  assert.doesNotMatch(customCreateSource, /<small>\{key\.id\}<\/small>/);
  assert.doesNotMatch(
    customCreateSource,
    /`\$\{selectedApiKey\.name\} \(\$\{selectedApiKey\.id\}\)`/,
  );
});

test("selecting a ModelArk model updates model fallback state only", () => {
  const picker = customCreateSource.match(/<ModelOptionSelect[\s\S]*?\/>/)?.[0] ?? "";
  assert.match(picker, /onChange=\{\(modelName\) =>\s*patch\(\{[\s\S]*?modelName,/);
  assert.match(picker, /modelFallbacks: normalizeModelFallbacks/);
  assert.doesNotMatch(picker, /modelProvider/);
});

test("custom creation supports ordered same-provider fallback models", () => {
  assert.match(customCreateSource, /<ModelFallbackFields/);
  assert.match(customCreateSource, /primaryModelName=\{node\.modelName \?\? ""\}/);
  assert.match(
    customCreateSource,
    /modelSource === "custom" && \(\s*<ModelFallbackFields/,
  );
  assert.match(configYamlSource, /modelFallbacks = normalizeModelFallbacks/);
});

test("ModelArk fallback models use the provider model dropdown", () => {
  assert.match(customCreateSource, /fallbackModelsForSearch/);
  assert.match(customCreateSource, /fallbackSearchQuery/);
  assert.match(customCreateSource, /onFallbacksChange=\{\(modelFallbacks\)/);
  assert.match(
    customCreateSource,
    /t\("traditional\.model\.fallbackPlaceholder"\)/,
  );
});

test("cross-provider fallback editor hides env internals and keeps rows on blur", () => {
  assert.doesNotMatch(modelFallbackFieldsSource, /model\.apiKeyEnv/);
  assert.doesNotMatch(modelFallbackFieldsSource, /invalidApiKeyEnv/);
  assert.doesNotMatch(modelFallbackFieldsSource, /onBlur=\{normalizeCurrentValue\}/);
  assert.match(modelFallbackFieldsSource, /modelApiKeyEnv: fallbackApiKeyEnv/);
  assert.match(modelFallbackFieldsSource, /configuredSecretEnvKeys/);
  assert.match(modelFallbackFieldsSource, /configuredSecret[\s\S]*?"••••••"/);
});

test("fallback editor keeps row identity stable while switching provider type", () => {
  assert.doesNotMatch(modelFallbackFieldsSource, /key=\{`\$\{fallbackValue/);
  assert.doesNotMatch(modelFallbackFieldsSource, /key=\{`endpoint-/);
  assert.match(modelFallbackFieldsSource, /key=\{`fallback-row-\$\{index\}`\}/);
});

test("fallback editor keeps the model name field consistent across provider types", () => {
  assert.match(modelFallbackFieldsSource, /model-fallback-fields__model-name/);
  assert.match(
    modelFallbackFieldsSource,
    /<span className="model-fallback-fields__field-label">\s*\{t\(`\$\{variant\}\.model\.name`\)\}/,
  );
  assert.match(modelFallbackFieldsSource, /model-fallback-fields__endpoint-details/);
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
  assert.match(customCreateSource, /t\("traditional\.model\.activateAction"\)/);
  assert.match(
    customCreateSource,
    /className="cw-a2a-space-option cw-model-option is-activation-link"/,
  );
  assert.match(customCreateStyles, /\.cw-model-option\.is-activation-link/);
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
    /<label className="cw-label">\{t\("traditional\.model\.name"\)\}<\/label>[\s\S]{0,300}placeholder=/,
  );
  assert.doesNotMatch(customCreateSource, /留空或使用当前云的官方 Ark 地址时/);
});

test("custom model API base fields validate absolute HTTP URLs", () => {
  assert.match(modelApiBaseSource, /isValidModelApiBaseUrl/);
  assert.match(modelApiBaseSource, /url\.protocol === "https:"/);
  assert.match(modelApiBaseSource, /url\.protocol === "http:"/);
  assert.match(customCreateSource, /isValidModelApiBaseUrl\(\s*node\.modelApiBase/);
  assert.match(newAgentWorkbenchSource, /isValidModelApiBaseUrl\(apiBase\)/);
  assert.match(modelFallbackFieldsSource, /isValidModelApiBaseUrl\(endpoint\.modelApiBase\)/);
  assert.match(customCreateSource, /traditional\.model\.invalidApiBase/);
  assert.match(newAgentWorkbenchSource, /workbench\.model\.invalidApiBase/);
  assert.match(modelFallbackFieldsSource, /\$\{variant\}\.model\.invalidApiBase/);
});

test("a newly selected custom model starts empty without changing saved custom drafts", () => {
  assert.match(
    customCreateSource,
    /source === "custom" && modelSource === "ark"[\s\S]*?\? ""/,
  );
  assert.match(
    customCreateSource,
    /<label className="cw-label">\s*\{t\("traditional\.model\.name"\)\}\s*<\/label>[\s\S]{0,220}value=\{node\.modelName \?\? ""\}/,
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
