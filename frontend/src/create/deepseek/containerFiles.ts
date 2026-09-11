import type { ProjectFile } from "../project";
import { runtimeAdapter } from "./runtimeAdapter";
import type { CloudProvider } from "../../adk/cloudProvider";

export const DSH_PACKAGE_VERSION = "0.1.5-rc.1";

export function nativeContainerFiles(cloudProvider: CloudProvider = "volcengine"): ProjectFile[] {
  return [
    {
      path: "Dockerfile",
      content: `FROM node:24-bookworm AS deepseek-harness
ARG DEBIAN_MIRROR=${cloudProvider === "volcengine" ? "mirrors.aliyun.com" : "deb.debian.org"}

RUN sed -i "s|deb.debian.org|\$DEBIAN_MIRROR|g" /etc/apt/sources.list.d/debian.sources \\
    && apt-get update \\
    && apt-get install -y --no-install-recommends ripgrep tini \\
    && rm -rf /var/lib/apt/lists/*
RUN npm install --global @deepseek-ai/dsh@${DSH_PACKAGE_VERSION} \\
    && npm cache clean --force

FROM deepseek-harness
ENV NODE_ENV=production \\
    DSH_HOME=/home/node/.dsh \\
    PORT=8000
WORKDIR /workspace
RUN mkdir -p /home/node/.dsh /opt/agent /opt/application /workspace \\
    && chown -R node:node /home/node/.dsh /opt/agent /opt/application /workspace
COPY --chown=node:node settings.yaml container.patch.yml runtime.mjs /opt/agent/
COPY --chown=node:node --chmod=755 start.sh /opt/agent/start.sh
COPY --chown=node:node --chmod=755 start.sh /opt/application/run.sh
USER node
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \\
    CMD node -e "fetch('http://127.0.0.1:' + (process.env._FAAS_RUNTIME_PORT || process.env.PORT || '8000') + '/ping').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/agent/start.sh"]
`,
    },
    {
      path: "start.sh",
      content: `#!/bin/sh
set -eu

# Runtime launches the filesystem entry point without Docker image ENV
export PATH="/usr/local/bin:$PATH"
export DSH_HOME="\${DSH_HOME:-/home/node/.dsh}"
export NODE_ENV="\${NODE_ENV:-production}"
cd /workspace
mkdir -p "$DSH_HOME"
# The exported settings are the configuration for this container
cp /opt/agent/settings.yaml "$DSH_HOME/settings.yaml"
exec dsh --profile web --patch /opt/agent/container.patch.yml --no-open \\
  --port 3080 "$@"
`,
    },
    {
      path: "container.patch.yml",
      content: `# Keep the native web service private; AgentKit serves the invocation API
- id: webserver
  config:
    host: 127.0.0.1
    port: 3080
    compression: gzip
    compressionLevel: 1
    compressionThresholdBytes: 1024
- insert:
    - id: agentkit-runtime
      name: /opt/agent/runtime.mjs
`,
    },
    { path: "runtime.mjs", content: runtimeAdapter },
    { path: "agentkit.yaml", content: `common:\n  agent_name: deepseek-harness\n  entry_point: runtime.mjs\n  launch_type: cloud\nlaunch_types:\n  cloud:\n    region: ${cloudProvider === "byteplus" ? "ap-southeast-1" : "cn-beijing"}\n` },
    {
      path: ".dockerignore",
      content: `**
!Dockerfile
!settings.yaml
!container.patch.yml
!start.sh
!runtime.mjs
`,
    },
  ];
}
