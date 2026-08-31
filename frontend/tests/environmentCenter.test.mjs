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
const resourceCollectionStyles = readFileSync(
  new URL("../src/ui/ResourceCollection.css", import.meta.url),
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
const buildLogSource = readFileSync(
  new URL("../src/ui/studioBuildLog.ts", import.meta.url),
  "utf8",
);
const manifestSource = readFileSync(
  new URL("../src/ui/environmentManifest.ts", import.meta.url),
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
  assert.match(environmentSource, />基础环境<\/h2>/);
  assert.match(environmentSource, /AIO Sandbox/);
  assert.match(environmentSource, /Ubuntu/);
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
  assert.match(environmentSource, /BUILD_LOG_REFRESH_INTERVAL_MS = 3_000/);
  assert.match(environmentSource, /window\.setTimeout\(refresh, BUILD_LOG_REFRESH_INTERVAL_MS\)/);
  assert.match(environmentSource, /<StudioBuildProgress/);
  assert.match(environmentSource, /构建详情/);
  assert.match(environmentSource, /已用时/);
  assert.match(environmentSource, /在 CodePipeline 中查看/);
  assert.match(clientSource, /\?includeLogs=true/);
  assert.match(buildProgressSource, /navigator\.clipboard\.writeText\(log\)/);
  assert.match(buildProgressSource, /highlightBashLog\(log\)/);
  assert.match(buildProgressSource, /shouldFollowBuildLog\(event\.currentTarget\)/);
  assert.match(buildProgressSource, /dangerouslySetInnerHTML/);
  assert.match(buildProgressSource, /正在等待 CodePipeline 输出日志/);
  assert.match(buildLogSource, /highlight\.js\/lib\/languages\/bash/);
  assert.match(buildProgressStyles, /overflow: auto/);
  assert.match(environmentStyles, /\.environment-build-dialog__body[\s\S]*?overflow: hidden/);
  assert.match(buildProgressStyles, /@media \(max-width: 640px\)/);
  assert.match(environmentStyles, /max-height: 92dvh/);
});

test("opens a version-bound environment manifest beside the primary card action", async () => {
  assert.match(resourceCardSource, /auxiliaryAction/);
  assert.match(resourceCardSource, /className="library-resource-card__auxiliary-action"/);
  assert.match(environmentSource, /function ManifestIcon/);
  assert.match(environmentSource, /查看环境 Manifest/);
  assert.match(environmentSource, /尚无可用 Manifest/);
  assert.match(environmentSource, /<EnvironmentManifestDialog/);
  assert.match(environmentSource, /<CodeEditor[\s\S]*?path="environment\.yaml"[\s\S]*?readOnly/);
  assert.match(environmentSource, /navigator\.clipboard\.writeText\(manifestYaml\)/);
  assert.match(clientSource, /\/manifest/);
  assert.match(environmentStyles, /\.environment-manifest-dialog__editor/);
  assert.match(environmentStyles, /\.environment-card \.library-resource-card__auxiliary-action\s*\{[\s\S]*?border-color: transparent;[\s\S]*?background: transparent;/);
  assert.match(environmentStyles, /\.environment-card \.library-resource-card__auxiliary-action:hover:not\(:disabled\)[\s\S]*?background: hsl\(var\(--muted\) \/ 0\.72\)/);
  assert.match(resourceCollectionStyles, /@media \(hover: none\), \(pointer: coarse\)/);

  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const manifest = await server.ssrLoadModule("/src/ui/environmentManifest.ts");
    const yaml = manifest.formatEnvironmentManifest({
      apiVersion: "agentkit.studio/v1alpha1",
      kind: "Environment",
      metadata: {
        id: "env-1",
        name: "Browser tools",
        version: "20260831T010203Z-a1b2c3d4",
        description: "Browser automation",
      },
      spec: {
        image: "registry.example/browser:latest",
        baseEnvironment: "ubuntu",
        baseImage: "ubuntu:24.04",
        operatingSystem: "ubuntu-24.04",
        language: "python-3.12",
        executionRuntime: "veadk",
        packages: ["playwright", "chromium"],
        capabilities: [],
        skills: [],
      },
      status: {
        phase: "available",
        createdAt: "2026-08-31T01:02:03Z",
        updatedAt: "2026-08-31T01:05:03Z",
      },
    });
    assert.match(yaml, /^apiVersion: agentkit\.studio\/v1alpha1$/m);
    assert.match(yaml, /^kind: Environment$/m);
    assert.match(yaml, /^  image: registry\.example\/browser:latest$/m);
    assert.match(yaml, /^    - playwright$/m);
  } finally {
    await server.close();
  }
  assert.match(manifestSource, /stringify\(manifest/);
});

test("uses AIO Sandbox as the default base environment and preserves its runtime", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    assert.equal(model.EMPTY_ENVIRONMENT_DRAFT.baseEnvironment, "aio-sandbox");
    const dockerfile = model.buildEnvironmentDockerfile(model.EMPTY_ENVIRONMENT_DRAFT);
    assert.match(dockerfile, /^ARG AIO_BASE_IMAGE=agentkit-cli-2107625663-cn-beijing\.cr\.volces\.com\/agentkit\/agent-native-requirements-aio:0\.2\.1-20260831$/m);
    assert.match(dockerfile, /^FROM --platform=\$\{AIO_BASE_PLATFORM\} \$\{AIO_BASE_IMAGE\}$/m);
    assert.match(dockerfile, /BASH_VENV_PATH=\/opt\/veadk-environment\/\.venv/);
    assert.match(dockerfile, /^EXPOSE 8080$/m);
    assert.doesNotMatch(dockerfile, /^CMD /m);
    assert.doesNotMatch(dockerfile, /^ENTRYPOINT /m);
  } finally {
    await server.close();
  }
});

test("highlights Bash logs and follows only while the reader stays near the bottom", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const buildLog = await server.ssrLoadModule("/src/ui/studioBuildLog.ts");
    assert.equal(buildLog.shouldFollowBuildLog({
      scrollHeight: 1000,
      scrollTop: 730,
      clientHeight: 240,
    }), true);
    assert.equal(buildLog.shouldFollowBuildLog({
      scrollHeight: 1000,
      scrollTop: 600,
      clientHeight: 240,
    }), false);
    assert.match(buildLog.highlightBashLog("apt-get update && echo ready"), /hljs-built_in/);
    assert.match(buildLog.highlightBashLog("echo '<script>'"), /&lt;script&gt;/);
  } finally {
    await server.close();
  }
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
    assert.match(dockerfile, /ARG APT_MIRROR_URL=http:\/\/archive\.ubuntu\.com\/ubuntu/);
    assert.match(dockerfile, /Acquire::Retries \"5\"/);
    assert.match(dockerfile, /Acquire::ForceIPv4 \"true\"/);
    assert.equal(dockerfile.match(/apt-get update/g)?.length, 1);
    assert.equal(dockerfile.match(/apt-get install -y --no-install-recommends/g)?.length, 1);
    assert.match(dockerfile, /Python-3\.12\.11\.tgz/);
    assert.match(dockerfile, /\.\/configure --prefix=\/opt\/python/);
    assert.doesNotMatch(dockerfile, /astral\.sh|github\.com\/astral-sh/);
    assert.match(dockerfile, /pandoc/);
    assert.match(dockerfile, /chromium/);
    assert.match(dockerfile, /lark-cli/);
    assert.match(dockerfile, /python -m playwright install chromium/);
    assert.doesNotMatch(dockerfile, /playwright install --with-deps/);
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
    assert.match(dockerfile, /^    gh \\$/m);
    assert.match(dockerfile, /ENV PLAYWRIGHT_BROWSERS_PATH=\/ms-playwright/);
    assert.equal(
      dockerfile.match(/python -m pip install --upgrade playwright/g)?.length,
      1,
    );
    assert.equal(
      dockerfile.match(/python -m playwright install chromium/g)?.length,
      1,
    );
    assert.equal(dockerfile.match(/apt-get update/g)?.length, 1);
    assert.equal(dockerfile.match(/apt-get install -y --no-install-recommends/g)?.length, 1);
    assert.match(dockerfile, /^    libasound2t64 \\$/m);
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
        assert.equal(dockerfile.match(/apt-get update/g)?.length, 1);
        assert.equal(dockerfile.match(/apt-get install -y --no-install-recommends/g)?.length, 1);
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
