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
  assert.match(customCreateSource, /<RadioGroup<ModelSource \| "gateway">/);
  assert.match(customCreateSource, /value: "ark" as const/);
  assert.match(customCreateSource, /value: "custom" as const/);
  assert.match(customCreateSource, /value: "gateway" as const/);
  assert.match(customCreateSource, /label: "模型网关"/);
  assert.match(customCreateSource, /disabled: true/);
  assert.match(customCreateSource, /待上线/);
  assert.match(customCreateSource, /modelSource === "ark" \? \(/);
  assert.match(customCreateSource, /<ModelOptionSelect/);
  assert.match(customCreateSource, /服务商 Provider/);
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
  assert.equal(customCreateSource.match(/<CatalogSelect/g)?.length, 2);
  assert.match(customCreateSource, /triggerAriaLabel="选择 API Key"/);
  assert.match(customCreateSource, /menuAriaLabel="API Key 列表"/);
  assert.match(customCreateSource, /searchPlaceholder="搜索 API Key 名称"/);
  assert.match(
    customCreateSource,
    /response\.keys\.find\(\(key\) => key\.name === apiKeyName\)/,
  );
  assert.match(customCreateSource, /暂无可用 API Key/);
  assert.match(customCreateSource, /\["ArrowDown", "ArrowUp", "Home", "End"\]/);
  assert.match(
    customCreateSource,
    /searchPlaceholder="搜索名称、Model ID 或服务商"/,
  );
  assert.match(customCreateSource, /createPortal\(/);
  assert.match(customCreateSource, /top: menuPosition\.top \?\? "auto"/);
  assert.match(customCreateSource, /bottom: menuPosition\.bottom \?\? "auto"/);
  assert.match(customCreateSource, /model\.lifecycleStatus === "Retiring"/);
  assert.match(customCreateSource, /即将下线/);
  assert.match(customCreateSource, /正在加载模型列表/);
  assert.match(customCreateSource, /当前账号下暂无可配置模型/);
  assert.match(customCreateSource, /刷新 API Key 和模型列表/);
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
    /<label className="cw-label">\s*模型名称\s*<\/label>[\s\S]{0,220}value=\{node\.modelName \?\? ""\}/,
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
