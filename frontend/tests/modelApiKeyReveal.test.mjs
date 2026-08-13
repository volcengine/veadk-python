import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const previewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const previewStyles = readFileSync(
  new URL("../src/ui/ProjectPreview.css", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);

test("reveals a selected ModelArk API Key only after an explicit request", () => {
  assert.match(clientSource, /export async function revealModelApiKey/);
  assert.match(
    clientSource,
    /`\/web\/model-api-keys\/\$\{encodeURIComponent\(apiKeyId\)\}\/value`/,
  );
  assert.match(clientSource, /\{ method: "POST", signal, cache: "no-store" \}/);
  assert.match(clientSource, /cache: "no-store"/);
  assert.match(
    previewSource,
    /await revealModelApiKey\(\s*requestApiKeyId,\s*controller\.signal,?\s*\)/,
  );
  assert.match(previewSource, /value: response\.value/);
  assert.match(previewSource, /由所选 API Key 注入/);
});

test("supports hide, loading, error and retry states with accessible controls", () => {
  assert.match(previewSource, /status: "hidden"/);
  assert.match(previewSource, /status: "loading"/);
  assert.match(previewSource, /status: "visible"/);
  assert.match(previewSource, /status: "error"/);
  assert.match(previewSource, /显示 API Key/);
  assert.match(previewSource, /隐藏 API Key/);
  assert.match(previewSource, /重试显示 API Key/);
  assert.match(previewSource, /aria-label=\{modelApiKeyRevealLabel\}/);
  assert.match(previewSource, /title=\{modelApiKeyRevealLabel\}/);
  assert.match(previewSource, /function ModelApiKeyEyeIcon/);
  assert.match(previewSource, /function ModelApiKeyEyeOffIcon/);
  assert.match(previewStyles, /\.pp-env-secret-toggle/);
  assert.match(previewStyles, /\.pp-env-reveal-error/);
});

test("clears revealed values when hidden, switched, page-hidden or unmounted", () => {
  assert.match(
    previewSource,
    /function clearModelApiKeyReveal[\s\S]*?setModelApiKeyRevealState\(HIDDEN_MODEL_API_KEY_REVEAL\)/,
  );
  assert.match(
    previewSource,
    /useEffect\(\(\) => \{[\s\S]*?clearModelApiKeyReveal\(\);[\s\S]*?\}, \[selectedModelApiKeyId\]\)/,
  );
  assert.match(previewSource, /window\.addEventListener\("pagehide", clearModelApiKeyReveal\)/);
  assert.match(previewSource, /modelApiKeyRevealAbortRef\.current\?\.abort\(\)/);
  assert.match(
    previewSource,
    /return \(\) => \{[\s\S]*?removeEventListener\("pagehide", clearModelApiKeyReveal\);[\s\S]*?clearModelApiKeyReveal\(\);/,
  );
  assert.match(
    previewSource,
    /modelApiKeyRevealState\.apiKeyId === selectedModelApiKeyId/,
  );
});

test("never copies a revealed value into drafts or deployment payloads", () => {
  const deployEnvStart = previewSource.indexOf("function deployEnvVars");
  const deployEnvEnd = previewSource.indexOf(
    "async function handleFeishuToggle",
    deployEnvStart,
  );
  assert.notEqual(deployEnvStart, -1);
  assert.notEqual(deployEnvEnd, -1);
  const deployEnvSource = previewSource.slice(deployEnvStart, deployEnvEnd);
  assert.doesNotMatch(deployEnvSource, /modelApiKeyReveal|revealModelApiKey/);
  assert.doesNotMatch(customCreateSource, /revealModelApiKey/);
  assert.doesNotMatch(previewSource, /onDeploymentEnvChange\?\.\([^)]*response\.value/);
});
