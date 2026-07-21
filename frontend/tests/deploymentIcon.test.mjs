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

test("uses the custom deployment mark only for the idle deploy action", () => {
  assert.match(projectPreviewSource, /import \{ DeployIcon \} from "\.\/DeployIcon"/);
  assert.doesNotMatch(projectPreviewSource, /CloudUpload/);
  assert.match(
    projectPreviewSource,
    /deploying \? \([\s\S]*?<Loader2[\s\S]*?deployError \? \([\s\S]*?<RotateCcw[\s\S]*?<DeployIcon className="pp-ic" \/>/,
  );
});

test("draws the deployment mark as a local current-color line icon", () => {
  assert.match(deployIconSource, /export function DeployIcon/);
  assert.match(deployIconSource, /viewBox="0 0 24 24"/);
  assert.match(deployIconSource, /stroke="currentColor"/);
  assert.match(deployIconSource, /aria-hidden="true"/);
});
