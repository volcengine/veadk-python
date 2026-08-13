import {
  createGitHubPullRequest,
  normalizeRepositoryPath,
  type GitHubAutomationRegion,
} from "../adk/githubIntegration";
import {
  baseBranchField,
  commonGitHubInput,
  initialAutomationValues,
  repositoryField,
  runtimeIdField,
  runtimeNameField,
} from "./githubFields";
import type { GitHubAutomationDefinition } from "./types";
import { runtimeNameProblem } from "../create/runtimeName";

interface RuntimeDeliveryWorkflowInput {
  baseBranch: string;
  projectPath: string;
  runtimeName: string;
  runtimeId: string;
  region: GitHubAutomationRegion;
}

const RUNTIME_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export function validateRuntimeSettings(
  input: Pick<RuntimeDeliveryWorkflowInput, "runtimeName" | "runtimeId">,
): void {
  const runtimeNameError = runtimeNameProblem(input.runtimeName);
  if (runtimeNameError) {
    throw new Error(runtimeNameError);
  }
  if (!RUNTIME_ID_PATTERN.test(input.runtimeId)) {
    throw new Error("Runtime ID 格式不正确");
  }
}

export function buildRuntimeDeliveryWorkflow(input: RuntimeDeliveryWorkflowInput): string {
  validateRuntimeSettings(input);
  const template = `name: Publish to AgentKit Runtime

on:
  push:
    branches:
      - __BASE_BRANCH__
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: __CONCURRENCY_GROUP__
  cancel-in-progress: true

jobs:
  publish:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: __PROJECT_PATH__
    env:
      AGENTKIT_CLOUD_PROVIDER: volcengine
      VOLC_ACCESSKEY: \${{ secrets.VOLCENGINE_ACCESS_KEY }}
      VOLC_SECRETKEY: \${{ secrets.VOLCENGINE_SECRET_KEY }}
      VOLC_SESSIONTOKEN: \${{ secrets.VOLCENGINE_SESSION_TOKEN }}
      AGENTKIT_RUNTIME_NAME: __RUNTIME_NAME__
      AGENTKIT_RUNTIME_ID: __RUNTIME_ID__
      AGENTKIT_REGION: __REGION__
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install project and AgentKit SDK
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then python -m pip install -r requirements.txt; fi
          python -m pip install "agentkit-sdk-python>=0.8.0"
      - name: Publish Runtime
        shell: bash
        run: |
          python - <<'PY'
          import os
          from pathlib import Path

          import yaml
          from agentkit.sdk.runtime import types as runtime_types
          from agentkit.sdk.runtime.client import AgentkitRuntimeClient
          from agentkit.toolkit import sdk
          from agentkit.toolkit.models import PreflightMode

          runtime_client = AgentkitRuntimeClient(
              access_key=os.environ["VOLC_ACCESSKEY"],
              secret_key=os.environ["VOLC_SECRETKEY"],
              session_token=os.environ.get("VOLC_SESSIONTOKEN", ""),
              region=os.environ["AGENTKIT_REGION"],
          )
          runtime = runtime_client.get_runtime(
              runtime_types.GetRuntimeRequest(
                  runtime_id=os.environ["AGENTKIT_RUNTIME_ID"],
              )
          )
          runtime_name = getattr(runtime, "name", "") or os.environ["AGENTKIT_RUNTIME_NAME"]
          runtime_role_name = getattr(runtime, "role_name", "") or "Auto"
          next_version = (getattr(runtime, "current_version_number", 0) or 0) + 1

          config = {
              "common": {
                  "agent_name": runtime_name,
                  "entry_point": "app.py",
                  "description": "Continuously published from GitHub",
                  "python_version": "3.12",
                  "launch_type": "cloud",
              },
              "launch_types": {
                  "cloud": {
                      "region": os.environ["AGENTKIT_REGION"],
                      "project_name": "default",
                      "image_tag": f"veadk-v{next_version}",
                      "runtime_id": os.environ["AGENTKIT_RUNTIME_ID"],
                      "runtime_name": runtime_name,
                      "runtime_role_name": runtime_role_name,
                      "python_version": "3.12",
                  }
              },
          }
          config_path = Path("agentkit.yaml")
          config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
          result = sdk.launch(
              config_file=str(config_path),
              preflight_mode=PreflightMode.WARN,
          )
          if not result.success:
              raise SystemExit(f"AgentKit publish failed: {result.error}")
          PY
`;
  const replacements: Record<string, string> = {
    __BASE_BRANCH__: JSON.stringify(input.baseBranch),
    __PROJECT_PATH__: JSON.stringify(input.projectPath),
    __RUNTIME_NAME__: JSON.stringify(input.runtimeName),
    __RUNTIME_ID__: JSON.stringify(input.runtimeId),
    __REGION__: JSON.stringify(input.region),
    __CONCURRENCY_GROUP__: JSON.stringify(`agentkit-runtime-${input.runtimeId}`),
  };
  return Object.entries(replacements).reduce(
    (workflow, [key, value]) => workflow.split(key).join(value),
    template,
  );
}

export const runtimeDeliveryAutomation: GitHubAutomationDefinition = {
  id: "delivery",
  kind: "github",
  category: "development",
  icon: "github",
  name: "AgentKit Runtime 持续交付",
  description: "为您的仓库添加持续交付到 AgentKit Runtime 的自动化工作流。",
  title: "AgentKit Runtime 持续交付",
  subtitle: "用 Pull Request 把持续发布配置安全地加入代码仓库",
  panel: "提交后将在目标仓库创建发布分支，并发起包含 GitHub Actions 工作流的 PR。",
  submitLabel: "确定并提交 PR",
  fields: [
    repositoryField,
    baseBranchField,
    {
      name: "projectPath",
      label: "Agent 项目目录",
      placeholder: ".",
      help: "留空时使用仓库根目录；目录内需包含挂载完整 Studio App Server 的 app.py",
      required: false,
    },
    runtimeNameField,
    runtimeIdField,
  ],
  initialValues: initialAutomationValues(),
  regionHelp: "必须与目标 Runtime 所在地域一致",
  secrets: [
    "VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY（必填）",
    "VOLCENGINE_SESSION_TOKEN（使用临时凭据时必填）",
  ],
  submit(values, signal) {
    const input = commonGitHubInput(values);
    const projectPath = normalizeRepositoryPath(values.projectPath, ".");
    return createGitHubPullRequest(
      {
        ...input,
        files: [
          {
            path: ".github/workflows/publish-agentkit.yml",
            content: buildRuntimeDeliveryWorkflow({
              baseBranch: input.baseBranch,
              projectPath,
              runtimeName: values.runtimeName.trim(),
              runtimeId: values.runtimeId.trim(),
              region: input.region,
            }),
            commitMessage: "feat: publish Agent to AgentKit Runtime",
          },
        ],
        branchPrefix: "feat/agentkit-release",
        title: "feat: 持续发布到 AgentKit Runtime",
        description: "新增 GitHub Actions 工作流，在目标分支更新时持续发布到 AgentKit Runtime。合并前请配置工作流所需的 Volcengine Secrets。",
      },
      signal,
    );
  },
};
