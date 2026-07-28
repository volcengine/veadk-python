import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);

test("keeps the deployment action text-only", () => {
  assert.doesNotMatch(projectPreviewSource, /DeployIcon|CloudUpload|RotateCcw/);
  assert.match(
    projectPreviewSource,
    /deploying[\s\S]*?`\$\{deploymentActionLabel\}中…`[\s\S]*?deployError[\s\S]*?`重试\$\{deploymentActionLabel\}`[\s\S]*?: deploymentActionLabel/,
  );
});
