import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

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
  assert.match(appSource, /"studio_instance_loaded"/);
  assert.match(appSource, /identifyStudioTelemetryUser/);
  assert.match(appSource, /userId: access\.telemetry\.userId/);
  assert.doesNotMatch(telemetrySource, /function identityName/);
  assert.match(telemetrySource, /name !== "studio_instance_loaded"/);
  assert.match(telemetrySource, /"studio_agent_deploy_succeeded"/);
  assert.match(telemetrySource, /"studio_agent_deploy_failed"/);
  assert.match(telemetrySource, /"studio_sandbox_create_succeeded"/);
  assert.match(telemetrySource, /"studio_sandbox_create_failed"/);
  assert.match(telemetrySource, /user_id: userId/);
  assert.doesNotMatch(clientSource, /deployerId/);
  assert.doesNotMatch(telemetrySource, /deployer_id/);
  assert.match(projectPreviewSource, /trackStudioEvent\("studio_agent_deploy_succeeded"/);
  assert.match(projectPreviewSource, /trackStudioEvent\("studio_agent_deploy_failed"/);
  assert.match(projectPreviewSource, /runtime_id: result\.runtimeId/);
  assert.match(projectPreviewSource, /failed_phase: latestPhase/);
  assert.match(projectPreviewSource, /error_kind: deploymentErrorKind\(err, latestPhase\)/);
  assert.doesNotMatch(projectPreviewSource, /studio_agent_deploy_started/);
  assert.match(appSource, /trackStudioEvent\("studio_sandbox_create_succeeded"/);
  assert.match(appSource, /trackStudioEvent\("studio_sandbox_create_failed"/);
  assert.match(appSource, /sandbox_kind: sandboxLaunchKind/);
  assert.match(appSource, /sandbox_source: sandboxLaunchFromAgents \? "my_agents" : "new_chat"/);
  assert.match(appSource, /sandbox_session_id: createdSession\.id/);
  assert.match(appSource, /error_kind: sandboxTelemetryErrorKind\(launchError\)/);
  assert.doesNotMatch(appSource, /studio_sandbox_create_started/);
  assert.doesNotMatch(telemetrySource, /studio_sandbox_create_started/);
});

test("tags deploy telemetry with the creation workflow source", () => {
  assert.match(customCreateSource, /deploymentTelemetrySource="custom_create"/);
  assert.match(intelligentCreateSource, /deploymentTelemetrySource="intelligent_create"/);
  assert.match(codePackageCreateSource, /deploymentTelemetrySource="code_package"/);
});
