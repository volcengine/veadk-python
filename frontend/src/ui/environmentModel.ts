import type {
  EnvironmentBaseEnvironment,
  EnvironmentContainerRepository,
  EnvironmentGitSource,
  EnvironmentImageSource,
  EnvironmentLanguage,
  EnvironmentOperatingSystem,
} from "../adk/client";
import type { SelectedSkill } from "../create/types";
import type { CloudProvider } from "../adk/cloudProvider";

export type {
  EnvironmentBuildStatus,
  EnvironmentBuildVersion,
  EnvironmentBaseEnvironment,
  EnvironmentLanguage,
  EnvironmentOperatingSystem,
  StudioEnvironment,
} from "../adk/client";

export type EnvironmentCategoryId =
  | "tools"
  | "productivity"
  | "browser"
  | "system";

export interface EnvironmentOption {
  id: string;
  label: string;
  description: string;
  installer: "apt" | "pip" | "npm";
  packageName: string;
}

export interface EnvironmentCategory {
  id: EnvironmentCategoryId;
  label: string;
  description: string;
  options: readonly EnvironmentOption[];
}

export interface EnvironmentDraft {
  name: string;
  description: string;
  baseEnvironment: EnvironmentBaseEnvironment;
  operatingSystem: EnvironmentOperatingSystem;
  language: EnvironmentLanguage;
  optionIds: string[];
  selectedSkills: SelectedSkill[];
  dockerfile?: string;
  gitSource?: EnvironmentGitSource | null;
  containerRepository?: EnvironmentContainerRepository | null;
  imageSource?: EnvironmentImageSource | null;
}

export const ENVIRONMENT_OPERATING_SYSTEMS: ReadonlyArray<{
  id: EnvironmentOperatingSystem;
  label: string;
  image: string;
}> = [
  { id: "ubuntu-22.04", label: "Ubuntu 22.04", image: "ubuntu:22.04" },
  { id: "ubuntu-24.04", label: "Ubuntu 24.04", image: "ubuntu:24.04" },
];

export const ENVIRONMENT_BASE_ENVIRONMENTS: ReadonlyArray<{
  id: EnvironmentBaseEnvironment;
  label: string;
  description: string;
}> = [
  {
    id: "aio-sandbox",
    label: "AIO Sandbox",
    description: "内置 Sandbox Shell 能力 · Ubuntu 22.04",
  },
  {
    id: "codex-sandbox",
    label: "Codex Sandbox",
    description: "内置 Codex CLI、浏览器与代码执行环境",
  },
  {
    id: "ubuntu",
    label: "Ubuntu",
    description: "标准 Linux 基础镜像",
  },
];

export const AIO_BASE_IMAGE = "agentkit-cli-2107625663-cn-beijing.cr.volces.com/agentkit/agent-native-requirements-aio:0.2.1-20260831";

export const CODEX_SANDBOX_BASE_IMAGES: Record<CloudProvider, string> = {
  volcengine: "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/codexenv:1.1.0",
  byteplus: "enterprise-public-ap-southeast-1.cr.volces.com/vefaas-public/codexenv:1.1.0",
};

export const ENVIRONMENT_LANGUAGES: ReadonlyArray<{
  id: EnvironmentLanguage;
  label: string;
}> = [
  { id: "python-3.10", label: "Python 3.10" },
  { id: "python-3.12", label: "Python 3.12" },
];

const PYTHON_PATCH_VERSIONS: Record<EnvironmentLanguage, string> = {
  "python-3.10": "3.10.18",
  "python-3.12": "3.12.11",
};

export const ENVIRONMENT_CATEGORIES: readonly EnvironmentCategory[] = [
  {
    id: "tools",
    label: "工具",
    description: "常用 CLI 与内容处理工具",
    options: [
      { id: "lark-cli", label: "lark-cli", description: "飞书开放平台命令行工具", installer: "pip", packageName: "lark-cli" },
      { id: "pandoc", label: "pandoc", description: "文档格式转换工具", installer: "apt", packageName: "pandoc" },
      { id: "opencli", label: "opencli", description: "将网站与桌面应用转换为命令行工具", installer: "npm", packageName: "@jackwener/opencli@1.8.7" },
    ],
  },
  {
    id: "productivity",
    label: "效率",
    description: "加速依赖安装、检索和协作",
    options: [
      { id: "uv", label: "uv", description: "快速 Python 包与项目管理器", installer: "pip", packageName: "uv" },
      { id: "ripgrep", label: "ripgrep", description: "高性能文本检索工具", installer: "apt", packageName: "ripgrep" },
      { id: "jq", label: "jq", description: "JSON 查询与转换工具", installer: "apt", packageName: "jq" },
      { id: "github-cli", label: "GitHub CLI", description: "在终端中管理 GitHub 工作流", installer: "apt", packageName: "gh" },
    ],
  },
  {
    id: "browser",
    label: "浏览器自动化",
    description: "网页操作、测试与内容采集",
    options: [
      { id: "playwright", label: "Playwright", description: "浏览器自动化与端到端测试", installer: "pip", packageName: "playwright" },
      { id: "chromium", label: "Chromium", description: "无头浏览器运行时", installer: "apt", packageName: "chromium" },
    ],
  },
  {
    id: "system",
    label: "系统与媒体",
    description: "基础开发、网络和媒体处理能力",
    options: [
      { id: "git", label: "Git", description: "代码版本管理", installer: "apt", packageName: "git" },
      { id: "curl", label: "curl", description: "网络请求与文件下载", installer: "apt", packageName: "curl" },
      { id: "ffmpeg", label: "FFmpeg", description: "音视频转码与处理", installer: "apt", packageName: "ffmpeg" },
      { id: "imagemagick", label: "ImageMagick", description: "图片转换与批处理", installer: "apt", packageName: "imagemagick" },
    ],
  },
];

const ALL_OPTIONS = ENVIRONMENT_CATEGORIES.flatMap((category) => category.options);

const PYTHON_BUILD_APT_PACKAGES = [
  "build-essential",
  "curl",
  "libbz2-dev",
  "libffi-dev",
  "libgdbm-dev",
  "liblzma-dev",
  "libncursesw5-dev",
  "libreadline-dev",
  "libsqlite3-dev",
  "libssl-dev",
  "tk-dev",
  "uuid-dev",
  "zlib1g-dev",
] as const;

const PLAYWRIGHT_COMMON_APT_PACKAGES = [
  "xvfb",
  "fonts-noto-color-emoji",
  "fonts-unifont",
  "libfontconfig1",
  "libfreetype6",
  "xfonts-cyrillic",
  "xfonts-scalable",
  "fonts-liberation",
  "fonts-ipafont-gothic",
  "fonts-wqy-zenhei",
  "fonts-tlwg-loma-otf",
  "fonts-freefont-ttf",
] as const;

const PLAYWRIGHT_CHROMIUM_APT_PACKAGES: Record<
  EnvironmentOperatingSystem,
  readonly string[]
> = {
  "ubuntu-22.04": [
    "libasound2",
    "libatk-bridge2.0-0",
    "libatk1.0-0",
    "libatspi2.0-0",
    "libcairo2",
    "libcups2",
    "libdbus-1-3",
    "libdrm2",
    "libgbm1",
    "libglib2.0-0",
    "libnspr4",
    "libnss3",
    "libpango-1.0-0",
    "libwayland-client0",
    "libx11-6",
    "libxcb1",
    "libxcomposite1",
    "libxdamage1",
    "libxext6",
    "libxfixes3",
    "libxkbcommon0",
    "libxrandr2",
  ],
  "ubuntu-24.04": [
    "libasound2t64",
    "libatk-bridge2.0-0t64",
    "libatk1.0-0t64",
    "libatspi2.0-0t64",
    "libcairo2",
    "libcups2t64",
    "libdbus-1-3",
    "libdrm2",
    "libgbm1",
    "libglib2.0-0t64",
    "libnspr4",
    "libnss3",
    "libpango-1.0-0",
    "libx11-6",
    "libxcb1",
    "libxcomposite1",
    "libxdamage1",
    "libxext6",
    "libxfixes3",
    "libxkbcommon0",
    "libxrandr2",
  ],
};

function appendUnique(target: string[], packages: readonly string[]) {
  for (const packageName of packages) {
    if (!target.includes(packageName)) target.push(packageName);
  }
}

function environmentAptPackages(
  environment: EnvironmentDraft,
  selected: readonly EnvironmentOption[],
  pythonVersion: string,
  usesUbuntuPython: boolean,
  usesAioPython: boolean,
) {
  const packages = ["ca-certificates"];
  if (!usesAioPython) {
    appendUnique(
      packages,
      usesUbuntuPython
        ? [`python${pythonVersion}`, `python${pythonVersion}-venv`]
        : PYTHON_BUILD_APT_PACKAGES,
    );
  }
  for (const option of selected) {
    if (option.id === "playwright" || option.id === "chromium") continue;
    if (option.installer === "apt") appendUnique(packages, [option.packageName]);
    if (option.id === "opencli") appendUnique(packages, ["curl", "xz-utils"]);
  }
  if (environment.optionIds.some((id) => id === "playwright" || id === "chromium")) {
    appendUnique(packages, PLAYWRIGHT_COMMON_APT_PACKAGES);
    appendUnique(packages, PLAYWRIGHT_CHROMIUM_APT_PACKAGES[environment.operatingSystem]);
  }
  return packages;
}

export const EMPTY_ENVIRONMENT_DRAFT: EnvironmentDraft = {
  name: "",
  description: "",
  baseEnvironment: "aio-sandbox",
  operatingSystem: "ubuntu-22.04",
  language: "python-3.12",
  optionIds: [],
  selectedSkills: [],
};

export function environmentLanguageLabel(language: EnvironmentLanguage): string {
  return ENVIRONMENT_LANGUAGES.find((item) => item.id === language)?.label ?? language;
}

export function environmentOperatingSystemLabel(operatingSystem: EnvironmentOperatingSystem): string {
  return ENVIRONMENT_OPERATING_SYSTEMS.find((item) => item.id === operatingSystem)?.label ?? operatingSystem;
}

export function environmentBaseEnvironmentLabel(baseEnvironment: EnvironmentBaseEnvironment): string {
  return ENVIRONMENT_BASE_ENVIRONMENTS.find((item) => item.id === baseEnvironment)?.label ?? baseEnvironment;
}

export function environmentComponentCount(environment: EnvironmentDraft): number {
  return environment.optionIds.length + environment.selectedSkills.length + 3;
}

export function environmentBaseFromDockerfile(dockerfile: string): {
  baseEnvironment: EnvironmentBaseEnvironment;
  operatingSystem: EnvironmentOperatingSystem;
} {
  const from = dockerfile.match(/^\s*FROM\s+(.+)$/im)?.[1] ?? "";
  return {
    baseEnvironment: /\/codexenv:/i.test(from)
      ? "codex-sandbox"
      : /aio\.sandbox/i.test(dockerfile)
        ? "aio-sandbox"
        : "ubuntu",
    operatingSystem: /ubuntu:24\.04/i.test(from) ? "ubuntu-24.04" : "ubuntu-22.04",
  };
}

export function buildEnvironmentDockerfile(
  environment: EnvironmentDraft,
  cloudProvider: CloudProvider = "volcengine",
): string {
  const selected = ALL_OPTIONS.filter((option) => environment.optionIds.includes(option.id));
  const usesAioPython = environment.baseEnvironment === "aio-sandbox";
  const usesCodexPython = environment.baseEnvironment === "codex-sandbox";
  const usesPresetPython = usesAioPython || usesCodexPython;
  const language = usesPresetPython ? "python-3.12" : environment.language;
  const pythonVersion = language.replace("python-", "");
  const pythonPatchVersion = PYTHON_PATCH_VERSIONS[language];
  const operatingSystem = ENVIRONMENT_OPERATING_SYSTEMS.find(
    (item) => item.id === environment.operatingSystem,
  ) ?? ENVIRONMENT_OPERATING_SYSTEMS[0];
  const usesUbuntuPython =
    (environment.operatingSystem === "ubuntu-22.04" && pythonVersion === "3.10") ||
    (environment.operatingSystem === "ubuntu-24.04" && pythonVersion === "3.12");
  const aptPackages = environmentAptPackages(
    environment,
    selected,
    pythonVersion,
    usesUbuntuPython,
    usesPresetPython,
  );
  const lines = usesAioPython
    ? [
        `ARG AIO_BASE_IMAGE=${AIO_BASE_IMAGE}`,
        "ARG AIO_BASE_PLATFORM=linux/amd64",
        "",
        `# Base environment: AIO Sandbox (${operatingSystem.label})`,
        "FROM --platform=${AIO_BASE_PLATFORM} ${AIO_BASE_IMAGE}",
      ]
    : usesCodexPython
      ? [
          `ARG CODEX_BASE_IMAGE=${CODEX_SANDBOX_BASE_IMAGES[cloudProvider]}`,
          "ARG CODEX_BASE_PLATFORM=linux/amd64",
          "",
          "# Base environment: Codex Sandbox",
          "FROM --platform=${CODEX_BASE_PLATFORM} ${CODEX_BASE_IMAGE}",
        ]
      : [
          `# Operating system: ${operatingSystem.label}`,
          `FROM ${operatingSystem.image}`,
        ];
  lines.push(
    "",
    "ARG DEBIAN_FRONTEND=noninteractive",
    "ARG APT_MIRROR_URL=http://archive.ubuntu.com/ubuntu",
    "ARG PIP_INDEX_URL=https://pypi.org/simple",
    "ARG PYTHON_SOURCE_BASE_URL=https://www.python.org/ftp/python",
    "ARG PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev",
    "ARG PIP_DEFAULT_TIMEOUT=300",
    "ARG PIP_RETRIES=10",
    "",
    "# Install all system dependencies in one transaction from the provider-local mirror.",
    "RUN set -eux; \\",
    '    mirror="${APT_MIRROR_URL%/}"; \\',
    "    for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do \\",
    '        [ -f "$source_file" ] || continue; \\',
    '        sed -i -E "s#https?://(archive|security).ubuntu.com/ubuntu/?#${mirror}#g" "$source_file"; \\',
    "    done; \\",
    "    printf 'Acquire::Retries \"5\";\\nAcquire::ForceIPv4 \"true\";\\nAcquire::http::Timeout \"60\";\\nAcquire::https::Timeout \"60\";\\n' > /etc/apt/apt.conf.d/80-veadk-network; \\",
    "    apt-get update; \\",
    "    apt-get install -y --no-install-recommends \\",
    ...aptPackages.map((packageName) => "    " + packageName + " \\"),
    "    ; rm -rf /var/lib/apt/lists/*",
    "",
    "ENV PYTHONDONTWRITEBYTECODE=1 \\",
    "    PYTHONUNBUFFERED=1 \\",
    "    PIP_NO_CACHE_DIR=1",
    "",
    `# Python ${pythonVersion}`,
  );
  if (usesAioPython) {
    lines.push(
      "# Keep Studio dependencies isolated from AIO's system interpreter.",
      "RUN /opt/python3.12/bin/python -m venv /opt/veadk-environment/.venv",
      "",
      "ENV VIRTUAL_ENV=/opt/veadk-environment/.venv \\",
      "    BASH_VENV_PATH=/opt/veadk-environment/.venv \\",
      "    PATH=\"/opt/veadk-environment/.venv/bin:$PATH\"",
    );
  } else if (usesCodexPython) {
    lines.push(
      "# Keep Studio dependencies isolated from the Codex runtime.",
      "RUN python3 -m venv /opt/veadk-environment/.venv",
      "",
      "ENV VIRTUAL_ENV=/opt/veadk-environment/.venv \\",
      "    PATH=\"/opt/veadk-environment/.venv/bin:$PATH\"",
    );
  } else if (usesUbuntuPython) {
    lines.push(`RUN python${pythonVersion} -m venv /opt/venv`);
  } else {
    lines.push(
      `RUN curl --retry 5 --retry-all-errors --connect-timeout 30 -fsSL "\${PYTHON_SOURCE_BASE_URL}/${pythonPatchVersion}/Python-${pythonPatchVersion}.tgz" -o /tmp/python.tgz \\`,
      "    && mkdir -p /tmp/python-source \\",
      "    && tar -xzf /tmp/python.tgz --strip-components=1 -C /tmp/python-source \\",
      "    && cd /tmp/python-source \\",
      "    && ./configure --prefix=/opt/python --with-ensurepip=install \\",
      "    && make -j\"$(nproc)\" \\",
      "    && make install \\",
      `    && /opt/python/bin/python${pythonVersion} -m venv /opt/venv \\`,
      "    && rm -rf /tmp/python-source /tmp/python.tgz",
    );
  }
  if (!usesPresetPython) lines.push("", "ENV PATH=\"/opt/venv/bin:$PATH\"");

  const selectedOptionIds = new Set(environment.optionIds);
  if (selectedOptionIds.has("playwright") || selectedOptionIds.has("chromium")) {
    lines.push(
      "",
      "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \\",
      "    PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000",
    );
  }
  lines.push(
    "",
    "WORKDIR /workspace",
    "",
    "# VeADK: Agent 开发与运行框架",
    "RUN python -m pip install --upgrade veadk-python",
  );

  let browserInstalled = false;
  for (const option of selected) {
    lines.push("", `# ${option.label}: ${option.description}`);
    if (option.id === "opencli") {
      lines.push(
        "RUN node_arch=\"$(dpkg --print-architecture)\" \\",
        "    && case \"$node_arch\" in amd64) node_arch=x64 ;; arm64) node_arch=arm64 ;; *) echo \"Unsupported architecture: $node_arch\" >&2; exit 1 ;; esac \\",
        "    && curl --retry 5 --connect-timeout 30 -fsSL \"https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-${node_arch}.tar.xz\" -o /tmp/node.tar.xz \\",
        "    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \\",
        `    && npm install --global ${option.packageName} \\`,
        "    && npm cache clean --force \\",
        "    && rm -f /tmp/node.tar.xz",
      );
    } else if (option.id === "playwright" || option.id === "chromium") {
      if (!browserInstalled) {
        lines.push("RUN python -m pip install --upgrade playwright");
        lines.push("RUN python -m playwright install chromium");
        browserInstalled = true;
      }
    } else if (option.installer !== "apt") {
      lines.push(`RUN python -m pip install --upgrade ${option.packageName}`);
    }
  }

  if (usesAioPython) {
    lines.push(
      "",
      "# Keep AIO's inherited /opt/gem/run.sh startup chain and shell API.",
      "EXPOSE 8080",
    );
  } else if (!usesCodexPython) {
    lines.push("", "CMD [\"/bin/bash\"]");
  }
  return lines.join("\n");
}
