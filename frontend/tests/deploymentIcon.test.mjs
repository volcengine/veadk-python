import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);

test("omits the standalone deployment action", () => {
  assert.doesNotMatch(projectPreviewSource, /DeployIcon|CloudUpload|RotateCcw/);
  assert.doesNotMatch(projectPreviewSource, /deploymentActionLabel|pp-config-actions|pp-deploy studio-update-action/);
});
