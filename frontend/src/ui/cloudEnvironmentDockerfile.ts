import type { CloudProvider } from "../adk/cloudProvider";
import type { CloudCliToolId } from "../create/types";

const AGENTKIT_BASE_IMAGES: Record<CloudProvider, string> = {
  volcengine:
    "agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest",
  byteplus:
    "agentkit-prod-public-ap-southeast-1.cr.bytepluses.com/base/py-simple:python3.12-bookworm-slim-latest",
};
const VOLCENGINE_PYPI_INDEXES = [
  "https://repo.huaweicloud.com/repository/pypi/simple",
  "https://mirrors.aliyun.com/pypi/simple/",
  "https://pypi.org/simple",
] as const;

const LARK_CLI_VERSION = "1.0.87";
const LARK_CLI_SHA256 = {
  amd64: "6027b1ddc12440400581bbdf9554850d8e119c7dd400439b1220e7a87b9673c5",
  arm64: "fade9a22d363172a9c18a8287c99c80d6d106a2900f3fce4015e4e156c5fc776",
};
const GITHUB_CLI_VERSION = "2.97.0";
const GITHUB_CLI_SHA256 = {
  amd64: "a2c9b8497e1f85b1ad0dfcb78b5a622e098801b8e461e459e88e1ee12f018112",
  arm64: "73ea440ecad9c9e284429997ee6f93577bc6f7bc6fba357ef62c53ad8fb641a5",
};

interface CliInstallOptions {
  assetName: string;
  version: string;
  checksums: Record<"amd64" | "arm64", string>;
  downloadUrls: string[];
  archiveMember: string;
  installSource: string;
  cleanupSource: string;
  binaryName: string;
}

function renderCliInstall(options: CliInstallOptions): string {
  const quotedDownloadUrls = options.downloadUrls
    .map((url) => `"${url}"`)
    .join(" ");
  return [
    "RUN set -eux; \\",
    '    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \\',
    '    case "$arch" in \\',
    `      amd64) checksum="${options.checksums.amd64}" ;; \\`,
    `      arm64) checksum="${options.checksums.arm64}" ;; \\`,
    '      *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \\',
    "    esac; \\",
    `    asset="${options.assetName}"; \\`,
    "    downloaded=0; \\",
    `    for base_url in ${quotedDownloadUrls}; do \\`,
    `      if curl -fLSs --connect-timeout 10 --max-time 180 --retry 1 --retry-delay 1 -o "/tmp/\${asset}" "\${base_url}/v${options.version}/\${asset}"; then downloaded=1; break; fi; \\`,
    "    done; \\",
    '    test "$downloaded" = 1; \\',
    '    echo "${checksum}  /tmp/${asset}" | sha256sum -c -; \\',
    `    tar -xzf "/tmp/\${asset}" -C /tmp "${options.archiveMember}"; \\`,
    `    install -m 0755 "${options.installSource}" "/usr/local/bin/${options.binaryName}"; \\`,
    `    rm -rf "/tmp/\${asset}" "${options.cleanupSource}"`,
  ].join("\n");
}

function githubReleaseUrls(
  cloudProvider: CloudProvider,
  repository: string,
): string[] {
  const official = `https://github.com/${repository}/releases/download`;
  const mirror = `https://ghfast.top/${official}`;
  return cloudProvider === "volcengine"
    ? [mirror, official]
    : [official, mirror];
}

function renderPythonDependencyInstall(cloudProvider: CloudProvider): string {
  if (cloudProvider !== "volcengine") {
    return "RUN uv pip install -r requirements.txt";
  }

  const attempts = VOLCENGINE_PYPI_INDEXES.map(
    (index) => `uv pip install --index-url ${index} -r requirements.txt`,
  );
  return `RUN ${attempts.join(" || \\\n    ")}`;
}

export function buildCloudEnvironmentDockerfile(
  cloudProvider: CloudProvider,
  cliTools: CloudCliToolId[],
): string {
  const selected = new Set(cliTools);
  const systemPackages = ["ca-certificates", "curl"];
  if (selected.has("github-cli")) systemPackages.push("git");
  if (selected.has("pandoc")) systemPackages.push("pandoc");
  const blocks = [
    `FROM ${AGENTKIT_BASE_IMAGES[cloudProvider]}`,
    "",
    "# Configure AgentKit runtime defaults.",
    "ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 DOCKER_CONTAINER=1",
    "ARG TARGETARCH",
    "",
    "# Install system dependencies required by the selected tools.",
    `RUN apt-get update && apt-get install -y --no-install-recommends ${systemPackages.join(" ")} && rm -rf /var/lib/apt/lists/*`,
  ];

  if (selected.has("lark-cli")) {
    blocks.push(
      "",
      "# Install Lark CLI from the official release archive.",
      renderCliInstall({
        assetName: `lark-cli-${LARK_CLI_VERSION}-linux-\${arch}.tar.gz`,
        version: LARK_CLI_VERSION,
        checksums: LARK_CLI_SHA256,
        downloadUrls: githubReleaseUrls(cloudProvider, "larksuite/cli"),
        archiveMember: "lark-cli",
        installSource: "/tmp/lark-cli",
        cleanupSource: "/tmp/lark-cli",
        binaryName: "lark-cli",
      }),
    );
  }

  if (selected.has("github-cli")) {
    blocks.push(
      "",
      "# Install GitHub CLI (gh) from the official release archive.",
      renderCliInstall({
        assetName: `gh_${GITHUB_CLI_VERSION}_linux_\${arch}.tar.gz`,
        version: GITHUB_CLI_VERSION,
        checksums: GITHUB_CLI_SHA256,
        downloadUrls: githubReleaseUrls(cloudProvider, "cli/cli"),
        archiveMember: `gh_${GITHUB_CLI_VERSION}_linux_\${arch}/bin/gh`,
        installSource: `/tmp/gh_${GITHUB_CLI_VERSION}_linux_\${arch}/bin/gh`,
        cleanupSource: `/tmp/gh_${GITHUB_CLI_VERSION}_linux_\${arch}`,
        binaryName: "gh",
      }),
    );
  }

  blocks.push(
    "",
    "# Install Python dependencies before copying the source for better layer caching.",
    "COPY requirements.txt requirements.txt",
    renderPythonDependencyInstall(cloudProvider),
    "",
    "# Copy the Agent application and configure its runtime entrypoint.",
    "EXPOSE 8000",
    "",
    "WORKDIR /app",
    "COPY . .",
    "",
    'CMD ["python", "-m", "app"]',
    "",
  );
  return blocks.join("\n");
}
