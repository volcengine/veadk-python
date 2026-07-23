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
  A2A_REGISTRY_DEFAULTS,
  A2A_REGISTRY_ENV,
  BUILTIN_TOOLS,
  KB_BACKENDS,
  LTM_BACKENDS,
  MODEL_ENV,
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
const projectPreviewStyles = readFileSync(
  new URL("../src/ui/ProjectPreview.css", import.meta.url),
  "utf8",
);
const codeBrowserSource = readFileSync(
  new URL("../src/ui/CodeBrowserDialog.tsx", import.meta.url),
  "utf8",
);
const codeBrowserStyles = readFileSync(
  new URL("../src/ui/CodeBrowserDialog.css", import.meta.url),
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

test("does not request auto-resolved credentials per component", () => {
  const envKeys = [
    ...BUILTIN_TOOLS,
    ...STM_BACKENDS,
    ...LTM_BACKENDS,
    ...KB_BACKENDS,
    ...TRACING_EXPORTERS,
  ].flatMap((option) => option.env.map((env) => env.key));

  const autoResolvedCredentials = [
    "MODEL_AGENT_API_KEY",
    "MODEL_EMBEDDING_API_KEY",
    "MODEL_IMAGE_API_KEY",
    "MODEL_EDIT_API_KEY",
    "MODEL_VIDEO_API_KEY",
    "TOOL_VESPEECH_API_KEY",
    "TOOL_VESEARCH_API_KEY",
    "VOLCENGINE_ACCESS_KEY",
    "VOLCENGINE_SECRET_KEY",
    "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY",
  ];

  for (const key of autoResolvedCredentials) {
    assert.equal(envKeys.includes(key), false, key);
  }
  assert.equal(MODEL_ENV.some((env) => env.key === "MODEL_AGENT_API_KEY"), false);
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

test("uses concise placeholders for agent names and custom environment variables", () => {
  assert.match(customCreateSource, /placeholder="customer_service"/);
  assert.doesNotMatch(customCreateSource, /placeholder="例如：customer_service"/);
  assert.match(projectPreviewSource, /placeholder="名称"/);
  assert.match(projectPreviewSource, /placeholder="值"/);
  assert.doesNotMatch(projectPreviewSource, /placeholder="(?:KEY|VALUE)"/);
});

test("collects non-automatic built-in tool settings for deployment", () => {
  assert.match(
    customCreateSource,
    /for \(const toolId of node\.builtinTools \?\? \[\]\)/,
  );
  assert.match(
    customCreateSource,
    /BUILTIN_TOOLS\.find\(\(item\) => item\.id === toolId\)/,
  );
  assert.match(customCreateSource, /selections\.push\(\{ env: tool\.env \}\)/);
});

test("materializes A2A registry defaults for deployment env", () => {
  assert.equal(
    A2A_REGISTRY_ENV.find((item) => item.key === "REGISTRY_SPACE_ID")
      ?.placeholder,
    "请输入智能体中心 ID，如 as-yer579143kbrkemozdn6",
  );
  assert.deepEqual(
    runtimeEnvVars(A2A_REGISTRY_ENV, {
      REGISTRY_SPACE_ID: "space-test",
      REGISTRY_TOP_K: A2A_REGISTRY_DEFAULTS.topK,
      REGISTRY_REGION: A2A_REGISTRY_DEFAULTS.region,
      REGISTRY_ENDPOINT: A2A_REGISTRY_DEFAULTS.endpoint,
    }),
    [
      { key: "REGISTRY_SPACE_ID", value: "space-test" },
      { key: "REGISTRY_TOP_K", value: "3" },
      { key: "REGISTRY_REGION", value: "cn-beijing" },
      {
        key: "REGISTRY_ENDPOINT",
        value: "https://open.volcengineapi.com/",
      },
    ],
  );
  assert.match(
    customCreateSource,
    /a2aRegistryEnvValues\(node\.a2aRegistry, \{ includeDefaults: true \}\)/,
  );
  assert.match(
    customCreateSource,
    /fixedValues:\s*\{ \.\.\.config\.fixedValues, \.\.\.fixedValues \}/,
  );
  assert.match(
    customCreateSource,
    /deploymentEnvValues=\{\{[\s\S]*?\.\.\.draft\.deployment\?\.envValues,[\s\S]*?\.\.\.deploymentEnv\.fixedValues,/,
  );
});

test("keeps deployment configuration primary beside an inspectable Agent topology", () => {
  assert.match(customCreateSource, /agentDraft=\{draft\}/);
  assert.match(projectPreviewSource, /className="pp-topology-pane"/);
  assert.match(projectPreviewSource, /onMouseEnter=\{\(\) => onHover\(agent\.id\)\}/);
  assert.match(projectPreviewSource, /onMouseLeave=\{\(\) => onHover\(null\)\}/);
  assert.match(projectPreviewSource, /onBlur=\{\(\) => onFocus\(null\)\}/);
  assert.match(projectPreviewSource, /<ProjectCodeBrowser project=\{project\}/);
  assert.match(projectPreviewSource, />\s*导出配置\s*</);
  assert.match(projectPreviewSource, />\s*下载源码\s*</);
  assert.match(
    projectPreviewStyles,
    /grid-template-columns:\s*minmax\(260px, 3fr\) minmax\(520px, 7fr\)/,
  );
});

test("shows concrete Agent configuration only while a topology node is inspected", () => {
  assert.match(
    projectPreviewSource,
    /\{inspectedAgent && inspectedAgentMeta && InspectedAgentIcon && \(/,
  );
  for (const label of [
    "模型",
    "工具",
    "技能",
    "知识库",
    "短期记忆",
    "长期记忆",
    "观测",
  ]) {
    assert.match(projectPreviewSource, new RegExp(`<dt>${label}</dt>`));
  }
  assert.doesNotMatch(projectPreviewSource, /<dt>组件<\/dt>/);
  assert.match(projectPreviewSource, /findTool\(toolId\)\?\.label/);
  assert.match(projectPreviewSource, /findKb\(node\.knowledgebaseBackend/);
  assert.match(projectPreviewSource, /findExporter\(exporterId\)\?\.label/);
});

test("uses an unboxed 查看源码 trigger", () => {
  assert.match(codeBrowserSource, /<span>查看源码<\/span>/);
  assert.match(
    codeBrowserStyles,
    /\.code-browser-trigger\s*\{[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;/,
  );
  assert.match(codeBrowserStyles, /\.code-browser-trigger:focus-visible/);
});

test("opens generated source in an editable code browser dialog", () => {
  assert.match(codeBrowserSource, /role="dialog"[\s\S]*?aria-modal="true"/);
  assert.match(codeBrowserSource, /<CodeEditor[\s\S]*?onChange=\{handleEdit\}/);
  assert.match(codeBrowserSource, /event\.key === "Escape"/);
  assert.match(codeBrowserSource, /document\.body\.style\.overflow = "hidden"/);
  assert.match(
    codeBrowserStyles,
    /\.code-browser-dialog\s*\{[\s\S]*?height:\s*min\(720px, 84vh\);/,
  );
});
