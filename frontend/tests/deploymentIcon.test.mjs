import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const deployIconSource = readFileSync(
  new URL("../src/ui/DeployIcon.tsx", import.meta.url),
  "utf8",
);

test("keeps the deployment action text-only", () => {
  assert.doesNotMatch(projectPreviewSource, /DeployIcon|CloudUpload/);
  assert.match(
    projectPreviewSource,
    /deploying[\s\S]*?`\$\{deploymentActionLabel\}中…`[\s\S]*?deployError[\s\S]*?`重试\$\{deploymentActionLabel\}`[\s\S]*?: deploymentActionLabel/,
  );
});

test("draws the deployment mark as a local current-color line icon", () => {
  assert.match(deployIconSource, /export function DeployIcon/);
  assert.match(deployIconSource, /viewBox="0 0 24 24"/);
  assert.match(deployIconSource, /stroke="currentColor"/);
  assert.match(deployIconSource, /aria-hidden="true"/);
});
