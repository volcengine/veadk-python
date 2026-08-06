import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import test from "node:test";

const srcRoot = new URL("../src/", import.meta.url);

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const telemetrySource = readFileSync(
  new URL("../src/adk/telemetry.ts", import.meta.url),
  "utf8",
);
const telemetryEventsSource = readFileSync(
  new URL("../src/adk/telemetryEvents.ts", import.meta.url),
  "utf8",
);
const telemetryClassifiersSource = readFileSync(
  new URL("../src/adk/telemetryClassifiers.ts", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const intelligentCreateSource = readFileSync(
  new URL("../src/create/IntelligentCreate.tsx", import.meta.url),
  "utf8",
);
const codePackageCreateSource = readFileSync(
  new URL("../src/create/CodePackageCreate.tsx", import.meta.url),
  "utf8",
);
const feishuIntegrationSource = readFileSync(
  new URL("../src/automations/feishu/FeishuBotIntegration.tsx", import.meta.url),
  "utf8",
);

function sourceFiles(dirUrl) {
  return readdirSync(dirUrl, { withFileTypes: true }).flatMap((entry) => {
    const entryUrl = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, dirUrl);
    if (entry.isDirectory()) return sourceFiles(entryUrl);
    if (!entry.name.endsWith(".ts") && !entry.name.endsWith(".tsx")) return [];
    return [entryUrl];
  });
}

function relativeSourcePath(fileUrl) {
  return decodeURIComponent(fileUrl.pathname)
    .split("/frontend/src/")
    .at(-1);
}

test("normalizes Studio telemetry from /web/ui-config", () => {
  assert.match(clientSource, /export interface StudioTelemetryConfig/);
  assert.match(clientSource, /function normalizeStudioTelemetryConfig/);
  assert.match(clientSource, /telemetry: normalizeStudioTelemetryConfig\(d\.telemetry\)/);
  assert.match(clientSource, /DISABLED_STUDIO_TELEMETRY/);
});

test("initializes APMPlus lazily and sends Studio custom events", () => {
  assert.match(telemetrySource, /import\("@apmplus\/web"\)/);
  assert.match(telemetrySource, /client\("init"/);
  assert.match(telemetrySource, /client\("start"\)/);
  assert.match(telemetrySource, /apmplusClient\("config", \{ userId \}\)/);
  assert.match(telemetrySource, /apmplusClient\("report"/);
  assert.match(telemetrySource, /ev_type: "custom"/);
});

test("tracks Studio load, authenticated users, Agent deploy results, and Sandbox creation results", () => {
  assert.match(appSource, /initStudioTelemetry\(cfg\.telemetry\)/);
  assert.match(appSource, /trackStudioLoaded/);
  assert.match(telemetryEventsSource, /"studio_instance_loaded"/);
  assert.match(appSource, /identifyStudioTelemetryUser/);
  assert.match(appSource, /userId: access\.telemetry\.userId/);
  assert.doesNotMatch(telemetrySource, /function identityName/);
  assert.match(telemetrySource, /name !== "studio_instance_loaded"/);
  assert.match(telemetrySource, /"studio_agent_deploy"/);
  assert.match(telemetrySource, /"studio_sandbox_create"/);
  assert.doesNotMatch(telemetrySource, /"studio_agent_deploy_succeeded"/);
  assert.doesNotMatch(telemetrySource, /"studio_agent_deploy_failed"/);
  assert.doesNotMatch(telemetrySource, /"studio_sandbox_create_succeeded"/);
  assert.doesNotMatch(telemetrySource, /"studio_sandbox_create_failed"/);
  assert.match(telemetrySource, /user_id: userId/);
  assert.doesNotMatch(clientSource, /deployerId/);
  assert.doesNotMatch(telemetrySource, /deployer_id/);
  assert.match(telemetryEventsSource, /trackStudioEvent\("studio_agent_deploy"/);
  assert.match(telemetryEventsSource, /deploy_status: "succeeded"/);
  assert.match(telemetryEventsSource, /deploy_status: "failed"/);
  assert.match(telemetryEventsSource, /deploy_source: args\.telemetry\.source/);
  assert.match(telemetryEventsSource, /create_mode: args\.telemetry\.createMode/);
  assert.match(telemetryEventsSource, /ai_assisted: args\.telemetry\.aiAssisted/);
  assert.match(telemetryEventsSource, /runtime_id: args\.runtimeId/);
  assert.match(telemetryEventsSource, /failed_phase: args\.phase/);
  assert.match(telemetryEventsSource, /error_kind: agentDeployErrorKind\(args\.error, args\.phase\)/);
  assert.match(telemetryEventsSource, /error_summary: telemetryErrorSummary\(args\.error\)/);
  assert.match(projectPreviewSource, /trackAgentDeploySucceeded/);
  assert.match(projectPreviewSource, /trackAgentDeployFailed/);
  assert.doesNotMatch(projectPreviewSource, /trackStudioEvent/);
  assert.doesNotMatch(projectPreviewSource, /function deploymentErrorKind/);
  assert.doesNotMatch(projectPreviewSource, /studio_agent_deploy_started/);
  assert.match(telemetryEventsSource, /trackStudioEvent\("studio_sandbox_create"/);
  assert.match(telemetryEventsSource, /sandbox_status: "succeeded"/);
  assert.match(telemetryEventsSource, /sandbox_status: "failed"/);
  assert.match(telemetryEventsSource, /sandbox_kind: args\.kind/);
  assert.match(telemetryEventsSource, /sandbox_source: args\.source/);
  assert.match(telemetryEventsSource, /sandbox_session_id: args\.sessionId/);
  assert.match(telemetryEventsSource, /error_kind: sandboxCreateErrorKind\(args\.error\)/);
  assert.match(appSource, /trackSandboxCreateSucceeded/);
  assert.match(appSource, /trackSandboxCreateFailed/);
  assert.doesNotMatch(appSource, /trackStudioEvent/);
  assert.doesNotMatch(appSource, /function sandboxTelemetryErrorKind/);
  assert.doesNotMatch(appSource, /studio_sandbox_create_started/);
  assert.doesNotMatch(telemetrySource, /studio_sandbox_create_started/);
});

test("keeps telemetry event schema and error classification outside UI components", () => {
  assert.match(telemetryEventsSource, /export type DeploymentTelemetrySource/);
  assert.match(telemetryEventsSource, /export type DeploymentCreateMode/);
  assert.match(telemetryEventsSource, /export interface DeploymentTelemetryOrigin/);
  assert.match(telemetryEventsSource, /agentsSource: "local" \| "cloud"/);
  assert.match(telemetryEventsSource, /export type SandboxTelemetryKind = "codex" \| SandboxAgentKind/);
  assert.match(telemetryEventsSource, /function agentDeployCategories/);
  assert.match(telemetryClassifiersSource, /export function agentDeployErrorKind/);
  assert.match(telemetryClassifiersSource, /export function sandboxCreateErrorKind/);
  assert.match(telemetryClassifiersSource, /export function telemetryErrorSummary/);
  assert.match(telemetryClassifiersSource, /name === "RuntimeProbeError"/);
  assert.doesNotMatch(telemetryClassifiersSource, /from "\.\/client"/);
  assert.doesNotMatch(projectPreviewSource, /export type DeploymentTelemetryOrigin/);
  assert.doesNotMatch(projectPreviewSource, /deploy_source:/);
  assert.doesNotMatch(projectPreviewSource, /runtime_network_type:/);
  assert.doesNotMatch(appSource, /sandbox_kind:/);
  assert.doesNotMatch(appSource, /sandbox_session_id:/);
});

test("keeps raw Studio event reporting behind telemetry event wrappers", () => {
  const allowed = new Set(["adk/telemetry.ts", "adk/telemetryEvents.ts"]);
  const offenders = sourceFiles(srcRoot)
    .filter((fileUrl) => statSync(fileUrl).isFile())
    .map((fileUrl) => ({
      path: relativeSourcePath(fileUrl),
      source: readFileSync(fileUrl, "utf8"),
    }))
    .filter(({ path, source }) => !allowed.has(path) && /\btrackStudioEvent\(/.test(source))
    .map(({ path }) => path);

  assert.deepEqual(offenders, []);
});

test("tags deploy telemetry with source, create mode, and AI assistance", () => {
  assert.match(appSource, /setCustomCreateMode\("custom"\)/);
  assert.match(appSource, /setCustomCreateMode\("yaml_import"\)/);
  assert.match(appSource, /createMode=\{customCreateMode\}/);
  assert.match(customCreateSource, /source: "scratch"/);
  assert.match(customCreateSource, /createMode,/);
  assert.match(customCreateSource, /aiAssisted: usedAiGeneration/);
  assert.match(customCreateSource, /setUsedAiGeneration\(true\)/);
  assert.match(intelligentCreateSource, /source: "scratch"/);
  assert.match(intelligentCreateSource, /createMode: "intelligent"/);
  assert.match(intelligentCreateSource, /aiAssisted: true/);
  assert.match(codePackageCreateSource, /source: "code_package"/);
  assert.match(codePackageCreateSource, /createMode: "code_package"/);
  assert.match(codePackageCreateSource, /aiAssisted: false/);
  assert.match(feishuIntegrationSource, /source: "feishu_automation"/);
  assert.match(feishuIntegrationSource, /createMode: "feishu_template"/);
  assert.match(feishuIntegrationSource, /trackAgentDeploySucceeded/);
  assert.match(feishuIntegrationSource, /trackAgentDeployFailed/);
});
