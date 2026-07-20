import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/create/deploymentEnv.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { firstMissingRuntimeEnv, runtimeEnvVars } = await import(moduleUrl);

test("maps active feature settings to VeADK runtime env rows", () => {
  const specs = [
    { key: "DATABASE_MYSQL_HOST", required: true },
    { key: "DATABASE_MYSQL_PASSWORD", required: true },
    { key: "DATABASE_MYSQL_PORT", required: false },
  ];
  assert.deepEqual(
    runtimeEnvVars(specs, {
      DATABASE_MYSQL_HOST: "mysql.internal",
      DATABASE_MYSQL_PASSWORD: "secret",
      DATABASE_REDIS_HOST: "stale-selection",
    }),
    [
      { key: "DATABASE_MYSQL_HOST", value: "mysql.internal" },
      { key: "DATABASE_MYSQL_PASSWORD", value: "secret" },
    ],
  );
});

test("reports the first missing required runtime setting", () => {
  const specs = [
    { key: "FEISHU_APP_ID", required: true },
    { key: "FEISHU_APP_SECRET", required: true },
  ];
  assert.equal(
    firstMissingRuntimeEnv(specs, { FEISHU_APP_ID: "cli_xxx" })?.key,
    "FEISHU_APP_SECRET",
  );
  assert.equal(
    firstMissingRuntimeEnv(specs, {
      FEISHU_APP_ID: "cli_xxx",
      FEISHU_APP_SECRET: "secret",
    }),
    undefined,
  );
});
