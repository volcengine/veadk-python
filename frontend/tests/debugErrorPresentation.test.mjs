import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);

test("debug errors support full expansion, copying, and retry", () => {
  assert.match(
    source,
    /import \{ DeploymentErrorMessage \} from "\.\.\/ui\/DeploymentErrorMessage"/,
  );
  assert.match(source, /className="cw-debug-error-detail"/);
  assert.match(source, /className="cw-debug-msg-error"/);
  assert.match(source, /onRetry=\{async \(\) =>/);
});
