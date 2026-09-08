import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const errorComponentSource = readFileSync(
  new URL("../src/ui/DeploymentErrorMessage.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
test("debug errors show the complete backend detail by default", () => {
  assert.match(
    source,
    /import \{ DeploymentErrorMessage \} from "\.\.\/ui\/DeploymentErrorMessage"/,
  );
  assert.match(
    source,
    /message=\{variant\.error\}[\s\S]*?className="cw-debug-error-detail"[\s\S]*?defaultExpanded/,
  );
  assert.match(
    source,
    /message=\{message\.error\}[\s\S]*?className="cw-debug-msg-error"[\s\S]*?defaultExpanded/,
  );
  assert.match(errorComponentSource, /defaultExpanded = true/);
  assert.match(errorComponentSource, /useState\(defaultExpanded\)/);
  assert.match(errorComponentSource, /role="alert"/);
  assert.match(
    source,
    /className="cw-ab-start cw-ab-footer-start"[\s\S]*?onClick=\{\(\) => onStartVariant\(variant\.id\)\}/,
  );
});

test("creation and deployment keep friendly context and the original error", () => {
  assert.match(
    source,
    /<DeploymentErrorMessage[\s\S]*?className="cw-workspace-alert"[\s\S]*?message=\{buildErr\}/,
  );
  assert.match(
    source,
    /setBuildErr\(error instanceof Error \? error\.message : String\(error\)\)/,
  );
  assert.match(
    source,
    /className="cw-ai-error-message"[\s\S]*?\{aiErrorDialog\}/,
  );
  assert.match(
    clientSource,
    /if \(!res\.ok\) \{[\s\S]*?httpErrorMessage\(res, adkT\("client\.deploymentFailed"\)\)[\s\S]*?throw new Error\(detail\)/,
  );
  assert.match(
    clientSource,
    /if \(!final\.success\) throw new Error\(final\.error \|\| adkT\("client\.deploymentFailed"\)\)/,
  );
  assert.match(
    projectPreviewSource,
    /<DeploymentErrorMessage[\s\S]*?className="pp-error"[\s\S]*?message=\{[\s\S]*?deployError/,
  );
  assert.match(clientSource, /adkT\("common\.fallbackWithHttpStatus"/);
  assert.match(clientSource, /adkT\("client\.errorWithRawResponse"/);
  assert.match(
    projectPreviewSource,
    /label: buildStatusUnconfirmed[\s\S]*?t\("projectPreview\.task\.buildStatusUnconfirmed"\)[\s\S]*?t\("projectPreview\.task\.deploymentFailed"\)[\s\S]*?message: buildStatusUnconfirmed[\s\S]*?failedInBuild[\s\S]*?\.\.\.\(buildLog/,
  );
  assert.match(
    projectPreviewSource,
    /failedInBuild[\s\S]*?t\("projectPreview\.task\.buildFailedHint"\)[\s\S]*?failedInGithub[\s\S]*?t\("projectPreview\.task\.githubMountFailedHint"\)[\s\S]*?: message/,
  );
  assert.match(
    projectPreviewSource,
    /isBuildStatusConfirmationError[\s\S]*?RunPipeline result could not be reconciled[\s\S]*?Polling build status failed/,
  );
  assert.doesNotMatch(
    projectPreviewSource.match(
      /export function isBuildStatusConfirmationError[\s\S]*?\n}/,
    )?.[0] ?? "",
    /network error|fetch failed|Volcengine request timed out/i,
  );
  assert.match(
    projectPreviewSource,
    /buildStatusUnconfirmed[\s\S]*?BUILD_STATUS_CONFIRMATION_ERROR_MESSAGE[\s\S]*?failedInBuild/,
  );
  assert.match(
    projectPreviewSource,
    /deployError === BUILD_STATUS_CONFIRMATION_ERROR_MESSAGE[\s\S]*?undefined[\s\S]*?: requestDeploymentConfirmation/,
  );
  assert.match(
    projectPreviewSource,
    /deployError === BUILD_STATUS_CONFIRMATION_ERROR_MESSAGE[\s\S]*?t\("projectPreview\.errors\.buildStatusUnconfirmedWithDetail"/,
  );
});

test("generated-agent debug requests preserve backend error details", () => {
  assert.match(
    clientSource,
    /if \(typeof detail === "string"\) return detail/,
  );
  for (const fallbackKey of [
    "createDebugRunFailed",
    "createDebugSessionFailed",
    "loadDebugTraceFailed",
    "debugRunFailed",
    "cleanupDebugRunFailed",
  ]) {
    assert.match(
      clientSource,
      new RegExp(`new Error\\(await httpErrorMessage\\(res, adkT\\("client\\.${fallbackKey}"\\)\\)\\)`),
    );
  }
});

test("debug test runs are persisted and reclaimed after refresh", () => {
  assert.match(source, /const DEBUG_TEST_RUN_STORAGE_KEY = "veadk\.generatedAgentTestRuns"/);
  assert.match(source, /window\.sessionStorage\.getItem\(DEBUG_TEST_RUN_STORAGE_KEY\)/);
  assert.match(source, /window\.sessionStorage\.setItem\(/);
  assert.match(source, /function rememberDebugTestRun\(runId: string\)/);
  assert.match(source, /function forgetDebugTestRun\(runId: string\)/);
  assert.match(source, /async function cleanupStoredDebugRuns\(\)/);
  assert.match(
    source,
    /const activeRunIds = new Set\([\s\S]*?debugRunsRef\.current\.values\(\)[\s\S]*?run\.runId/,
  );
  assert.match(
    source,
    /await cleanupStoredDebugRuns\(\);[\s\S]*?createdRun = await createGeneratedAgentTestRun/,
  );
  assert.match(source, /rememberDebugTestRun\(createdRun\.runId\)/);
  assert.match(source, /forgetDebugTestRun\(runtime\.run\.runId\)/);
});
