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
  firstInvalidRuntimeEnv,
  firstMissingRuntimeEnv,
  runtimeEnvConfiguration,
  runtimeEnvDisplayRows,
  runtimeEnvJsonError,
  runtimeEnvVars,
} = await loadTypeScriptModule("../src/create/deploymentEnv.ts");
const {
  A2A_REGISTRY_DEFAULTS,
  A2A_REGISTRY_ENV,
  BUILTIN_TOOLS,
  DEFAULT_KB_BACKEND,
  KB_BACKENDS,
  LTM_BACKENDS,
  MODEL_ENV,
  STM_BACKENDS,
  TRACING_EXPORTERS,
} = await loadTypeScriptModule("../src/create/veadkCatalog.ts");
const { localPickerMatches } = await loadTypeScriptModule(
  "../src/create/localPickerSearch.ts",
);
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
const openvikingConsoleUrl = "https://console.volcengine.com/vikingdb/openviking";
const openvikingSessionsDocUrl =
  "https://github.com/volcengine/OpenViking/blob/main/docs/zh/api/05-sessions.md";
const codeBrowserSource = readFileSync(
  new URL("../src/ui/CodeBrowserDialog.tsx", import.meta.url),
  "utf8",
);
const codeBrowserStyles = readFileSync(
  new URL("../src/ui/CodeBrowserDialog.css", import.meta.url),
  "utf8",
);
const vikingKnowledgebasesSource = readFileSync(
  new URL("../src/create/vikingKnowledgebases.ts", import.meta.url),
  "utf8",
);

test("defaults knowledgebase creation to VikingDB collections", () => {
  assert.equal(DEFAULT_KB_BACKEND, "viking");
  assert.equal(KB_BACKENDS[0].id, "viking");
  assert.notEqual(KB_BACKENDS.findIndex((item) => item.id === "viking"), -1);
  assert.match(customCreateSource, /<VikingKnowledgebaseSelect/);
  assert.match(vikingKnowledgebasesSource, /\/web\/viking-knowledgebases/);
});

test("filters A2A spaces and Viking knowledgebases locally by name or id", () => {
  assert.equal(localPickerMatches("客服", ["客服中心", "space-123"]), true);
  assert.equal(localPickerMatches("SPACE-123", ["客服中心", "space-123"]), true);
  assert.equal(localPickerMatches("missing", ["客服中心", "space-123"]), false);
  assert.match(customCreateSource, /filteredSpaces = useMemo/);
  assert.match(customCreateSource, /filteredItems = useMemo/);
  assert.match(customCreateSource, /搜索 AgentKit 智能体中心/);
  assert.match(customCreateSource, /搜索 VikingDB 知识库/);
});

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

test("keeps runtime env comments on deployment summary rows", () => {
  const rows = runtimeEnvDisplayRows(
    [
      {
        key: "DATABASE_OPENVIKING_USER_ID",
        required: false,
        comment:
          "OpenViking 记忆归属用户 / 场景 ID，对应 URI viking://user/<此值>/peers/<请求用户>/memories 中的 user 段",
      },
    ],
    {},
  );

  assert.equal(
    rows[0].comment,
    "OpenViking 记忆归属用户 / 场景 ID，对应 URI viking://user/<此值>/peers/<请求用户>/memories 中的 user 段",
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
  assert.equal(
    firstMissingRuntimeEnv(
      [
        {
          key: "DATABASE_OPENVIKING_URL",
          required: true,
          defaultValue: "https://default",
        },
      ],
      { DATABASE_OPENVIKING_URL: "" },
    )?.key,
    "DATABASE_OPENVIKING_URL",
  );
});

test("uses copyable default runtime values and validates JSON settings", () => {
  const specs = [
    {
      key: "DATABASE_OPENVIKING_URL",
      required: true,
      defaultValue: "https://default-openviking",
    },
    {
      key: "DATABASE_OPENVIKING_MEMORY_POLICY",
      required: false,
      defaultValue: '{"peer":{"enabled":true}}',
      format: "json",
    },
  ];

  assert.deepEqual(runtimeEnvDisplayRows(specs, {}), [
    {
      key: "DATABASE_OPENVIKING_URL",
      required: true,
      defaultValue: "https://default-openviking",
      value: "https://default-openviking",
    },
    {
      key: "DATABASE_OPENVIKING_MEMORY_POLICY",
      required: false,
      defaultValue: '{"peer":{"enabled":true}}',
      format: "json",
      value: '{"peer":{"enabled":true}}',
    },
  ]);
  assert.deepEqual(runtimeEnvVars(specs, {}), [
    { key: "DATABASE_OPENVIKING_URL", value: "https://default-openviking" },
    {
      key: "DATABASE_OPENVIKING_MEMORY_POLICY",
      value: '{"peer":{"enabled":true}}',
    },
  ]);
  assert.equal(runtimeEnvJsonError(specs[1], {}), undefined);
  assert.equal(
    runtimeEnvJsonError(specs[1], {
      DATABASE_OPENVIKING_MEMORY_POLICY: "{bad-json",
    }),
    "JSON 格式不正确",
  );
  assert.deepEqual(
    firstInvalidRuntimeEnv(specs, {
      DATABASE_OPENVIKING_MEMORY_POLICY: "{bad-json",
    }),
    { spec: specs[1], error: "JSON 格式不正确" },
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

test("declares the Mem0 runtime configuration and database dependency", () => {
  const mem0 = LTM_BACKENDS.find((option) => option.id === "mem0");

  assert.ok(mem0);
  assert.equal(mem0.pipExtra, "database");
  assert.deepEqual(
    mem0.env.map((env) => env.key),
    ["DATABASE_MEM0_API_KEY", "DATABASE_MEM0_BASE_URL"],
  );
});

test("declares the OpenViking long-term memory runtime configuration", () => {
  const openviking = LTM_BACKENDS.find((option) => option.id === "openviking");

  assert.ok(openviking);
  assert.equal(openviking.label, "OpenViking Memory");
  const openvikingUrl = openviking.env.find(
    (env) => env.key === "DATABASE_OPENVIKING_URL",
  );
  const openvikingApiKey = openviking.env.find(
    (env) => env.key === "DATABASE_OPENVIKING_API_KEY",
  );
  const openvikingPolicy = openviking.env.find(
    (env) => env.key === "DATABASE_OPENVIKING_MEMORY_POLICY",
  );
  assert.deepEqual(
    openviking.env.map((env) => [env.key, env.required, env.placeholder ?? ""]),
    [
      [
        "DATABASE_OPENVIKING_URL",
        true,
        "https://api.vikingdb.cn-beijing.volces.com/openviking",
      ],
      ["DATABASE_OPENVIKING_API_KEY", true, ""],
      ["DATABASE_OPENVIKING_USER_ID", false, "default"],
      [
        "DATABASE_OPENVIKING_MEMORY_POLICY",
        false,
        '{\n  "self": {"enabled": true},\n  "peer": {"enabled": true},\n  "working_memory": {"enabled": true},\n  "memory_types": null\n}',
      ],
    ],
  );
  assert.equal(openvikingUrl?.defaultValue, undefined);
  assert.equal(
    firstMissingRuntimeEnv(openviking.env, {
      DATABASE_OPENVIKING_API_KEY: "test-api-key",
    })?.key,
    "DATABASE_OPENVIKING_URL",
  );
  assert.equal(openvikingPolicy?.defaultValue, undefined);
  assert.deepEqual(
    runtimeEnvVars(openviking.env, {
      DATABASE_OPENVIKING_URL: "https://openviking.local",
      DATABASE_OPENVIKING_API_KEY: "test-api-key",
    }),
    [
      {
        key: "DATABASE_OPENVIKING_URL",
        value: "https://openviking.local",
      },
      { key: "DATABASE_OPENVIKING_API_KEY", value: "test-api-key" },
    ],
  );
  assert.equal(openvikingPolicy?.comment, "记忆策略");
  assert.equal(openvikingPolicy?.multiline, true);
  assert.equal(openvikingPolicy?.format, "json");
  assert.match(
    openviking.env.find((env) => env.key === "DATABASE_OPENVIKING_USER_ID")
      ?.help ?? "",
    /viking:\/\/user\/<此值>\/peers\/<请求用户>\/memories/,
  );
  assert.equal(
    openvikingPolicy?.help,
    "记忆的抽取策略和隔离策略,不填写时使用官方默认策略。",
  );
  assert.equal(openvikingUrl?.link?.url, openvikingConsoleUrl);
  assert.equal(openvikingApiKey?.link?.url, openvikingConsoleUrl);
  assert.equal(openvikingPolicy?.link?.url, openvikingSessionsDocUrl);
  assert.match(customCreateSource, /className="cw-input cw-env-textarea"/);
  assert.match(customCreateSource, /runtimeEnvJsonError\(item, values\)/);
  assert.match(customCreateSource, /firstInvalidRuntimeEnv\(/);
  assert.match(projectPreviewSource, /className="pp-env-value pp-env-json-value"/);
  assert.match(projectPreviewSource, /runtimeEnvJsonError\(\s*row,/);
  assert.match(projectPreviewSource, /firstInvalidRuntimeEnv\(/);
  assert.match(customCreateSource, /className="cw-env-help"/);
  assert.match(customCreateSource, /className="cw-env-link"/);
  assert.match(customCreateSource, /title=\{`打开 OpenViking \$\{item\.link\.label\}`\}/);
  assert.match(customCreateSource, /data-help=\{item\.help\}/);
  assert.match(customCreateSource, /className="cw-env-help-popover"/);
  assert.match(projectPreviewSource, /className="pp-env-help"/);
  assert.match(projectPreviewSource, /className="pp-env-link"/);
  assert.match(projectPreviewSource, /title=\{`打开 OpenViking \$\{row\.link\.label\}`\}/);
  assert.match(projectPreviewSource, /data-help=\{row\.help \|\| row\.comment\}/);
  assert.match(projectPreviewSource, /className="pp-env-help-popover"/);
  assert.match(projectPreviewStyles, /\.pp-env-key-cell\s*\{/);
  assert.match(projectPreviewStyles, /\.pp-env-help\s*\{/);
  assert.match(projectPreviewStyles, /\.pp-env-link\s*\{/);
  assert.match(projectPreviewStyles, /cursor:\s*default;/);
  assert.match(projectPreviewStyles, /\.pp-env-help-popover\s*\{[\s\S]*?user-select:\s*text;/);
  assert.match(projectPreviewStyles, /\.pp-env-help:hover \.pp-env-help-popover/);
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

test("keeps the generated project stable when only deployment channel settings change", () => {
  assert.match(
    customCreateSource,
    /onFeishuEnabledChange=\{\(feishuEnabled\) => \{[\s\S]*?setDraft\(nextDraft\);/,
  );
  assert.doesNotMatch(customCreateSource, /buildPreviewProject/);
  assert.match(
    customCreateSource,
    /generateAgentProject\(codegenDraft\(releaseDraft\)\)/,
  );
  assert.match(projectPreviewSource, /await onFeishuEnabledChange\(!feishuEnabled\)/);
  assert.match(projectPreviewSource, /deploying \|\| feishuUpdating/);
});

test("uses concise placeholders for agent names and custom environment variables", () => {
  assert.match(customCreateSource, /placeholder="assistant"/);
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
  assert.match(
    customCreateSource,
    /selections\.push\(\{ env: providerRuntimeEnv\(tool\.env, cloudProvider\) \}\)/,
  );
});

test("materializes A2A registry defaults for deployment env", () => {
  assert.equal(
    A2A_REGISTRY_ENV.find((item) => item.key === "REGISTRY_SPACE_ID")
      ?.placeholder,
    "请选择智能体中心",
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

test("summarizes the Agent above the deployment configuration", () => {
  assert.match(customCreateSource, /agentDraft=\{draft\}/);
  assert.match(projectPreviewSource, /className="pp-flow-thumbnail"/);
  assert.match(projectPreviewSource, /<AgentBuildCanvas[\s\S]*?readOnly/);
  assert.match(projectPreviewSource, /Agent 数量/);
  assert.match(projectPreviewSource, />\s*导出 YAML\s*</);
  assert.match(projectPreviewSource, /<ProjectCodeBrowser[\s\S]*?pp-artifact-source/);
  assert.match(projectPreviewSource, />\s*下载源代码\s*</);
  assert.match(
    projectPreviewStyles,
    /grid-template-rows:\s*auto auto/,
  );
  assert.match(projectPreviewStyles, /\.pp-release-preview\s*\{[\s\S]*?box-sizing:\s*border-box/);
});

test("keeps artifact actions beside the embedded publish canvas", () => {
  assert.match(
    projectPreviewSource,
    /className={`pp-release-preview\$\{embedded \? " is-embedded" : ""\}`}/,
  );
  assert.match(projectPreviewSource, /\{embedded && artifactActions\}/);
  assert.match(projectPreviewSource, />\s*导出 YAML\s*</);
  assert.match(projectPreviewSource, /label="查看源代码"/);
  assert.match(projectPreviewSource, />\s*下载源代码\s*</);
  assert.match(
    projectPreviewStyles,
    /\.pp-release-preview\.is-embedded\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\) 132px/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-artifact-actions\.is-rail\s*\{[\s\S]*?flex-direction:\s*column/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-artifact-actions\.is-rail \.pp-secondary,[\s\S]*?flex:\s*1 1 0;[\s\S]*?justify-content:\s*center/,
  );
});

test("enlarges the read-only execution canvas without topology configuration", () => {
  assert.match(
    projectPreviewSource,
    /className="pp-flow-dialog"[\s\S]*?interactivePreview/,
  );
  assert.match(projectPreviewSource, /只读预览，可缩放与拖动画布/);
  assert.doesNotMatch(projectPreviewSource, /pp-topology-pane|inspectedAgent/);
});

test("uses an unboxed source trigger", () => {
  assert.match(codeBrowserSource, /<span>\{label\}<\/span>/);
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
