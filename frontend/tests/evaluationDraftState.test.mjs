import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const require = createRequire(import.meta.url);
const bundle = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/migrations/evaluationDraftState.ts", import.meta.url),
    ),
  ],
  bundle: true,
  format: "cjs",
  platform: "node",
  write: false,
});
const module = { exports: {} };
Function("require", "module", "exports", bundle.outputFiles[0].text)(
  require,
  module,
  module.exports,
);
const {
  evaluationSettingsAreLocked,
  needsEvaluationDraftHydration,
} = module.exports;

test("loads saved evaluation cases once for a task restored from polling", () => {
  assert.equal(
    needsEvaluationDraftHydration("migration-1", true, "migration-previous"),
    true,
  );
  assert.equal(
    needsEvaluationDraftHydration("migration-1", true, "migration-1"),
    false,
  );
  assert.equal(
    needsEvaluationDraftHydration("migration-1", false, ""),
    false,
  );
});

test("locks an automatic evaluation while migration runs", () => {
  assert.equal(evaluationSettingsAreLocked("analyzing", false, false), true);
  assert.equal(evaluationSettingsAreLocked("migrating", false, false), true);
  assert.equal(evaluationSettingsAreLocked("succeeded", true, false), true);
});

test("keeps incomplete dataset recovery editable", () => {
  assert.equal(
    evaluationSettingsAreLocked("awaiting_upload", false, false),
    false,
  );
  assert.equal(evaluationSettingsAreLocked("migrating", false, true), false);
});
