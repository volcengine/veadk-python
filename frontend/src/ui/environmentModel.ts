import type {
  EnvironmentLanguage,
  EnvironmentOperatingSystem,
} from "../adk/client";
import type { SelectedSkill } from "../create/types";

export type {
  EnvironmentBuildStatus,
  EnvironmentBuildVersion,
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
  operatingSystem: EnvironmentOperatingSystem;
  language: EnvironmentLanguage;
  optionIds: string[];
  selectedSkills: SelectedSkill[];
  dockerfile?: string;
}

export const ENVIRONMENT_OPERATING_SYSTEMS: ReadonlyArray<{
  id: EnvironmentOperatingSystem;
  label: string;
  image: string;
}> = [
  { id: "ubuntu-22.04", label: "Ubuntu 22.04", image: "ubuntu:22.04" },
  { id: "ubuntu-24.04", label: "Ubuntu 24.04", image: "ubuntu:24.04" },
];

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

export const EMPTY_ENVIRONMENT_DRAFT: EnvironmentDraft = {
  name: "",
  description: "",
  operatingSystem: "ubuntu-22.04",
  language: "python-3.12",
  optionIds: ["lark-cli", "pandoc", "opencli", "uv", "ripgrep", "jq", "git", "curl"],
  selectedSkills: [],
};

export function environmentLanguageLabel(language: EnvironmentLanguage): string {
  return ENVIRONMENT_LANGUAGES.find((item) => item.id === language)?.label ?? language;
}

export function environmentOperatingSystemLabel(operatingSystem: EnvironmentOperatingSystem): string {
  return ENVIRONMENT_OPERATING_SYSTEMS.find((item) => item.id === operatingSystem)?.label ?? operatingSystem;
}

export function environmentComponentCount(environment: EnvironmentDraft): number {
  return environment.optionIds.length + environment.selectedSkills.length + 3;
}

export function buildEnvironmentDockerfile(environment: EnvironmentDraft): string {
  const selected = ALL_OPTIONS.filter((option) => environment.optionIds.includes(option.id));
  const pythonVersion = environment.language.replace("python-", "");
  const pythonPatchVersion = PYTHON_PATCH_VERSIONS[environment.language];
  const operatingSystem = ENVIRONMENT_OPERATING_SYSTEMS.find(
    (item) => item.id === environment.operatingSystem,
  ) ?? ENVIRONMENT_OPERATING_SYSTEMS[0];
  const usesUbuntuPython =
    (environment.operatingSystem === "ubuntu-22.04" && pythonVersion === "3.10") ||
    (environment.operatingSystem === "ubuntu-24.04" && pythonVersion === "3.12");
  const lines = [
    `# Operating system: ${operatingSystem.label}`,
    `FROM ${operatingSystem.image}`,
    "",
    "ARG DEBIAN_FRONTEND=noninteractive",
    "ARG PIP_INDEX_URL=https://pypi.org/simple",
    "ARG PYTHON_SOURCE_BASE_URL=https://www.python.org/ftp/python",
    "ARG PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev",
    "ARG PIP_DEFAULT_TIMEOUT=300",
    "ARG PIP_RETRIES=10",
    "",
    "ENV PYTHONDONTWRITEBYTECODE=1 \\",
    "    PYTHONUNBUFFERED=1 \\",
    "    PIP_NO_CACHE_DIR=1",
    "",
    `# Python ${pythonVersion}`,
    "RUN apt-get update \\",
  ];
  if (usesUbuntuPython) {
    lines.push(
      `    && apt-get install -y --no-install-recommends ca-certificates python${pythonVersion} python${pythonVersion}-venv \\`,
      `    && python${pythonVersion} -m venv /opt/venv \\`,
      "    && rm -rf /var/lib/apt/lists/*",
    );
  } else {
    lines.push(
      "    && apt-get install -y --no-install-recommends build-essential ca-certificates curl libbz2-dev libffi-dev libgdbm-dev liblzma-dev libncursesw5-dev libreadline-dev libsqlite3-dev libssl-dev tk-dev uuid-dev zlib1g-dev \\",
      `    && curl --retry 5 --retry-all-errors --connect-timeout 30 -fsSL "\${PYTHON_SOURCE_BASE_URL}/${pythonPatchVersion}/Python-${pythonPatchVersion}.tgz" -o /tmp/python.tgz \\`,
      "    && mkdir -p /tmp/python-source \\",
      "    && tar -xzf /tmp/python.tgz --strip-components=1 -C /tmp/python-source \\",
      "    && cd /tmp/python-source \\",
      "    && ./configure --prefix=/opt/python --with-ensurepip=install \\",
      "    && make -j\"$(nproc)\" \\",
      "    && make install \\",
      `    && /opt/python/bin/python${pythonVersion} -m venv /opt/venv \\`,
      "    && rm -rf /tmp/python-source /tmp/python.tgz /var/lib/apt/lists/*",
    );
  }
  lines.push("", "ENV PATH=\"/opt/venv/bin:$PATH\"");

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

  for (const option of selected) {
    lines.push("", `# ${option.label}: ${option.description}`);
    if (option.id === "github-cli") {
      lines.push(
        "RUN apt-get update \\",
        "    && apt-get install -y --no-install-recommends wget \\",
        "    && mkdir -p -m 755 /etc/apt/keyrings \\",
        "    && wget -qO /etc/apt/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg \\",
        "    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \\",
        "    && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" > /etc/apt/sources.list.d/github-cli.list \\",
        "    && apt-get update \\",
        "    && apt-get install -y --no-install-recommends gh \\",
        "    && rm -rf /var/lib/apt/lists/*",
      );
    } else if (option.id === "opencli") {
      lines.push(
        "RUN apt-get update \\",
        "    && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \\",
        "    && node_arch=\"$(dpkg --print-architecture)\" \\",
        "    && case \"$node_arch\" in amd64) node_arch=x64 ;; arm64) node_arch=arm64 ;; *) echo \"Unsupported architecture: $node_arch\" >&2; exit 1 ;; esac \\",
        "    && curl --retry 5 --connect-timeout 30 -fsSL \"https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-${node_arch}.tar.xz\" -o /tmp/node.tar.xz \\",
        "    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \\",
        `    && npm install --global ${option.packageName} \\`,
        "    && npm cache clean --force \\",
        "    && rm -f /tmp/node.tar.xz \\",
        "    && rm -rf /var/lib/apt/lists/*",
      );
    } else if (option.id === "playwright") {
      lines.push("RUN python -m pip install --upgrade playwright");
      if (!selectedOptionIds.has("chromium")) {
        lines.push("RUN python -m playwright install --with-deps chromium");
      }
    } else if (option.id === "chromium") {
      if (!selectedOptionIds.has("playwright")) {
        lines.push("RUN python -m pip install --upgrade playwright");
      }
      lines.push("RUN python -m playwright install --with-deps chromium");
    } else if (option.installer === "apt") {
      lines.push(
        "RUN apt-get update \\",
        `    && apt-get install -y --no-install-recommends ${option.packageName} \\`,
        "    && rm -rf /var/lib/apt/lists/*",
      );
    } else {
      lines.push(`RUN python -m pip install --upgrade ${option.packageName}`);
    }
  }

  lines.push("", "CMD [\"/bin/bash\"]");
  return lines.join("\n");
}
