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
    /id="runtime-min-instance"[\s\S]*?type="number"[\s\S]*?value=\{minInstance\}/,
  );
  assert.match(
    projectPreviewSource,
    /id="runtime-max-instance"[\s\S]*?type="number"[\s\S]*?value=\{maxInstance\}/,
  );
  assert.match(
    projectPreviewSource,
    /disabled=\{deploying \|\| sidecarEnabled\}/,
  );
  assert.match(
    projectPreviewSource,
    /inMemorySession \|\| sidecarEnabled[\s\S]*?className="pp-instance-note"[\s\S]*?Harness Sidecar 首期仅支持单实例，Runtime 固定为 1～1[\s\S]*?为避免多实例间会话丢失，推荐将 Runtime 固定为 1～1/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-instance-note\s*\{[\s\S]*?color:\s*hsl\(42 96% 43%\);[\s\S]*?font-size:\s*12px/,
  );
});

test("renders the Runtime update progress step conditionally", () => {
  assert.match(
    projectPreviewSource,
    /needsInstanceUpdate[\s\S]*?\[\.\.\.baseDeploymentSteps, INSTANCE_UPDATE_STEP\][\s\S]*?: baseDeploymentSteps[\s\S]*?createEvaluationSets/,
  );
  assert.match(
    workspaceSource,
    /task\.instanceRange[\s\S]*?instanceUpdateStep\(task\.instanceRange\)[\s\S]*?: DEPLOYMENT_STEPS/,
  );
  assert.match(
    workspaceSource,
    /phase: "update"[\s\S]*?label: "更新实例配置"[\s\S]*?将 Runtime 实例数调整为 \$\{range\.min\}～\$\{range\.max\}/,
  );
});

test("renders the evaluation-set progress step only when selected", () => {
  assert.match(
    projectPreviewSource,
    /phase: "evaluation"[\s\S]*?label: "创建评测集"/,
  );
  assert.match(
    projectPreviewSource,
    /createEvaluationSets[\s\S]*?\[\.\.\.deploymentStepsWithInstanceUpdate, EVALUATION_SET_STEP\][\s\S]*?: deploymentStepsWithInstanceUpdate/,
  );
  assert.match(
    workspaceSource,
    /task\.createEvaluationSets[\s\S]*?EVALUATION_SET_STEP/,
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
