import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const projectPreviewStyles = readFileSync(
  new URL("../src/ui/ProjectPreview.css", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const codePackageCreateSource = readFileSync(
  new URL("../src/create/CodePackageCreate.tsx", import.meta.url),
  "utf8",
);

test("deployment sends the selected Runtime instance range", () => {
  assert.match(
    projectPreviewSource,
    /!agentDraft\.memory\.shortTerm[\s\S]*?agentDraft\.shortTermBackend \|\| "local"[\s\S]*?=== "local"/,
  );
  assert.match(
    projectPreviewSource,
    /sessionStorage: inMemorySession \? "in-memory" : "persistent"/,
  );
  assert.match(projectPreviewSource, /minInstance: instanceRange\.min/);
  assert.match(projectPreviewSource, /maxInstance: instanceRange\.max/);
  assert.match(clientSource, /sessionStorage: opts\?\.sessionStorage/);
  assert.match(clientSource, /minInstance: opts\?\.minInstance/);
  assert.match(clientSource, /maxInstance: opts\?\.maxInstance/);
});

test("renders Runtime instance inputs with memory-aware and Sidecar-safe defaults", () => {
  assert.match(
    projectPreviewSource,
    /const \[minInstance, setMinInstance\] = useState\("1"\)/,
  );
  assert.match(
    projectPreviewSource,
    /const \[maxInstance, setMaxInstance\] = useState\([\s\S]*?inMemorySession \|\| sidecarEnabled \? "1" : "5"/,
  );
  assert.match(
    projectPreviewSource,
    /id="runtime-min-instance"[\s\S]*?type="number"[\s\S]*?min="0"[\s\S]*?value=\{minInstance\}/,
  );
  assert.match(
    projectPreviewSource,
    /id="runtime-max-instance"[\s\S]*?type="number"[\s\S]*?value=\{maxInstance\}/,
  );
  assert.match(
    projectPreviewSource,
    /disabled=\{deploying \|\| sidecarEnabled\}/,
  );
  assert.match(projectPreviewSource, /min < 0/);
  assert.match(
    projectPreviewSource,
    /t\("projectPreview\.errors\.instanceRangeInteger"\)/,
  );
  assert.match(
    projectPreviewSource,
    /inMemorySession \|\| sidecarEnabled[\s\S]*?className="pp-instance-note"[\s\S]*?projectPreview\.sidecarSingleInstance[\s\S]*?projectPreview\.inMemorySingleInstance/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-instance-note\s*\{[\s\S]*?color:\s*hsl\(42 96% 43%\);[\s\S]*?font-size:\s*12px/,
  );
});

test("renders the Runtime update progress step conditionally", () => {
  assert.match(
    projectPreviewSource,
    /deploymentStepsWithInstanceUpdate = needsInstanceUpdate[\s\S]*?\[\.\.\.baseDeploymentSteps, \{ phase: "update", label: t\("projectPreview\.steps\.updateInstances"\) \}\][\s\S]*?: baseDeploymentSteps[\s\S]*?deploymentStepsBeforeGithub = effectiveCreateEvaluationSets[\s\S]*?projectPreview\.steps\.createEvaluationSets[\s\S]*?deploymentStepsWithGithub[\s\S]*?projectPreview\.steps\.syncCode/,
  );
  assert.match(
    workspaceSource,
    /if \(task\.instanceRange\) steps\.push\(instanceUpdateStep\(task\.instanceRange, t\)\)/,
  );
  assert.match(
    workspaceSource,
    /if \(task\.instanceRange\)[\s\S]*?if \(task\.createEvaluationSets\)[\s\S]*?agentWorkspace\.deploymentSteps\.evaluation[\s\S]*?if \(task\.mpaProfile\)[\s\S]*?if \(task\.githubDelivery\)[\s\S]*?agentWorkspace\.deploymentSteps\.github[\s\S]*?steps\.push\(baseSteps\[baseSteps\.length - 1\]\)/,
  );
  assert.match(
    workspaceSource,
    /phase: "update"[\s\S]*?label: t\("agentWorkspace\.deploymentSteps\.update\.label"\)[\s\S]*?description: t\("agentWorkspace\.deploymentSteps\.update\.description", range\)/,
  );
});

test("structured Agent deployments apply MPA Profile after Runtime publish", () => {
  assert.match(clientSource, /export async function applyMpaProfileAfterDeployment/);
  assert.match(clientSource, /sourceProfileId = params\.sourceDraftId\?\.trim\(\)/);
  assert.match(clientSource, /`studio-draft:\$\{params\.sourceDraftId\.trim\(\)\}`/);
  assert.doesNotMatch(clientSource, /sourceProfileRevision/);
  assert.match(projectPreviewSource, /applyMpaProfileAfterDeployment\(/);
  assert.match(
    projectPreviewSource,
    /const isMpaDeployment = Boolean\(agentDraft\);[\s\S]*?const shouldRunMpaLifecycle = isMpaDeployment && !githubUpdateOffloaded/,
  );
  assert.match(
    projectPreviewSource,
    /const deploymentSteps = shouldRunMpaLifecycle[\s\S]*?phase: "profile_applying"[\s\S]*?phase: "smoke_running"[\s\S]*?phase: "runnable"/,
  );
  assert.match(
    projectPreviewSource,
    /if \(shouldRunMpaLifecycle && agentDraft && \(completeResult\.runtimeId \|\| deploymentRuntimeId\)\)[\s\S]*?applyMpaProfileAfterDeployment/,
  );
  assert.match(
    projectPreviewSource,
    /agentCategory: isMpaDeployment \? "mpa" : "general"/,
  );
  assert.match(
    projectPreviewSource,
    /syncGithubCicdRuntime\(\{[\s\S]*?agentCategory: isMpaDeployment \? "mpa" : "general"/,
  );
  assert.match(customCreateSource, /agentCategory: "mpa"/);
  assert.match(
    projectPreviewSource,
    /runtimeRevision: isRuntimeUpdate \? deploymentRuntimeRevision : undefined/,
  );
  assert.match(projectPreviewSource, /mpaProfile: shouldRunMpaLifecycle/);
  assert.match(projectPreviewSource, /mpaSmoke: shouldRunMpaLifecycle && !isRuntimeUpdate/);
  assert.match(workspaceSource, /if \(task\.mpaProfile\)/);
  assert.match(workspaceSource, /if \(task\.mpaSmoke\)/);
  assert.match(customCreateSource, /applyMpaProfileAfterDeployment/);
  assert.match(customCreateSource, /runtimeRevision: deploymentTarget\?\.etag/);
  assert.match(customCreateSource, /deploymentRuntimeRevision=\{deploymentTarget\?\.etag\}/);
  assert.doesNotMatch(codePackageCreateSource, /agentDraft=\{/);
  assert.doesNotMatch(codePackageCreateSource, /applyMpaProfileAfterDeployment/);
});

test("renders the evaluation-set progress step only when selected", () => {
  assert.match(
    projectPreviewSource,
    /phase: "evaluation"[\s\S]*?label: t\("projectPreview\.steps\.createEvaluationSets"\)/,
  );
  assert.match(
    projectPreviewSource,
    /effectiveCreateEvaluationSets[\s\S]*?\[\.\.\.deploymentStepsWithInstanceUpdate, \{ phase: "evaluation", label: t\("projectPreview\.steps\.createEvaluationSets"\) \}\][\s\S]*?: deploymentStepsWithInstanceUpdate/,
  );
  assert.match(
    workspaceSource,
    /task\.createEvaluationSets[\s\S]*?agentWorkspace\.deploymentSteps\.evaluation/,
  );
});

test("draws complete native radio and checkbox states after the global reset", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-network-option input\s*\{[\s\S]*?appearance:\s*none;[\s\S]*?border-radius:\s*50%/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-network-option input:checked::before\s*\{[\s\S]*?transform:\s*scale\(1\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-network-check input,\s*\.pp-evaluation-set-option input\s*\{[\s\S]*?appearance:\s*none;[\s\S]*?border-radius:\s*4px/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-network-check input:checked::before,\s*\.pp-evaluation-set-option input:checked::before\s*\{[\s\S]*?rotate\(45deg\)/,
  );
});
