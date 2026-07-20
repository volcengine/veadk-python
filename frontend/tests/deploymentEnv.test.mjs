import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

async function loadTypeScriptModule(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  return import(moduleUrl);
}

const {
  firstMissingRuntimeEnv,
  runtimeEnvConfiguration,
  runtimeEnvDisplayRows,
  runtimeEnvVars,
} = await loadTypeScriptModule("../src/create/deploymentEnv.ts");
const {
  KB_BACKENDS,
  LTM_BACKENDS,
  STM_BACKENDS,
  TRACING_EXPORTERS,
} = await loadTypeScriptModule("../src/create/veadkCatalog.ts");
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);

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

test("collects every component parameter and enables selected tracing exporters", () => {
  const backendSelections = [
    ...STM_BACKENDS,
    ...LTM_BACKENDS,
    ...KB_BACKENDS,
  ].map((option) => ({ env: option.env }));
  const exporterSelections = TRACING_EXPORTERS.map((option) => ({
    env: option.env,
    enableFlag: option.enableFlag,
  }));

  const config = runtimeEnvConfiguration([
    ...backendSelections,
    ...exporterSelections,
  ]);
  const expectedKeys = new Set(
    [...backendSelections, ...exporterSelections].flatMap((selection) => [
      ...selection.env.map((env) => env.key),
      ...(selection.enableFlag ? [selection.enableFlag] : []),
    ]),
  );

  assert.deepEqual(new Set(config.specs.map((spec) => spec.key)), expectedKeys);
  for (const exporter of TRACING_EXPORTERS) {
    assert.equal(config.fixedValues[exporter.enableFlag], "true");
  }
});

test("shows configured database and Feishu values in the runtime env summary", () => {
  const rows = runtimeEnvDisplayRows(
    [
      { key: "DATABASE_POSTGRESQL_HOST", required: true },
      { key: "DATABASE_POSTGRESQL_PASSWORD", required: true },
      { key: "FEISHU_APP_ID", required: true },
      { key: "FEISHU_APP_SECRET", required: true },
    ],
    {
      DATABASE_POSTGRESQL_HOST: "postgres.internal",
      DATABASE_POSTGRESQL_PASSWORD: "database-secret",
      FEISHU_APP_ID: "cli_example",
      FEISHU_APP_SECRET: "feishu-secret",
    },
  );

  assert.deepEqual(rows, [
    {
      key: "DATABASE_POSTGRESQL_HOST",
      value: "postgres.internal",
      required: true,
    },
    {
      key: "DATABASE_POSTGRESQL_PASSWORD",
      value: "database-secret",
      required: true,
    },
    { key: "FEISHU_APP_ID", value: "cli_example", required: true },
    { key: "FEISHU_APP_SECRET", value: "feishu-secret", required: true },
  ]);
});

test("regenerates project code when Feishu changes on the deployment page", () => {
  assert.match(
    customCreateSource,
    /const nextProject = await generateAgentProject\(codegenDraft\(nextDraft\)\)/,
  );
  assert.match(customCreateSource, /setProject\(nextProject\)/);
  assert.match(projectPreviewSource, /await onFeishuEnabledChange\(!feishuEnabled\)/);
  assert.match(projectPreviewSource, /deploying \|\| feishuUpdating/);
});
