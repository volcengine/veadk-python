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
    /deploying \? "部署中…" : deployError \? "重试部署" : "部署"/,
  );
});
