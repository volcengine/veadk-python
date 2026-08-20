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
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const codeEditorSource = readFileSync(
  new URL("../src/ui/CodeEditor.tsx", import.meta.url),
  "utf8",
);
const globalStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
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
  assert.match(volcengine, /https:\/\/ghfast\.top\/https:\/\/github\.com\/larksuite\/cli\/releases\/download/);
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
  assert.match(byteplus, /https:\/\/ghfast\.top\/https:\/\/github\.com\/cli\/cli\/releases\/download/);
  assert.match(
    buildCloudEnvironmentDockerfile("volcengine", ["pandoc"]),
    /apt-get install -y --no-install-recommends ca-certificates curl pandoc/,
  );
  assert.match(volcengine, /# Configure AgentKit runtime defaults\./);
  assert.match(volcengine, /# Install system dependencies/);
  assert.match(volcengine, /# Install Lark CLI/);
  assert.match(volcengine, /# Install Python dependencies/);
  assert.match(volcengine, /# Copy the Agent application/);
});

test("exports cloud environment selections through YAML", () => {
  assert.match(
    configYamlSource,
    /draft\.cloudEnvironment\?\.cliTools\.length[\s\S]*?o\.cloudEnvironment\s*=\s*\{[\s\S]*?cliTools:/,
  );
  assert.match(configYamlSource, /dockerfile:/);
  assert.match(configYamlSource, /return normalizeDraft\(obj\)/);
});

test("keeps publish mode visible when deployment environment validation fails", () => {
  const publishStart = createSource.indexOf("const openPublishPreview = async");
  const publishEnd = createSource.indexOf(
    "const openValidation =",
    publishStart,
  );
  const publishSource = createSource.slice(publishStart, publishEnd);
  const validationStart = publishSource.indexOf("const invalidEnv =");
  const validationEnd = publishSource.indexOf("setBuilding(true)", validationStart);
  const validationSource = publishSource.slice(validationStart, validationEnd);
  assert.match(validationSource, /if \(invalidEnv\)/);
  assert.doesNotMatch(
    validationSource,
    /if \(invalidEnv\)[\s\S]*?setWorkspaceMode\("build"\)/,
  );
});

test("combines the Apps SDK UI environment controls with deployment", () => {
  assert.match(
    createSource,
    /type WorkspaceMode = "build" \| "validate" \| "publish";/,
  );
  assert.doesNotMatch(createSource, /\| "optimize"/);
  assert.doesNotMatch(createSource, /\{ id: "environment", label: "环境" \}/);
  assert.match(
    createSource,
    /onDeploy=\{\(\) => void handleWorkspaceChange\("publish"\)\}/,
  );
  assert.match(
    createSource,
    /deploymentEnvironmentPane=\{[\s\S]*?<CloudEnvironmentConfigurator[\s\S]*?<CloudEnvironmentAdvancedTrigger/,
  );
  assert.match(createSource, /deploymentTitle="环境与部署"/);
  assert.match(projectPreviewSource, /deploymentEnvironmentPane\?: ReactNode/);
  assert.match(projectPreviewSource, /\{deploymentEnvironmentPane\}/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Button/);
  assert.match(environmentSource, /aria-pressed=\{checked\}/);
  assert.match(environmentSource, /label: "效率"/);
  assert.match(environmentSource, /label: "研发"/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Icon/);
  assert.match(environmentSource, /PlusSm12px/);
  assert.match(environmentSource, /feishuLogo/);
  assert.match(environmentSource, /GitHubLogo/);
  assert.match(environmentSource, /pandocLogo/);
  assert.match(environmentSource, /CloudEnvironmentAdvancedTrigger/);
  assert.match(environmentSource, /role="dialog"/);
  assert.match(environmentSource, /编辑 Dockerfile/);
  assert.doesNotMatch(environmentSource, /DisclosureChevronIcon/);
  assert.doesNotMatch(environmentSource, /command:/);
  assert.doesNotMatch(environmentSource, /可选/);
  assert.match(environmentSource, /<CodeEditor[\s\S]*?path="Dockerfile"/);
  assert.match(environmentSource, /高阶配置/);
  assert.match(environmentSource, /EditCloudEnvironmentIcon/);
  assert.match(environmentSource, /关闭 Dockerfile 编辑器/);
  assert.match(
    environmentSource,
    /closeButtonRef\.current\?\.focus\(\);[\s\S]*?\}, \[editorOpen\]\);/,
  );
  assert.match(environmentSource, /恢复自动生成/);
  assert.match(environmentSource, /Lark CLI/);
  assert.match(environmentSource, /GitHub CLI/);
  assert.match(environmentSource, /Pandoc/);
});

test("keeps confirmation dialogs above the Dockerfile editor", () => {
  assert.match(
    environmentStyles,
    /\.cloud-env-dialog-backdrop\s*\{[\s\S]*?z-index:\s*1250/,
  );
  assert.match(
    globalStyles,
    /\.studio-confirm-backdrop\s*\{[\s\S]*?z-index:\s*1300/,
  );
});

test("uses Dockerfile syntax highlighting in generated and custom editors", () => {
  assert.match(codeEditorSource, /dockerFile.*legacy-modes\/mode\/dockerfile/);
  assert.match(codeEditorSource, /file === "dockerfile"/);
  assert.match(codeEditorSource, /StreamLanguage\.define\(dockerFile\)/);
  assert.match(environmentSource, /<CodeEditor[\s\S]*?path="Dockerfile"/);
});
