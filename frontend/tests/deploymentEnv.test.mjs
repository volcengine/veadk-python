import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
  return import(moduleUrl);
}

const {
  firstInvalidRuntimeEnv,
  firstMissingRuntimeEnv,
  missingRuntimeEnvs,
  runtimeEnvConfiguration,
  runtimeEnvDisplayRows,
  runtimeEnvJsonError,
  runtimeEnvMissingError,
  runtimeEnvRequirementHint,
  runtimeEnvVars,
} = await loadTypeScriptModule("../src/create/deploymentEnv.ts");
const {
  customModelCredentialRequirements,
  isProviderModelApiBase,
} = await loadTypeScriptModule("../src/create/customModelCredentials.ts");
const {
  A2A_REGISTRY_DEFAULTS,
  A2A_REGISTRY_ENV,
  a2aRegistryDefaults,
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
const vikingMemoriesSource = readFileSync(
  new URL("../src/create/vikingMemories.ts", import.meta.url),
  "utf8",
);

test("recognizes only the selected cloud's exact official model endpoint", () => {
  assert.equal(
    isProviderModelApiBase(
      "https://ark.cn-beijing.volces.com/api/v3/",
      "https://ark.cn-beijing.volces.com/api/v3/",
    ),
    true,
  );
  assert.equal(
    isProviderModelApiBase(
      "https://ark.ap-southeast.bytepluses.com/api/v3",
      "https://ark.ap-southeast.bytepluses.com/api/v3",
    ),
    true,
  );
  assert.equal(
    isProviderModelApiBase(
      "https://ark.ap-southeast.bytepluses.com/api/v3",
      "https://ark.cn-beijing.volces.com/api/v3/",
    ),
    false,
  );
  assert.equal(
    isProviderModelApiBase(
      "https://ark.cn-beijing.volces.com/api/v3?target=custom",
      "https://ark.cn-beijing.volces.com/api/v3/",
    ),
    false,
  );
});

test("derives distinct transient credential names for custom model agents", () => {
  const draft = {
    name: "Agent",
    agentType: "llm",
    modelApiBase: "https://models.example.com/v1",
    subAgents: [
      {
        name: "Agent",
        agentType: "llm",
        modelApiBase: "https://other-models.example.com/v1",
        subAgents: [],
      },
    ],
  };
  assert.deepEqual(
    customModelCredentialRequirements(
      draft,
      "https://ark.cn-beijing.volces.com/api/v3/",
    ),
    [
      { key: "CUSTOM_MODEL_AGENT_API_KEY", label: "Agent model API Key" },
      { key: "CUSTOM_MODEL_AGENT_API_KEY_2", label: "Agent model API Key" },
    ],
  );
});

test("does not request custom credentials for Ark-backed agents", () => {
  assert.deepEqual(
    customModelCredentialRequirements(
      {
        name: "Ark Agent",
        agentType: "llm",
        modelSource: "ark",
        modelApiBase: "https://models.example.com/v1",
        subAgents: [],
      },
      "https://ark.cn-beijing.volces.com/api/v3/",
    ),
    [],
  );
});

test("keeps custom model credentials transient on the publish page", () => {
  assert.match(
    customCreateSource,
    /requiredSecretEnv=\{customModelCredentials\}/,
  );
  assert.match(
    projectPreviewSource,
    /const \[secretEnvValues, setSecretEnvValues\]/,
  );
  assert.match(
    projectPreviewSource,
    /requiredSecretEnv\.map[\s\S]*?type="password"[\s\S]*?projectPreview\.releaseOnlySecret/,
  );
  assert.match(projectPreviewSource, /role="alert"/);
  assert.doesNotMatch(customCreateSource, /envValues:\s*customModelCredentials/);
});

test("shows the selected ModelArk API key as a server-managed read-only value", () => {
  assert.match(
    customCreateSource,
    /MODEL_AGENT_API_KEY[\s\S]*?secret:\s*true[\s\S]*?readOnly:\s*true[\s\S]*?serverManaged:\s*true/,
  );
  assert.match(
    projectPreviewSource,
    /serverManagedModelApiKey\s*\? "text"\s*:\s*row\.secret\s*\? "password"/,
  );
  assert.match(projectPreviewSource, /const fixed =\s*row\.readOnly/);
  assert.doesNotMatch(customCreateSource, /arkModelApiKeyEnvValues/);
});

test("server-managed secrets are displayed but excluded from browser deploy payloads", () => {
  const specs = [
    {
      key: "MODEL_AGENT_API_KEY",
      required: true,
      placeholder: "由所选 API Key 注入",
      secret: true,
      readOnly: true,
      serverManaged: true,
    },
  ];
  assert.deepEqual(runtimeEnvDisplayRows(specs, {}), [
    { ...specs[0], value: "由所选 API Key 注入" },
  ]);
  assert.deepEqual(
    runtimeEnvDisplayRows(specs, {
      MODEL_AGENT_API_KEY: "legacy-value-must-not-reach-the-browser",
    }),
    [{ ...specs[0], value: "由所选 API Key 注入" }],
  );
  assert.deepEqual(runtimeEnvVars(specs, {}), []);
  assert.equal(firstMissingRuntimeEnv(specs, {}), undefined);
});

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
  assert.match(customCreateSource, /traditional\.resources\.searchAgentKitCenter/);
  assert.match(customCreateSource, /traditional\.resources\.searchKnowledgeBase/);
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

test("keeps hidden runtime env values out of user-facing rows", () => {
  const specs = [
    {
      key: "DATABASE_VIKINGMEM_PROJECT",
      required: false,
      placeholder: "default",
      hidden: true,
    },
    { key: "DATABASE_REDIS_HOST", required: true },
  ];

  assert.deepEqual(runtimeEnvDisplayRows(specs, {}), [
    { key: "DATABASE_REDIS_HOST", required: true, value: "" },
  ]);
  assert.deepEqual(
    runtimeEnvVars(specs, {
      DATABASE_VIKINGMEM_PROJECT: "agent-project",
      DATABASE_REDIS_HOST: "redis.local",
    }),
    [
      { key: "DATABASE_VIKINGMEM_PROJECT", value: "agent-project" },
      { key: "DATABASE_REDIS_HOST", value: "redis.local" },
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

test("explains optimization dependencies and reports every missing runtime setting", () => {
  const specs = [
    {
      key: "MODEL_AGENT_API_KEY",
      required: true,
      serverManaged: true,
      requiredBy: ["上下文治理", "回答校验与修复"],
    },
    {
      key: "MCP_URLS",
      required: true,
      requiredBy: ["MCP 稳定性治理"],
    },
    {
      key: "MCP_API_KEY",
      required: true,
      requiredBy: ["MCP 稳定性治理"],
    },
  ];

  assert.equal(
    runtimeEnvRequirementHint(specs[0]),
    "Required by the following optimizations: 上下文治理, 回答校验与修复.",
  );
  assert.equal(
    runtimeEnvMissingError(specs[1]),
    "Required by the following optimizations: MCP 稳定性治理. Enter MCP_URLS.",
  );
  assert.deepEqual(
    missingRuntimeEnvs(specs, {}).map((spec) => spec.key),
    ["MCP_URLS", "MCP_API_KEY"],
  );
  assert.deepEqual(
    missingRuntimeEnvs(specs, {
      MCP_URLS: "https://mcp.example.test/mcp",
      MCP_API_KEY: "test-key",
    }),
    [],
  );

  const derivedSpec = {
    key: "MCP_URLS",
    required: true,
    readOnly: true,
    requiredBy: ["MCP 稳定性治理"],
    help: "由已添加的 HTTP MCP 工具自动注入。",
    missingError: "请返回“添加 MCP 工具”补充配置。",
  };
  assert.equal(
    runtimeEnvRequirementHint(derivedSpec),
    "Required by the following optimizations: MCP 稳定性治理. 由已添加的 HTTP MCP 工具自动注入。",
  );
  assert.equal(
    runtimeEnvMissingError(derivedSpec),
    "请返回“添加 MCP 工具”补充配置。",
  );
});

test("marks missing optimization env inputs invalid and focuses the first error", () => {
  assert.match(
    customCreateSource,
    /requiredBy:\s*modelProxyHarnessOptimizationLabels/,
  );
  assert.match(customCreateSource, /resolveMcpGatewayEnv\(/);
  assert.doesNotMatch(customCreateSource, /key: "MCP_URLS"/);
  assert.doesNotMatch(customCreateSource, /key: "MCP_API_KEY"/);
  assert.match(customCreateSource, /const mcpGatewayManaged =/);
  assert.match(
    customCreateSource,
    /key: mcpTool\.authTokenEnv,[\s\S]*?serverManaged: mcpGatewayManaged,[\s\S]*?hidden: mcpGatewayManaged/,
  );
  assert.match(
    customCreateSource,
    /deploymentTarget \|\| mcpGatewayManaged \? codegenDraft\(draft\) : undefined/,
  );
  assert.match(customCreateSource, /mcpSecretValues:/);
  assert.match(projectPreviewSource, /missingRuntimeEnvs\(/);
  assert.match(projectPreviewSource, /row\.placeholder \|\|/);
  assert.match(projectPreviewSource, /setDeploymentEnvErrors\(/);
  assert.match(projectPreviewSource, /focusDeploymentEnv\(/);
  assert.match(
    projectPreviewSource,
    /aria-invalid=\{Boolean\(fieldError \|\| jsonError\)\}/,
  );
  assert.match(
    projectPreviewSource,
    /className="pp-env-error"[\s\S]*?role="alert"[\s\S]*?\{fieldError\}/,
  );
});

test("omits Studio-managed MCP values from fields, validation, and public env payload", () => {
  const specs = [
    {
      key: "MCP_TEST_TOOL_AUTH_TOKEN",
      required: false,
      secret: true,
      readOnly: true,
      serverManaged: true,
      hidden: true,
    },
    {
      key: "MCP_SERVERS_JSON",
      required: true,
      secret: true,
      readOnly: true,
      serverManaged: true,
      hidden: true,
    },
  ];
  const values = {
    MCP_TEST_TOOL_AUTH_TOKEN: "transient-test-value",
  };

  assert.deepEqual(runtimeEnvDisplayRows(specs, values), []);
  assert.deepEqual(missingRuntimeEnvs(specs, values), []);
  assert.deepEqual(runtimeEnvVars(specs, values), []);
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
    "Invalid JSON format",
  );
  assert.deepEqual(
    firstInvalidRuntimeEnv(specs, {
      DATABASE_OPENVIKING_MEMORY_POLICY: "{bad-json",
    }),
    { spec: specs[1], error: "Invalid JSON format" },
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

test("declares the VikingDB long-term memory runtime configuration", () => {
  const viking = LTM_BACKENDS.find((option) => option.id === "viking");

  assert.ok(viking);
  assert.equal(viking.label, "VikingDB Memory");
  assert.deepEqual(
    viking.env.map((env) => [
      env.key,
      env.required,
      env.placeholder ?? "",
      env.hidden,
    ]),
    [
      ["DATABASE_VIKINGMEM_PROJECT", false, "default", true],
      ["DATABASE_VIKING_REGION", false, "", true],
      [
        "DATABASE_VIKINGMEM_MEMORY_TYPE",
        false,
        "sys_event_v1,sys_profile_v1",
        true,
      ],
    ],
  );
  assert.deepEqual(runtimeEnvDisplayRows(viking.env, {}), []);
  assert.deepEqual(
    runtimeEnvVars(viking.env, {
      DATABASE_VIKINGMEM_PROJECT: "agent-project",
      DATABASE_VIKING_REGION: "cn-beijing",
    }),
    [
      { key: "DATABASE_VIKINGMEM_PROJECT", value: "agent-project" },
      { key: "DATABASE_VIKING_REGION", value: "cn-beijing" },
    ],
  );
  assert.match(vikingMemoriesSource, /\/web\/viking-memories/);
  assert.match(customCreateSource, /function VikingMemorySelect/);
  assert.match(customCreateSource, /longTermMemoryIndex:\s*memory\.id/);
  assert.match(customCreateSource, /DATABASE_VIKINGMEM_PROJECT/);
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
  assert.equal(openvikingPolicy?.comment, "Memory policy");
  assert.equal(openvikingPolicy?.multiline, true);
  assert.equal(openvikingPolicy?.format, "json");
  assert.match(
    openviking.env.find((env) => env.key === "DATABASE_OPENVIKING_USER_ID")
      ?.help ?? "",
    /viking:\/\/user\/<this value>\/peers\/<request user>\/memories/,
  );
  assert.equal(
    openvikingPolicy?.help,
    "Controls memory extraction and isolation. Leave it blank to use the official default policy.",
  );
  assert.equal(openvikingUrl?.link?.url, openvikingConsoleUrl);
  assert.equal(openvikingApiKey?.link?.url, openvikingConsoleUrl);
  assert.equal(openvikingPolicy?.link?.url, openvikingSessionsDocUrl);
  assert.match(customCreateSource, /className="cw-input cw-env-textarea"/);
  assert.match(customCreateSource, /runtimeEnvJsonError\(item, values, t\("traditional\.env\.invalidJson"\)\)/);
  assert.match(customCreateSource, /firstInvalidRuntimeEnv\(/);
  assert.match(projectPreviewSource, /className="pp-env-value pp-env-json-value"/);
  assert.match(projectPreviewSource, /runtimeEnvJsonError\(\s*row,/);
  assert.match(projectPreviewSource, /firstInvalidRuntimeEnv\(/);
  assert.match(customCreateSource, /className="cw-env-help"/);
  assert.match(customCreateSource, /className="cw-env-link"/);
  assert.match(customCreateSource, /title=\{t\("traditional\.env\.openOpenViking"/);
  assert.match(customCreateSource, /data-help=\{item\.help\}/);
  assert.match(customCreateSource, /className="cw-env-help-popover"/);
  assert.match(projectPreviewSource, /className="pp-env-help"/);
  assert.match(projectPreviewSource, /className="pp-env-link"/);
  assert.match(
    projectPreviewSource,
    /title=\{t\("projectPreview\.openOpenViking", \{ label: row\.link\.label \}\)\}/,
  );
  assert.match(
    projectPreviewSource,
    /const helpText =[\s\S]*?runtimeEnvRequirementHint\(row\)[\s\S]*?row\.help \|\|[\s\S]*?row\.comment/,
  );
  assert.match(projectPreviewSource, /data-help=\{helpText\}/);
  assert.match(projectPreviewSource, /className="pp-env-help-popover"/);
  assert.match(projectPreviewStyles, /\.pp-env-key-cell\s*\{/);
  assert.match(projectPreviewStyles, /\.pp-env-help\s*\{/);
  assert.match(projectPreviewStyles, /\.pp-env-link\s*\{/);
  assert.match(projectPreviewStyles, /cursor:\s*default;/);
  assert.match(projectPreviewStyles, /\.pp-env-help-popover\s*\{[\s\S]*?user-select:\s*text;/);
  assert.match(projectPreviewStyles, /\.pp-env-help:hover \.pp-env-help-popover/);
});

test("declares the OpenViking knowledge runtime configuration", () => {
  const openviking = KB_BACKENDS.find((option) => option.id === "openviking");

  assert.ok(openviking);
  assert.equal(openviking.label, "OpenViking Knowledge");
  assert.equal(openviking.pipExtra, undefined);
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
        "DATABASE_OPENVIKING_TARGET_URI",
        false,
        "viking://user/default/resources/<index>/",
      ],
    ],
  );
  assert.match(
    openviking.env.find((env) => env.key === "DATABASE_OPENVIKING_USER_ID")
      ?.help ?? "",
    /viking:\/\/user\/<this value>\/resources\/<knowledge base index>\//,
  );
  assert.match(
    openviking.env.find((env) => env.key === "DATABASE_OPENVIKING_TARGET_URI")
      ?.help ?? "",
    /KnowledgeBase index/,
  );
  assert.equal(
    firstMissingRuntimeEnv(openviking.env, {
      DATABASE_OPENVIKING_URL: "https://openviking.local",
    })?.key,
    "DATABASE_OPENVIKING_API_KEY",
  );
  assert.deepEqual(
    runtimeEnvVars(openviking.env, {
      DATABASE_OPENVIKING_URL: "https://openviking.local",
      DATABASE_OPENVIKING_API_KEY: "test-api-key",
      DATABASE_OPENVIKING_TARGET_URI: "viking://user/team/resources/faq/",
    }),
    [
      {
        key: "DATABASE_OPENVIKING_URL",
        value: "https://openviking.local",
      },
      { key: "DATABASE_OPENVIKING_API_KEY", value: "test-api-key" },
      {
        key: "DATABASE_OPENVIKING_TARGET_URI",
        value: "viking://user/team/resources/faq/",
      },
    ],
  );
  assert.match(customCreateSource, /traditional\.env\.openVikingIndex/);
  assert.match(
    customCreateSource,
    /id === "viking"\s*\|\|\s*id === "openviking"/,
  );
  assert.match(
    customCreateSource,
    /item\.key\s*===\s*"DATABASE_OPENVIKING_USER_ID"[\s\S]*<OpenVikingKnowledgeIndexField/,
  );
  assert.match(customCreateSource, /traditional\.env\.openVikingIndexHelp/);
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

test("regenerates the project when deployment channel settings change", () => {
  assert.match(
    customCreateSource,
    /onFeishuEnabledChange=\{async \(feishuEnabled\) => \{[\s\S]*?generateAgentProject\([\s\S]*?codegenDraft\(nextDraft\)[\s\S]*?setDraft\(nextDraft\);[\s\S]*?setProject\(generated\);/,
  );
  assert.match(
    customCreateSource,
    /const releaseDraft = releaseVariant[\s\S]*?releaseDraftFromDebugVariant\(providerDraft, releaseVariant\)[\s\S]*?generateAgentProject\(codegenDraft\(releaseDraft\)\)/,
  );
  assert.match(projectPreviewSource, /await onFeishuEnabledChange\(!feishuEnabled\)/);
  assert.match(projectPreviewSource, /deploying \|\| feishuUpdating/);
});

test("restores Feishu credentials into Runtime updates and reuses opaque values", () => {
  assert.match(
    projectPreviewSource,
    /appId=\{deploymentEnvValues\.FEISHU_APP_ID \?\? ""\}/,
  );
  assert.match(
    projectPreviewSource,
    /appSecret=\{deploymentEnvValues\.FEISHU_APP_SECRET \?\? ""\}/,
  );
  assert.match(
    projectPreviewSource,
    /appIdConfigured=\{configuredRuntimeEnvKeySet\.has\([\s\S]*?"FEISHU_APP_ID"/,
  );
  assert.match(
    projectPreviewSource,
    /appSecretConfigured=\{configuredRuntimeEnvKeySet\.has\([\s\S]*?"FEISHU_APP_SECRET"/,
  );
  assert.match(
    customCreateSource,
    /deploymentEnvValues=\{\{[\s\S]*?\.\.\.providerDraft\.deployment\?\.envValues/,
  );
  assert.match(
    customCreateSource,
    /const patchDeploymentEnvValues = \(values: Record<string, string>\)[\s\S]*?envValues: \{[\s\S]*?\.\.\.\(current\.deployment\?\.envValues \?\? \{\}\),[\s\S]*?\.\.\.values/,
  );
  assert.match(
    customCreateSource,
    /onFeishuCredentialsChange=\{\(appId, appSecret\) =>[\s\S]*?patchDeploymentEnvValues\(\{[\s\S]*?FEISHU_APP_ID: appId,[\s\S]*?FEISHU_APP_SECRET: appSecret/,
  );
  assert.match(
    customCreateSource,
    /removedConfiguredMcpEnvKeys\([\s\S]*?FEISHU_APP_ID[\s\S]*?FEISHU_APP_SECRET/,
  );
});

test("normalizes generated project drafts to the selected cloud provider", () => {
  assert.match(customCreateSource, /function draftForCloudProvider/);
  assert.match(
    customCreateSource,
    /setDraft\(\(current\) => draftForCloudProvider\(current, cloudProvider\)\)/,
  );
  assert.match(
    customCreateSource,
    /const providerDraft = useMemo\([\s\S]*?draftForCloudProvider\(draft, cloudProvider\)/,
  );
  assert.match(
    customCreateSource,
    /return nextProvider === "byteplus" && trimmed\.includes\("doubao-"\)/,
  );
  assert.match(
    customCreateSource,
    /const variantDraft: AgentDraft = \{[\s\S]*?\.\.\.providerDraft[\s\S]*?debugRuntimeDraft\(variantDraft, transientModelSecretValues\)/,
  );
});

test("uses concise placeholders for agent names and custom environment variables", () => {
  assert.match(customCreateSource, /placeholder="assistant"/);
  assert.doesNotMatch(customCreateSource, /placeholder="例如：customer_service"/);
  assert.match(projectPreviewSource, /placeholder=\{t\("common\.name"\)\}/);
  assert.match(projectPreviewSource, /placeholder=\{t\("projectPreview\.value"\)\}/);
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
    "Select an agent center",
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
    /a2aRegistryEnvValues\([\s\S]*?node\.a2aRegistry,[\s\S]*?\{ includeDefaults: true \},[\s\S]*?cloudProvider,[\s\S]*?\)/,
  );
  assert.match(
    customCreateSource,
    /fixedValues:\s*\{ \.\.\.config\.fixedValues, \.\.\.fixedValues \}/,
  );
  assert.match(
    customCreateSource,
    /deploymentEnvValues=\{\{[\s\S]*?\.\.\.providerDraft\.deployment\?\.envValues,[\s\S]*?\.\.\.deploymentEnv\.fixedValues,/,
  );
});

test("uses BytePlus defaults for an A2A registry child agent", () => {
  assert.deepEqual(a2aRegistryDefaults("byteplus"), {
    topK: "3",
    region: "ap-southeast-1",
    endpoint: "https://agentkit.ap-southeast-1.byteplusapi.com/",
  });
  assert.match(
    customCreateSource,
    /region=\{[\s\S]*?node\.a2aRegistry\?\.registryRegion \|\|[\s\S]*?a2aDefaults\.region[\s\S]*?\}/,
  );
});

test("summarizes the Agent above the deployment configuration", () => {
  assert.match(customCreateSource, /agentDraft=\{draft\}/);
  assert.match(projectPreviewSource, /className="pp-flow-thumbnail"/);
  assert.match(projectPreviewSource, /<AgentBuildCanvas[\s\S]*?readOnly/);
  assert.match(projectPreviewSource, /projectPreview\.agentCount/);
  assert.match(projectPreviewSource, /projectPreview\.exportYaml/);
  assert.match(projectPreviewSource, /<ProjectCodeBrowser[\s\S]*?pp-artifact-source/);
  assert.match(projectPreviewSource, /projectPreview\.downloadSource/);
  assert.match(
    projectPreviewStyles,
    /grid-template-rows:\s*auto auto/,
  );
  assert.match(projectPreviewStyles, /\.pp-release-preview\s*\{[\s\S]*?box-sizing:\s*border-box/);
});

test("keeps root project files visible before expanded folders", () => {
  for (const source of [codeBrowserSource, projectPreviewSource]) {
    assert.match(
      source,
      /function sortedChildren\(node: TreeNode, filesFirst = false\)/,
    );
    assert.match(
      source,
      /return filesFirst \? \(aFolder \? 1 : -1\) : aFolder \? -1 : 1/,
    );
    assert.match(source, /sortedChildren\(node, depth === 0\)/);
  }
});

test("keeps artifact actions beside the embedded publish canvas", () => {
  assert.match(
    projectPreviewSource,
    /className={`pp-release-preview\$\{embedded \? " is-embedded" : ""\}`}/,
  );
  assert.match(projectPreviewSource, /\{embedded && artifactActions\}/);
  assert.match(projectPreviewSource, /projectPreview\.exportYaml/);
  assert.match(projectPreviewSource, /label=\{t\("projectPreview\.viewSource"\)\}/);
  assert.match(projectPreviewSource, /projectPreview\.downloadSource/);
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

test("lets the narrow publish overview shrink to its content", () => {
  assert.match(
    projectPreviewStyles,
    /@media \(max-width: 860px\)[\s\S]*?\.pp-release-overview\s*\{[\s\S]*?min-height:\s*0;/,
  );
  assert.doesNotMatch(
    projectPreviewStyles,
    /@media \(max-width: 860px\)[\s\S]*?\.pp-release-overview\s*\{[\s\S]*?min-height:\s*460px;/,
  );
});

test("enlarges the read-only execution canvas without topology configuration", () => {
  assert.match(
    projectPreviewSource,
    /className="pp-flow-dialog"[\s\S]*?interactivePreview/,
  );
  assert.match(projectPreviewSource, /projectPreview\.flowPreviewHint/);
  assert.doesNotMatch(projectPreviewSource, /pp-topology-pane|inspectedAgent/);
});

test("uses an unboxed source trigger", () => {
  assert.match(codeBrowserSource, /<span>\{displayLabel\}<\/span>/);
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
    /\.code-browser-dialog\s*\{[\s\S]*?height:\s*min\(800px, 88vh\);/,
  );
});
