import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/migrations/deploymentEnvironment.ts", import.meta.url),
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
const { migrationDeploymentEnvDefaults } = await import(moduleUrl);

function artifact(defaults) {
  return {
    environment: {
      required: ["ARK_API_KEY", "SIGNING_PRIVATE_KEY"],
      optional: [
        "APP_HOST",
        "ENABLE_APMPLUS",
        "ENABLE_LLM_SHIELD",
        "MODEL_AGENT_API_BASE",
        "MODEL_NAME",
      ],
      defaults: {
        ARK_API_KEY: "must-not-be-used",
        SIGNING_PRIVATE_KEY: "must-not-be-used",
        APP_HOST: "0.0.0.0",
        ENABLE_APMPLUS: "true",
        ENABLE_LLM_SHIELD: "false",
        MODEL_AGENT_API_BASE: "https://wrong-provider.example/api/v3",
        MODEL_NAME: "wrong-provider-model",
        UNDECLARED: "ignored",
        ...defaults,
      },
    },
  };
}

test("fills public migration defaults while keeping secrets empty", () => {
  assert.deepEqual(migrationDeploymentEnvDefaults(artifact(), "volcengine"), {
    APP_HOST: "0.0.0.0",
    ENABLE_APMPLUS: "true",
    ENABLE_LLM_SHIELD: "false",
    MODEL_AGENT_API_BASE: "https://ark.cn-beijing.volces.com/api/v3/",
    MODEL_NAME: "doubao-seed-2-1-pro-260628",
  });
});

test("uses BytePlus model settings for a BytePlus deployment", () => {
  const values = migrationDeploymentEnvDefaults(
    artifact({ APP_HOST: "" }),
    "byteplus",
  );

  assert.equal(values.ARK_API_KEY, undefined);
  assert.equal(values.SIGNING_PRIVATE_KEY, undefined);
  assert.equal(values.APP_HOST, undefined);
  assert.equal(
    values.MODEL_AGENT_API_BASE,
    "https://ark.ap-southeast.bytepluses.com/api/v3",
  );
  assert.equal(values.MODEL_NAME, "dola-seed-2-1-turbo-260628");
});
