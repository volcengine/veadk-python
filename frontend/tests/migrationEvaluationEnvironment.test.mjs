import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL(
        "../src/migrations/evaluationEnvironment.ts",
        import.meta.url,
      ),
    ),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const { initialEvaluationEnvironmentValues } = await import(moduleUrl);

test("prefills declared evaluation environment defaults", () => {
  assert.deepEqual(
    initialEvaluationEnvironmentValues({
      required: ["MODEL_AGENT_API_KEY"],
      optional: ["MODEL_AGENT_API_BASE", "TZ"],
      defaults: {
        MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
        TZ: "Asia/Shanghai",
      },
    }),
    {
      MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
      TZ: "Asia/Shanghai",
    },
  );
});

test("does not prefill undeclared or absent values", () => {
  assert.deepEqual(
    initialEvaluationEnvironmentValues({
      required: ["MODEL_AGENT_API_KEY"],
      optional: ["TZ"],
      defaults: {
        UNDECLARED: "ignored",
      },
    }),
    {},
  );
  assert.deepEqual(initialEvaluationEnvironmentValues(undefined), {});
});
