import {
  createGitHubPullRequest,
  normalizeRepositoryPath,
  type GitHubAutomationRegion,
} from "../adk/githubIntegration";
import type { CloudProvider } from "../adk/cloudProvider";
import {
  baseBranchField,
  cloudCredentialSecretLabels,
  cloudCredentialSecretNames,
  cloudProviderDisplayName,
  commonGitHubInput,
  initialAutomationValues,
  repositoryField,
  runtimeIdField,
  runtimeNameField,
} from "./githubFields";
import type { GitHubAutomationDefinition } from "./types";
import { runtimeNameProblem } from "../create/runtimeName";
import { automationT } from "./i18n";

interface RuntimeDeliveryWorkflowInput {
  baseBranch: string;
  projectPath: string;
  runtimeName: string;
  runtimeId: string;
  region: GitHubAutomationRegion;
  cloudProvider?: CloudProvider;
}

const RUNTIME_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const BYTEPLUS_VIKING_MEMORY_REGION = "cn-hongkong";

export function validateRuntimeSettings(
  input: Pick<RuntimeDeliveryWorkflowInput, "runtimeName" | "runtimeId">,
): void {
  const runtimeNameError = runtimeNameProblem(
    input.runtimeName,
    (key) => automationT(`github.validation.runtimeName.${key}`),
  );
  if (runtimeNameError) {
    throw new Error(runtimeNameError);
  }
  if (!RUNTIME_ID_PATTERN.test(input.runtimeId)) {
    throw new Error(automationT("github.validation.runtimeId"));
  }
}

export function buildRuntimeDeliveryWorkflow(input: RuntimeDeliveryWorkflowInput): string {
  validateRuntimeSettings(input);
  const cloudProvider = input.cloudProvider ?? "volcengine";
  const secrets = cloudCredentialSecretNames(cloudProvider);
  const byteplusEnv = cloudProvider === "byteplus"
    ? `
      VOLCENGINE_ACCESS_KEY: \${{ secrets.${secrets.accessKey} }}
      VOLCENGINE_SECRET_KEY: \${{ secrets.${secrets.secretKey} }}
      VOLCENGINE_SESSION_TOKEN: \${{ secrets.${secrets.sessionToken} }}
      BYTEPLUS_REGION: ${JSON.stringify(input.region)}`
    : "";
  const byteplusRuntimeEnv = cloudProvider === "byteplus"
    ? `
                          "DATABASE_VIKING_REGION": ${JSON.stringify(BYTEPLUS_VIKING_MEMORY_REGION)},`
    : "";
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
    if: \${{ github.event_name != 'push' || !contains(github.event.head_commit.message, '[skip runtime]') }}
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: __PROJECT_PATH__
    env:
      AGENTKIT_CLOUD_PROVIDER: __CLOUD_PROVIDER__
      CLOUD_PROVIDER: __CLOUD_PROVIDER__
      __ACCESS_KEY_SECRET__: \${{ secrets.__ACCESS_KEY_SECRET__ }}
      __SECRET_KEY_SECRET__: \${{ secrets.__SECRET_KEY_SECRET__ }}
      __SESSION_TOKEN_SECRET__: \${{ secrets.__SESSION_TOKEN_SECRET__ }}__BYTEPLUS_ENV__
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

          credential_prefix = (
              "BYTEPLUS"
              if os.environ["AGENTKIT_CLOUD_PROVIDER"] == "byteplus"
              else "VOLCENGINE"
          )
          runtime_client = AgentkitRuntimeClient(
              access_key=os.environ[f"{credential_prefix}_ACCESS_KEY"],
              secret_key=os.environ[f"{credential_prefix}_SECRET_KEY"],
              session_token=os.environ.get(f"{credential_prefix}_SESSION_TOKEN", ""),
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
                      "runtime_envs": {
                          "CLOUD_PROVIDER": os.environ["CLOUD_PROVIDER"],
                          "AGENTKIT_CLOUD_PROVIDER": os.environ["AGENTKIT_CLOUD_PROVIDER"],__BYTEPLUS_RUNTIME_ENV__
                      },
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
    __CLOUD_PROVIDER__: JSON.stringify(cloudProvider),
    __ACCESS_KEY_SECRET__: secrets.accessKey,
    __SECRET_KEY_SECRET__: secrets.secretKey,
    __SESSION_TOKEN_SECRET__: secrets.sessionToken,
    __BYTEPLUS_ENV__: byteplusEnv,
    __BYTEPLUS_RUNTIME_ENV__: byteplusRuntimeEnv,
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
  name: "AgentKit Runtime delivery",
  description: "Add a workflow that continuously delivers your repository to AgentKit Runtime.",
  title: "AgentKit Runtime delivery",
  subtitle: "Add continuous delivery to the repository through a pull request",
  panel: "This creates a release branch and opens a pull request containing the GitHub Actions workflow.",
  submitLabel: "Confirm and create PR",
  fields: [
    repositoryField,
    baseBranchField,
    {
      name: "projectPath",
      label: "Agent project directory",
      placeholder: ".",
      help: "Defaults to the repository root; the directory must contain an app.py that mounts the complete Studio App Server",
      required: false,
    },
    runtimeNameField,
    runtimeIdField,
  ],
  initialValues: ({ cloudProvider }) => initialAutomationValues(cloudProvider),
  regionHelp: "Must match the target Runtime region",
  secrets: ({ cloudProvider }) => cloudCredentialSecretLabels(cloudProvider),
  submit(values, context, signal) {
    const input = commonGitHubInput(values);
    const projectPath = normalizeRepositoryPath(values.projectPath, ".");
    const providerName = cloudProviderDisplayName(context.cloudProvider);
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
              cloudProvider: context.cloudProvider,
            }),
            commitMessage: "feat: publish Agent to AgentKit Runtime",
          },
        ],
        branchPrefix: "feat/agentkit-release",
        title: automationT("cards.delivery.pullRequest.title"),
        description: automationT("cards.delivery.pullRequest.description", { provider: providerName }),
      },
      signal,
    );
  },
};
