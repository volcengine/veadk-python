"""AgentKit Runtime continuous-delivery automation."""

from __future__ import annotations

import json

from veadk.cli.github_automations._shared import (
    AutomationPullRequest,
    PullRequestFile,
    RuntimePullRequestBody,
    validate_runtime,
)

_WORKFLOW_PATH = ".github/workflows/publish-agentkit.yml"


class RuntimeDeliveryBody(RuntimePullRequestBody):
    """Configuration submitted by the Runtime delivery card."""


def runtime_delivery_workflow(
    *,
    base_branch: str,
    project_path: str,
    runtime_name: str,
    runtime_id: str,
    region: str,
    entry_point: str = "app.py",
    runtime_env_secrets: dict[str, str] | None = None,
) -> str:
    runtime_env_secrets = runtime_env_secrets or {}
    job_env = "\n".join(
        f"      {name}: ${{{{ secrets.{secret_name} }}}}"
        for name, secret_name in runtime_env_secrets.items()
    )
    template = """name: Publish to AgentKit Runtime

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
      VOLC_ACCESSKEY: ${{ secrets.VOLCENGINE_ACCESS_KEY }}
      VOLC_SECRETKEY: ${{ secrets.VOLCENGINE_SECRET_KEY }}
      VOLC_SESSIONTOKEN: ${{ secrets.VOLCENGINE_SESSION_TOKEN }}
      AGENTKIT_RUNTIME_NAME: __RUNTIME_NAME__
      AGENTKIT_RUNTIME_ID: __RUNTIME_ID__
      AGENTKIT_REGION: __REGION__
__JOB_ENV__
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
          runtime_env_names = __RUNTIME_ENV_NAMES__
          runtime_envs = {name: os.environ[name] for name in runtime_env_names}

          config = {
              "common": {
                  "agent_name": runtime_name,
                  "entry_point": __ENTRY_POINT__,
                  "description": "Continuously published from GitHub",
                  "python_version": "3.12",
                  "runtime_envs": runtime_envs,
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
                      "runtime_envs": runtime_envs,
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
"""
    replacements = {
        "__BASE_BRANCH__": json.dumps(base_branch),
        "__PROJECT_PATH__": json.dumps(project_path),
        "__RUNTIME_NAME__": json.dumps(runtime_name),
        "__RUNTIME_ID__": json.dumps(runtime_id),
        "__REGION__": json.dumps(region),
        "__ENTRY_POINT__": json.dumps(entry_point),
        "__CONCURRENCY_GROUP__": json.dumps(f"agentkit-runtime-{runtime_id}"),
        "__RUNTIME_ENV_NAMES__": json.dumps(list(runtime_env_secrets)),
        "__JOB_ENV__": job_env,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def build_runtime_delivery(body: RuntimeDeliveryBody) -> AutomationPullRequest:
    repository, project_path = validate_runtime(body)
    workflow = runtime_delivery_workflow(
        base_branch=body.base_branch,
        project_path=project_path,
        runtime_name=body.runtime_name,
        runtime_id=body.runtime_id,
        region=body.region,
    )
    return AutomationPullRequest(
        repository=repository,
        files=(
            PullRequestFile(
                path=_WORKFLOW_PATH,
                content=workflow,
                commit_message="feat: publish Agent to AgentKit Runtime",
            ),
        ),
        branch_prefix="feat/agentkit-release",
        title="feat: 持续发布到 AgentKit Runtime",
        description=(
            "新增 GitHub Actions 工作流，在目标分支更新时持续发布到 "
            "AgentKit Runtime。合并前请配置工作流所需的 Volcengine Secrets。"
        ),
    )
