import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createServer } from "vite";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebarSource = readFileSync(new URL("../src/ui/Sidebar.tsx", import.meta.url), "utf8");
const environmentSource = readFileSync(
  new URL("../src/ui/EnvironmentCenter.tsx", import.meta.url),
  "utf8",
);
const environmentStyles = readFileSync(
  new URL("../src/ui/EnvironmentCenter.css", import.meta.url),
  "utf8",
);
const dockerfileUploadSource = readFileSync(
  new URL("../src/ui/environmentDockerfileUpload.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const resourceCardSource = readFileSync(
  new URL("../src/ui/LibraryResourceCard.tsx", import.meta.url),
  "utf8",
);
const packageOptionSource = readFileSync(
  new URL("../src/ui/StudioPackageOption.tsx", import.meta.url),
  "utf8",
);
const packageOptionStyles = readFileSync(
  new URL("../src/ui/StudioPackageOption.css", import.meta.url),
  "utf8",
);
const buildProgressSource = readFileSync(
  new URL("../src/ui/StudioBuildProgress.tsx", import.meta.url),
  "utf8",
);
const buildProgressStyles = readFileSync(
  new URL("../src/ui/StudioBuildProgress.css", import.meta.url),
  "utf8",
);

test("keeps Environment available without a standalone sidebar item", () => {
  assert.doesNotMatch(sidebarSource, /onEnvironment: \(\) => void/);
  assert.doesNotMatch(sidebarSource, /onClick=\{onEnvironment\}/);
  assert.doesNotMatch(sidebarSource, /aria-label="环境"/);
  assert.match(appSource, /import \{ EnvironmentCenter \}/);
  assert.match(appSource, /environmentView\s*\? "environments"/);
  assert.match(appSource, /environmentView \? \([\s\S]*?<EnvironmentCenter cloudProvider=\{cloudProvider\} \/>/);
});

test("uses Apps SDK UI controls and shared Studio patterns", () => {
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Button/);
  assert.doesNotMatch(environmentSource, /@openai\/apps-sdk-ui\/components\/Checkbox/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Input/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/RadioGroup/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/SegmentedControl/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Textarea/);
  assert.match(environmentSource, /<ResourcePageShell className="environment-center"/);
  assert.match(environmentSource, /<ResourcePageHeader/);
  assert.match(environmentSource, /<ResourceToolbar className="environment-toolbar">/);
  assert.match(environmentSource, /<ResourceSearch/);
  assert.match(environmentSource, /<ResourceResults/);
  assert.match(environmentSource, /<ResourceGrid>/);
  assert.match(environmentSource, /<ResourceCreateCard/);
  assert.match(environmentSource, /<LibraryResourceCard/);
  assert.match(environmentSource, /<StudioPackageOption/);
  assert.match(environmentSource, /<SegmentedControl\.Option value="configuration">配置/);
  assert.match(environmentSource, /<SegmentedControl\.Option value="dockerfile">描述文件/);
  assert.doesNotMatch(environmentSource, /自动生成<\/Badge>/);
  assert.match(resourceCardSource, /<ResourceCardRevealAction/);
  assert.match(packageOptionSource, /aria-pressed=\{selected\}/);
  assert.match(packageOptionStyles, /min-height: 54px/);
});

test("covers environment categories, editor feedback, and responsive layout", () => {
  assert.match(environmentSource, />操作系统<\/h2>/);
  assert.match(environmentSource, />语言<\/h2>/);
  assert.match(environmentSource, />执行环境<\/h2>/);
  assert.match(environmentSource, />技能<\/h2>/);
  assert.match(environmentSource, /<SkillSourcePicker/);
  assert.match(environmentSource, /selected=\{draft\.selectedSkills\}/);
  assert.match(environmentSource, /name="VeADK"/);
  assert.match(environmentSource, /name="VeADK"[\s\S]*?selected[\s\S]*?disabled/);
  assert.match(environmentSource, /ENVIRONMENT_CATEGORIES\.map/);
  assert.match(environmentSource, /aria-label="Dockerfile 内容"/);
  assert.match(environmentSource, /role="status" aria-live="polite"/);
  assert.match(environmentSource, /StudioConfirmDialog/);
  assert.match(environmentStyles, /@media \(max-width: 560px\)/);
  assert.match(environmentStyles, /grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(environmentStyles, /\.environment-editor__header\s*\{\s*align-items: center;/);
  assert.match(environmentStyles, /\.environment-form[\s\S]*?height: 100%/);
  assert.match(environmentStyles, /\.environment-dockerfile__editor > textarea[\s\S]*?min-height: inherit/);
});

test("offers Dockerfile upload and custom configuration as explicit creation methods", () => {
  assert.match(environmentSource, /type EnvironmentCreationMethod = "custom" \| "dockerfile"/);
  assert.match(environmentSource, /aria-label="环境创建方式"/);
  assert.match(environmentSource, /value="custom"[\s\S]*?自定义配置/);
  assert.match(environmentSource, /value="dockerfile"[\s\S]*?上传 Dockerfile/);
  assert.match(environmentSource, /type="file"/);
  assert.match(environmentSource, /onDrop=\{handleDockerfileDrop\}/);
  assert.match(environmentSource, /aria-label="Dockerfile 文件"/);
  assert.match(environmentSource, /上传后可继续编辑内容/);
  assert.match(environmentStyles, /\.environment-creation-options/);
  assert.match(environmentStyles, /\.environment-upload-dropzone\.is-dragging/);
  assert.match(environmentStyles, /\.environment-upload-dropzone:focus-within/);
});

test("validates Dockerfile uploads before the environment is created", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const upload = await server.ssrLoadModule("/src/ui/environmentDockerfileUpload.ts");
    assert.equal(upload.validateDockerfileUpload("", 0), "Dockerfile 内容不能为空。");
    assert.equal(
      upload.validateDockerfileUpload("RUN echo hello", 14),
      "Dockerfile 缺少 FROM 指令。",
    );
    assert.equal(
      upload.validateDockerfileUpload("FROM ubuntu:24.04", upload.MAX_DOCKERFILE_BYTES + 1),
      "Dockerfile 不能超过 128 KiB。",
    );
    assert.equal(upload.validateDockerfileUpload("# syntax=docker/dockerfile:1\nFROM ubuntu:24.04"), "");
    assert.equal(upload.normalizeDockerfileContent("\uFEFFFROM ubuntu:24.04\r\n"), "FROM ubuntu:24.04\n");
    assert.match(dockerfileUploadSource, /file\.text\(\)/);
  } finally {
    await server.close();
  }
});

test("persists environments and starts image builds through the Studio API", () => {
  assert.match(environmentSource, /listEnvironments/);
  assert.match(environmentSource, /createEnvironment/);
  assert.match(environmentSource, /updateEnvironment/);
  assert.match(environmentSource, /deleteEnvironment/);
  assert.match(environmentSource, /buildEnvironment/);
  assert.match(environmentSource, /TextShimmer/);
  assert.match(environmentSource, /重新加载/);
  assert.match(environmentSource, /重新构建/);
  assert.doesNotMatch(environmentSource, /INITIAL_ENVIRONMENTS/);
  assert.match(clientSource, /\/web\/environments/);
  assert.match(clientSource, /\/web\/environment-resources/);
});

test("shows live build steps and redacted log snapshots in a responsive detail dialog", () => {
  assert.match(environmentSource, /getEnvironmentBuild/);
  assert.match(environmentSource, /includeLogs: true/);
  assert.match(environmentSource, /window\.setTimeout\(refresh, 5000\)/);
  assert.match(environmentSource, /<StudioBuildProgress/);
  assert.match(environmentSource, /构建详情/);
  assert.match(environmentSource, /已用时/);
  assert.match(environmentSource, /在 CodePipeline 中查看/);
  assert.match(clientSource, /\?includeLogs=true/);
  assert.match(buildProgressSource, /navigator\.clipboard\.writeText\(log\)/);
  assert.match(buildProgressSource, /正在等待 CodePipeline 输出日志/);
  assert.match(buildProgressStyles, /@media \(max-width: 640px\)/);
  assert.match(environmentStyles, /max-height: 92dvh/);
});

test("generates a Dockerfile from language and selected tools", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    const dockerfile = model.buildEnvironmentDockerfile({
      name: "Browser environment",
      description: "",
      operatingSystem: "ubuntu-22.04",
      language: "python-3.12",
      optionIds: ["lark-cli", "pandoc", "playwright", "chromium"],
    });
    assert.match(dockerfile, /^# Operating system: Ubuntu 22\.04$/m);
    assert.match(dockerfile, /^FROM ubuntu:22\.04$/m);
    assert.match(dockerfile, /^# Python 3\.12$/m);
    assert.match(dockerfile, /^# VeADK: Agent 开发与运行框架$/m);
    assert.match(dockerfile, /python -m pip install --upgrade veadk-python/);
    assert.match(dockerfile, /PIP_DEFAULT_TIMEOUT=300/);
    assert.match(dockerfile, /PIP_RETRIES=10/);
    assert.match(dockerfile, /PIP_INDEX_URL=https:\/\/pypi\.org\/simple/);
    assert.match(dockerfile, /PYTHON_SOURCE_BASE_URL=https:\/\/www\.python\.org\/ftp\/python/);
    assert.match(dockerfile, /PLAYWRIGHT_DOWNLOAD_HOST=https:\/\/cdn\.playwright\.dev/);
    assert.match(dockerfile, /https:\/\/archive\.ubuntu\.com/);
    assert.match(dockerfile, /https:\/\/security\.ubuntu\.com/);
    assert.match(dockerfile, /Acquire::Retries \"5\"/);
    assert.match(dockerfile, /Acquire::ForceIPv4 \"true\"/);
    assert.match(dockerfile, /Python-3\.12\.11\.tgz/);
    assert.match(dockerfile, /\.\/configure --prefix=\/opt\/python/);
    assert.doesNotMatch(dockerfile, /astral\.sh|github\.com\/astral-sh/);
    assert.match(dockerfile, /pandoc/);
    assert.match(dockerfile, /chromium/);
    assert.match(dockerfile, /lark-cli/);
    assert.match(dockerfile, /python -m playwright install --with-deps chromium/);
    assert.match(dockerfile, /# lark-cli: 飞书开放平台命令行工具/);
    assert.match(dockerfile, /# Playwright: 浏览器自动化与端到端测试/);
  } finally {
    await server.close();
  }
});

test("changes the base image with the selected operating system", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    const dockerfile = model.buildEnvironmentDockerfile({
      name: "Ubuntu environment",
      description: "",
      operatingSystem: "ubuntu-24.04",
      language: "python-3.10",
      optionIds: [],
    });
    assert.match(dockerfile, /^# Operating system: Ubuntu 24\.04$/m);
    assert.match(dockerfile, /^FROM ubuntu:24\.04$/m);
    assert.match(dockerfile, /^# Python 3\.10$/m);
  } finally {
    await server.close();
  }
});

test("uses reliable GitHub CLI and browser recipes without duplicate Chromium installs", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    const dockerfile = model.buildEnvironmentDockerfile({
      name: "Toolchain",
      description: "",
      operatingSystem: "ubuntu-24.04",
      language: "python-3.12",
      optionIds: ["opencli", "github-cli", "playwright", "chromium"],
    });
    assert.match(dockerfile, /githubcli-archive-keyring\.gpg/);
    assert.match(dockerfile, /https:\/\/cli\.github\.com\/packages stable main/);
    assert.match(dockerfile, /ENV PLAYWRIGHT_BROWSERS_PATH=\/ms-playwright/);
    assert.equal(
      dockerfile.match(/python -m pip install --upgrade playwright/g)?.length,
      1,
    );
    assert.equal(
      dockerfile.match(/python -m playwright install --with-deps chromium/g)?.length,
      1,
    );
    assert.match(dockerfile, /npm install --global @jackwener\/opencli@1\.8\.7/);
  } finally {
    await server.close();
  }
});

test("generates every supported OS and Python combination with per-tool comments", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    for (const operatingSystem of model.ENVIRONMENT_OPERATING_SYSTEMS) {
      for (const language of model.ENVIRONMENT_LANGUAGES) {
        const optionIds = model.ENVIRONMENT_CATEGORIES.flatMap((category) =>
          category.options.map((option) => option.id),
        );
        const dockerfile = model.buildEnvironmentDockerfile({
          name: "matrix",
          description: "",
          operatingSystem: operatingSystem.id,
          language: language.id,
          optionIds,
        });
        assert.match(dockerfile, new RegExp(`^FROM ${operatingSystem.image.replace(".", "\\.")}$`, "m"));
        assert.match(dockerfile, new RegExp(`^# Python ${language.id.replace("python-", "").replace(".", "\\.")}$`, "m"));
        for (const category of model.ENVIRONMENT_CATEGORIES) {
          for (const option of category.options) {
            assert.match(dockerfile, new RegExp(`^# ${option.label.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}:`, "m"));
          }
        }
      }
    }
  } finally {
    await server.close();
  }
});
