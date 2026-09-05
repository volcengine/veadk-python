import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
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
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

const { normalizeDraft } = await loadTypeScriptModule(
  "../src/create/normalizeDraft.ts",
);
const { buildCloudEnvironmentDockerfile } = await loadTypeScriptModule(
  "../src/ui/cloudEnvironmentDockerfile.ts",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);
const createSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const environmentSource = readFileSync(
  new URL("../src/ui/CloudEnvironmentConfigurator.tsx", import.meta.url),
  "utf8",
);
const environmentStyles = readFileSync(
  new URL("../src/ui/CloudEnvironmentConfigurator.css", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);

function draft(overrides = {}) {
  return {
    name: "cloud-agent",
    description: "Cloud environment",
    instruction: "Help the user.",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
    ...overrides,
  };
}

test("normalizes cloud CLI selections with a strict allowlist", () => {
  const normalized = normalizeDraft(
    draft({
      cloudEnvironment: {
        cliTools: [
          "github-cli",
          "unknown-cli",
          "pandoc",
          "lark-cli",
          "github-cli",
        ],
      },
    }),
  );
  assert.deepEqual(normalized.cloudEnvironment, {
    environmentId: "",
    environmentVersionId: "",
    cliTools: ["github-cli", "pandoc", "lark-cli"],
  });
});

test("preserves a custom Dockerfile while normalizing cloud environment settings", () => {
  const normalized = normalizeDraft(
    draft({
      cloudEnvironment: {
        cliTools: ["lark-cli"],
        dockerfile: "FROM example.invalid/custom\nRUN echo ready\n",
      },
    }),
  );
  assert.deepEqual(normalized.cloudEnvironment, {
    environmentId: "",
    environmentVersionId: "",
    cliTools: ["lark-cli"],
    dockerfile: "FROM example.invalid/custom\nRUN echo ready\n",
  });
});

test("builds an editable provider-specific Dockerfile preview", () => {
  const volcengine = buildCloudEnvironmentDockerfile("volcengine", [
    "lark-cli",
  ]);
  const byteplus = buildCloudEnvironmentDockerfile("byteplus", ["github-cli"]);

  assert.match(
    volcengine,
    /^FROM agentkit-prod-public-cn-beijing\.cr\.volces\.com\/base\/py-simple:/,
  );
  assert.match(volcengine, /lark-cli-1\.0\.87-linux-\$\{arch\}\.tar\.gz/);
  assert.match(volcengine, /--connect-timeout 10/);
  assert.match(
    volcengine,
    /https:\/\/ghfast\.top\/https:\/\/github\.com\/larksuite\/cli\/releases\/download/,
  );
  assert.match(
    byteplus,
    /^FROM agentkit-prod-public-ap-southeast-1\.cr\.bytepluses\.com\/base\/py-simple:/,
  );
  assert.match(byteplus, /gh_2\.97\.0_linux_\$\{arch\}\.tar\.gz/);
  assert.match(
    byteplus,
    /apt-get install -y --no-install-recommends ca-certificates curl git/,
  );
  assert.match(byteplus, /# Install GitHub CLI \(gh\)/);
  assert.match(
    byteplus,
    /https:\/\/ghfast\.top\/https:\/\/github\.com\/cli\/cli\/releases\/download/,
  );
  assert.match(
    buildCloudEnvironmentDockerfile("volcengine", ["pandoc"]),
    /apt-get install -y --no-install-recommends ca-certificates curl pandoc/,
  );
  assert.match(volcengine, /# Configure AgentKit runtime defaults\./);
  assert.match(volcengine, /# Install system dependencies/);
  assert.match(volcengine, /# Install Lark CLI/);
  assert.match(volcengine, /# Install Python dependencies/);
  assert.match(volcengine, /# Copy the Agent application/);
  const huawei = "https://repo.huaweicloud.com/repository/pypi/simple";
  const aliyun = "https://mirrors.aliyun.com/pypi/simple/";
  const pypi = "https://pypi.org/simple";
  assert.match(volcengine, new RegExp(huawei.replaceAll(".", "\\.")));
  assert.match(volcengine, new RegExp(aliyun.replaceAll(".", "\\.")));
  assert.match(volcengine, new RegExp(pypi.replaceAll(".", "\\.")));
  assert.ok(volcengine.indexOf(huawei) < volcengine.indexOf(aliyun));
  assert.ok(volcengine.indexOf(aliyun) < volcengine.indexOf(pypi));
  assert.match(byteplus, /RUN uv pip install -r requirements\.txt/);
  assert.doesNotMatch(byteplus, /repo\.huaweicloud\.com|mirrors\.aliyun\.com/);
});

test("exports cloud environment selections through YAML", () => {
  assert.match(
    configYamlSource,
    /draft\.cloudEnvironment\?\.environmentId[\s\S]*?o\.cloudEnvironment\s*=\s*\{[\s\S]*?environmentId:[\s\S]*?environmentVersionId:/,
  );
  assert.match(configYamlSource, /cliTools:/);
  assert.match(configYamlSource, /return normalizeDraft\(obj\)/);
});

test("adds an Apps SDK UI environment step before publishing", () => {
  assert.match(
    createSource,
    /type WorkspaceMode =[\s\S]*?\| "environment"[\s\S]*?\| "publish";/,
  );
  assert.match(createSource, /\{ id: "environment", label: "环境" \}/);
  assert.match(createSource, /environment:\s*"配置云上环境"/);
  assert.match(
    createSource,
    /workspaceMode === "environment"[\s\S]*?<CloudEnvironmentConfigurator/,
  );
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Select/);
  assert.match(environmentSource, /optionClassName\?: string/);
  assert.match(environmentSource, /optionClassName=\{optionClassName\}/);
  assert.match(environmentSource, /listEnvironments\(controller\.signal\)/);
  assert.match(environmentSource, /label: "默认环境"/);
  assert.match(environmentSource, /使用 AgentKit 默认运行环境/);
  assert.match(
    environmentSource,
    /onChange\(\{ environmentId: "", environmentVersionId: "" \}\)/,
  );
  assert.match(
    environmentSource,
    /value=\{value\.environmentId \|\| DEFAULT_ENVIRONMENT_VALUE\}/,
  );
  assert.match(
    environmentSource,
    /disabled: environment\.latestVersion\?\.status !== "available"/,
  );
  assert.match(environmentSource, /environmentVersionId: versionId/);
  assert.match(environmentSource, /正在加载环境/);
  assert.match(environmentSource, /环境加载失败/);
  assert.match(environmentSource, /isPersistenceStorageUnavailableError/);
  assert.match(environmentSource, /message\.includes\("HTTP 503"\)/);
  assert.match(
    environmentSource,
    /message\.includes\("管理员未配置持久化存储"\)/,
  );
  assert.match(
    environmentSource,
    /onChangeRef\.current\(\{\s*environmentId: "",\s*environmentVersionId: "",?\s*\}\)/,
  );
  assert.match(environmentSource, /部署 Runtime 时的默认基础镜像/);
  assert.match(environmentSource, /cloud-env-guidance--fallback/);
  assert.match(
    environmentStyles,
    /\.cloud-env-guidance\.cloud-env-guidance--fallback\s*\{[^}]*color:\s*hsl\(var\(--destructive\)\)/,
  );
  assert.match(environmentSource, /暂无自定义环境/);
  assert.match(environmentSource, /selectedEnvironment\.selectedSkills/);
  assert.doesNotMatch(environmentSource, /CloudEnvironmentAdvancedTrigger/);
  assert.doesNotMatch(environmentSource, /CodeEditor/);
  assert.match(
    createSource,
    /environment: draft\.cloudEnvironment\?\.environmentId/,
  );
  assert.match(clientSource, /environment: opts\?\.environment/);
  assert.match(
    clientSource,
    /environment\?:\s*\{[\s\S]*?environmentId: string;[\s\S]*?environmentVersionId: string;/,
  );
  assert.match(
    appSource,
    /cloudEnvironment: capability\.runtime\.environment \?\? \{[\s\S]*?environmentId: ""/,
  );
});

test("keeps selected environment details responsive", () => {
  assert.match(
    environmentStyles,
    /\.cloud-env-details[\s\S]*?grid-template-columns: repeat\(2/,
  );
  assert.match(environmentStyles, /@media \(max-width: 700px\)/);
  assert.match(environmentStyles, /grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(environmentSource, /searchPlaceholder="搜索环境"/);
  assert.match(environmentSource, /searchEmptyMessage="没有匹配的环境"/);
});
