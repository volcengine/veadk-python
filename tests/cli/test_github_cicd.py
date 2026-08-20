# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.cli import veadk
from veadk.cli.cli_frontend import _run_frontend_server


PROJECT = {
    "name": "demo_agent",
    "files": [
        {"path": "app.py", "content": "app = object()\n"},
        {"path": "requirements.txt", "content": "veadk-python\n"},
    ],
}
VOLCENGINE_CREDENTIALS = {
    "volcengine_access_key": "ak_test",
    "volcengine_secret_key": "sk_test",
    "volcengine_session_token": "token_test",
}


def test_parse_github_repo_url_accepts_common_forms() -> None:
    from veadk.cli.github_cicd import parse_github_repo_url

    assert parse_github_repo_url("https://github.com/acme/demo") == ("acme", "demo")
    assert parse_github_repo_url("https://github.com/acme/demo.git") == (
        "acme",
        "demo",
    )
    assert parse_github_repo_url("git@github.com:acme/demo.git") == (
        "acme",
        "demo",
    )


def test_create_github_cicd_pipeline_pushes_source_without_pr_or_runtime(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import create_github_cicd_pipeline

    github = FakeGitHubClient()

    result = create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=github,
        state_path=tmp_path / "state.json",
    )

    assert result["pipelineId"] == "github-acme-demo-main"
    assert result["github"]["branch"] == "main"
    assert result["github"]["commitSha"] == "commit-1"
    assert result["github"]["pullRequestUrl"] == ""
    assert result["github"]["pullRequestNumber"] == 0
    assert result["status"] == "succeeded"
    assert result["phase"] == "ready"
    assert isinstance(result["updatedAt"], str)
    assert "deployment" not in result
    assert github.created_branch is None
    assert github.committed_files == PROJECT["files"]
    assert github.pull_request is None

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["github-acme-demo-main"]["status"] == "succeeded"
    assert state["github-acme-demo-main"]["phase"] == "ready"
    assert state["github-acme-demo-main"]["runtimeId"] == ""
    assert state["github-acme-demo-main"]["githubToken"] == "ghp_secret"


def test_create_github_cicd_pipeline_reports_progress(tmp_path: Path) -> None:
    from veadk.cli.github_cicd import create_github_cicd_pipeline

    events: list[str] = []

    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=FakeGitHubClient(),
        state_path=tmp_path / "state.json",
        progress=events.append,
    )

    assert events == [
        "Validating AgentProject...",
        "Connecting GitHub repo acme/demo...",
        "Pushing 2 file(s) to main...",
        "Saving GitHub source sync state...",
        "GitHub source sync ready.",
    ]


def test_create_github_delivery_cicd_pipeline_writes_workflow_to_target_branch(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import create_github_delivery_cicd_pipeline

    github = FakeCicdGitHubClient()

    result = create_github_delivery_cicd_pipeline(
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        project_path=".",
        **VOLCENGINE_CREDENTIALS,
        github_client=github,
        state_path=tmp_path / "state.json",
    )

    assert result["pipelineId"] == "github-acme-demo-main"
    assert result["status"] == "cicd-bound"
    assert result["phase"] == "ready"
    assert result["runtimeId"] == "rt-created"
    assert result["github"]["branch"] == "main"
    assert result["github"]["pullRequestUrl"] == ""
    assert result["github"]["pullRequestNumber"] == 0
    assert result["cicd"]["enabled"] is True
    assert result["cicd"]["workflowPath"] == ".github/workflows/publish-agentkit.yml"
    assert github.created_branch is None
    assert github.pull_request is None
    assert github.committed_files[0]["path"] == ".github/workflows/publish-agentkit.yml"
    assert "rt-created" in github.committed_files[0]["content"]
    assert "Publish to AgentKit Runtime" in github.committed_files[0]["content"]
    assert github.actions_secrets == {
        "VOLCENGINE_ACCESS_KEY": "ak_test",
        "VOLCENGINE_SECRET_KEY": "sk_test",
        "VOLCENGINE_SESSION_TOKEN": "token_test",
    }

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    record = state["github-acme-demo-main"]
    assert record["runtimeId"] == "rt-created"
    assert record["cicdEnabled"] is True
    assert record["workflowPath"] == ".github/workflows/publish-agentkit.yml"
    assert record["githubToken"] == "ghp_secret"


def test_create_github_delivery_cicd_pipeline_writes_byteplus_provider_workflow(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import create_github_delivery_cicd_pipeline

    github = FakeCicdGitHubClient()

    result = create_github_delivery_cicd_pipeline(
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="bp-agent",
        runtime_id="rt-byteplus",
        region="ap-southeast-1",
        cloud_provider="byteplus",
        project_path=".",
        **VOLCENGINE_CREDENTIALS,
        github_client=github,
        state_path=tmp_path / "state.json",
    )

    workflow = github.committed_files[0]["content"]
    assert 'AGENTKIT_CLOUD_PROVIDER: "byteplus"' in workflow
    assert 'CLOUD_PROVIDER: "byteplus"' in workflow
    assert 'AGENTKIT_REGION: "ap-southeast-1"' in workflow
    assert '"CLOUD_PROVIDER": os.environ["CLOUD_PROVIDER"]' in workflow
    assert '"DATABASE_VIKING_REGION": "cn-hongkong"' in workflow
    assert "AGENTKIT_CLOUD_PROVIDER: volcengine" not in workflow
    assert "BYTEPLUS_ACCESS_KEY: ${{ secrets.BYTEPLUS_ACCESS_KEY }}" in workflow
    assert "VOLCENGINE_ACCESS_KEY: ${{ secrets.BYTEPLUS_ACCESS_KEY }}" in workflow
    assert "credential_prefix = (" in workflow
    assert result["cloudProvider"] == "byteplus"
    assert github.actions_secrets == {
        "BYTEPLUS_ACCESS_KEY": "ak_test",
        "BYTEPLUS_SECRET_KEY": "sk_test",
        "BYTEPLUS_SESSION_TOKEN": "token_test",
    }

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["github-acme-demo-main"]["cloudProvider"] == "byteplus"


def test_initialize_github_delivery_main_commits_source_and_workflow_to_main(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import initialize_github_delivery_main

    github = FakeMainDeliveryGitHubClient()

    result = initialize_github_delivery_main(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        project_path=".",
        **VOLCENGINE_CREDENTIALS,
        github_client=github,
        state_path=tmp_path / "state.json",
    )

    assert result["pipelineId"] == "github-acme-demo-main"
    assert result["status"] == "cicd-bound"
    assert result["phase"] == "ready"
    assert result["runtimeId"] == "rt-created"
    assert result["github"]["branch"] == "main"
    assert result["github"]["pullRequestUrl"] == ""
    assert result["github"]["commitSha"] == "main-init-commit"
    assert result["cicd"]["enabled"] is True
    assert result["cicd"]["workflowPath"] == ".github/workflows/publish-agentkit.yml"
    assert github.created_branch is None
    assert github.pull_request is None
    assert [item["path"] for item in github.committed_files] == [
        "app.py",
        "requirements.txt",
        ".github/workflows/publish-agentkit.yml",
    ]
    assert "[skip runtime]" in github.commit_message
    assert (
        "contains(github.event.head_commit.message, '[skip runtime]')"
        in github.committed_files[-1]["content"]
    )
    assert github.actions_secrets == {
        "VOLCENGINE_ACCESS_KEY": "ak_test",
        "VOLCENGINE_SECRET_KEY": "sk_test",
        "VOLCENGINE_SESSION_TOKEN": "token_test",
    }
    assert "VOLC_ACCESSKEY" not in github.committed_files[-1]["content"]
    assert "VOLCENGINE_ACCESS_KEY" in github.committed_files[-1]["content"]

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    record = state["github-acme-demo-main"]
    assert record["branch"] == "main"
    assert record["cicdEnabled"] is True
    assert record["runtimeId"] == "rt-created"
    assert record["versions"][0]["commitSha"] == "main-init-commit"
    assert record["versions"][0]["source"] == "github-cicd"
    assert record["versions"][0]["pullRequestUrl"] == ""


def test_github_client_initializes_empty_repository_branch() -> None:
    from veadk.cli.github_cicd import GitHubClient

    session = FakeEmptyRepoSession()

    commit_sha = GitHubClient("ghp_secret", session=session).commit_files(
        "acme",
        "demo",
        branch="main",
        files=PROJECT["files"],
        message="Studio: initialize empty repo",
    )

    assert commit_sha == "empty-commit"
    tree_request = session.request_json("POST", "/repos/acme/demo/git/trees")
    assert "base_tree" not in tree_request
    commit_request = session.request_json("POST", "/repos/acme/demo/git/commits")
    assert commit_request["parents"] == []
    ref_request = session.request_json("POST", "/repos/acme/demo/git/refs")
    assert ref_request == {"ref": "refs/heads/main", "sha": "empty-commit"}
    assert not session.has_request("PATCH", "/repos/acme/demo/git/refs/heads/main")


def test_list_github_delivery_versions_returns_recorded_versions(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        initialize_github_delivery_main,
        list_github_delivery_versions,
    )

    state_path = tmp_path / "state.json"
    initialize_github_delivery_main(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        **VOLCENGINE_CREDENTIALS,
        github_client=FakeMainDeliveryGitHubClient(),
        state_path=state_path,
    )

    result = list_github_delivery_versions(
        runtime_id="rt-created",
        state_path=state_path,
    )

    assert result["runtimeId"] == "rt-created"
    assert result["github"]["branch"] == "main"
    assert result["currentCommitSha"] == "main-init-commit"
    assert result["versions"][0]["version"] == "v1"
    assert result["versions"][0]["commitSha"] == "main-init-commit"
    assert result["versions"][0]["status"] == "current"


def test_list_github_delivery_versions_reads_main_branch_commits(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        initialize_github_delivery_main,
        list_github_delivery_versions,
    )

    state_path = tmp_path / "state.json"
    initialize_github_delivery_main(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        **VOLCENGINE_CREDENTIALS,
        github_client=FakeMainDeliveryGitHubClient(),
        state_path=state_path,
    )

    result = list_github_delivery_versions(
        runtime_id="rt-created",
        github_client=FakeVersionGitHubClient(),
        state_path=state_path,
    )

    assert result["currentCommitSha"] == "github-commit-2"
    assert result["runtimeStatus"] == "published"
    assert [item["commitSha"] for item in result["versions"][:2]] == [
        "github-commit-3",
        "github-commit-2",
    ]
    assert result["versions"][0]["version"] == "v3"
    assert result["versions"][0]["author"] == "CatherineKu"
    assert result["versions"][0]["description"] == "feat: add pending tool"
    assert (
        result["versions"][0]["pullRequestUrl"] == "https://github.com/acme/demo/pull/8"
    )
    assert result["versions"][0]["runtimeStatus"] == "publishing"
    assert result["versions"][0]["status"] == "publishing"
    assert result["versions"][1]["version"] == "v2"
    assert result["versions"][1]["author"] == "CatherineKu"
    assert result["versions"][1]["description"] == "feat: add version probe"
    assert (
        result["versions"][1]["pullRequestUrl"] == "https://github.com/acme/demo/pull/7"
    )
    assert result["versions"][1]["runtimeStatus"] == "published"
    assert result["versions"][1]["status"] == "current"


def test_list_github_delivery_versions_skips_workflow_runs_for_source_only_binding(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        bind_github_cicd_runtime,
        create_github_cicd_pipeline,
        list_github_delivery_versions,
    )

    state_path = tmp_path / "state.json"
    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=FakeGitHubClient(commit_sha="source-commit"),
        state_path=state_path,
    )
    bind_github_cicd_runtime(
        pipeline_id="github-acme-demo-main",
        runtime_id="rt-source-only",
        region="cn-beijing",
        state_path=state_path,
    )
    github = FakeSourceOnlyVersionGitHubClient()

    result = list_github_delivery_versions(
        runtime_id="rt-source-only",
        github_client=github,
        state_path=state_path,
    )

    assert github.workflow_runs_called is False
    assert result["cicd"]["enabled"] is False
    assert "githubSyncError" not in result
    assert result["versions"][0]["commitSha"] == "source-commit"
    assert result["versions"][0]["runtimeStatus"] == "published"


def test_create_github_delivery_rollback_pr_uses_target_commit(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        create_github_delivery_rollback_pr,
        initialize_github_delivery_main,
    )

    state_path = tmp_path / "state.json"
    initialize_github_delivery_main(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        **VOLCENGINE_CREDENTIALS,
        github_client=FakeMainDeliveryGitHubClient(),
        state_path=state_path,
    )
    github = FakeRollbackGitHubClient()

    result = create_github_delivery_rollback_pr(
        runtime_id="rt-created",
        target_commit_sha="main-init-commit",
        github_client=github,
        state_path=state_path,
    )

    assert result["runtimeId"] == "rt-created"
    assert result["status"] == "rollback-merged"
    assert result["github"]["branch"] == "main"
    assert result["github"]["pullRequestUrl"] == "https://github.com/acme/demo/pull/9"
    assert result["github"]["commitSha"] == "rollback-merge-commit"
    assert result["rollback"]["commitSha"] == "rollback-merge-commit"
    assert result["rollback"]["targetCommitSha"] == "main-init-commit"
    assert result["rollback"]["runtimeStatus"] == "publishing"
    assert github.rollback_request == (
        "main",
        "main-init-commit",
        "studio/rollback-main-ini",
    )
    assert github.merged_pull_request == 9
    state = json.loads(state_path.read_text(encoding="utf-8"))
    record = state["github-acme-demo-main"]
    assert record["versions"][0]["commitSha"] == "main-init-commit"
    assert record["rollbackEvents"][0]["commitSha"] == "rollback-merge-commit"
    assert record["rollbackEvents"][0]["targetCommitSha"] == "main-init-commit"


def test_list_github_delivery_versions_marks_rollback_as_event(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        create_github_delivery_rollback_pr,
        initialize_github_delivery_main,
        list_github_delivery_versions,
    )

    state_path = tmp_path / "state.json"
    initialize_github_delivery_main(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        **VOLCENGINE_CREDENTIALS,
        github_client=FakeMainDeliveryGitHubClient(),
        state_path=state_path,
    )
    create_github_delivery_rollback_pr(
        runtime_id="rt-created",
        target_commit_sha="main-init-commit",
        github_client=FakeRollbackGitHubClient(),
        state_path=state_path,
    )

    result = list_github_delivery_versions(
        runtime_id="rt-created",
        github_client=FakeRollbackVersionGitHubClient(),
        state_path=state_path,
    )

    assert result["currentCommitSha"] == "main-init-commit"
    assert result["runtimeStatus"] == "published"
    assert result["versions"][0]["changeType"] == "rollback"
    assert result["versions"][0]["version"] == "回退事件"
    assert result["versions"][0]["runtimeStatus"] == "published"
    assert result["versions"][0]["rollbackTargetCommitSha"] == "main-init-commit"
    assert result["versions"][1]["commitSha"] == "main-init-commit"
    assert result["versions"][1]["status"] == "current"


def test_attach_github_delivery_cicd_pipeline_uses_existing_source_sync_branch(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        attach_github_delivery_cicd_pipeline,
        create_github_cicd_pipeline,
    )

    state_path = tmp_path / "state.json"
    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=FakeGitHubClient(),
        state_path=state_path,
    )
    github = FakeGitHubClient(commit_sha="workflow-commit")

    result = attach_github_delivery_cicd_pipeline(
        pipeline_id="github-acme-demo-main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        project_path=".",
        **VOLCENGINE_CREDENTIALS,
        github_client=github,
        state_path=state_path,
    )

    assert result["pipelineId"] == "github-acme-demo-main"
    assert result["runtimeId"] == "rt-created"
    assert result["status"] == "cicd-bound"
    assert result["github"]["branch"] == "main"
    assert result["github"]["pullRequestUrl"] == ""
    assert result["github"]["pullRequestNumber"] == 0
    assert result["github"]["commitSha"] == "workflow-commit"
    assert result["cicd"]["enabled"] is True
    assert github.created_branch is None
    assert github.pull_request is None
    assert github.committed_files[0]["path"] == ".github/workflows/publish-agentkit.yml"
    assert "rt-created" in github.committed_files[0]["content"]
    assert github.actions_secrets["VOLCENGINE_ACCESS_KEY"] == "ak_test"
    assert github.actions_secrets["VOLCENGINE_SECRET_KEY"] == "sk_test"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    record = state["github-acme-demo-main"]
    assert record["runtimeId"] == "rt-created"
    assert record["cicdEnabled"] is True
    assert record["workflowPath"] == ".github/workflows/publish-agentkit.yml"


def test_bind_github_cicd_pipeline_to_runtime(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        bind_github_cicd_runtime,
        create_github_cicd_pipeline,
    )

    state_path = tmp_path / "state.json"
    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=FakeGitHubClient(),
        state_path=state_path,
    )

    binding = bind_github_cicd_runtime(
        pipeline_id="github-acme-demo-main",
        runtime_id="rt-created",
        region="cn-beijing",
        state_path=state_path,
    )

    assert binding["runtimeId"] == "rt-created"
    assert binding["github"]["pullRequestUrl"] == ""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["github-acme-demo-main"]["runtimeId"] == "rt-created"


def test_sync_github_cicd_runtime_pushes_bound_source_branch(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        bind_github_cicd_runtime,
        create_github_cicd_pipeline,
        sync_github_cicd_runtime,
    )

    state_path = tmp_path / "state.json"
    first_github = FakeGitHubClient(commit_sha="commit-1")
    second_github = FakeGitHubClient(commit_sha="commit-2")

    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=first_github,
        state_path=state_path,
    )
    bind_github_cicd_runtime(
        pipeline_id="github-acme-demo-main",
        runtime_id="rt-created",
        region="cn-beijing",
        state_path=state_path,
    )

    result = sync_github_cicd_runtime(
        runtime_id="rt-created",
        project=PROJECT,
        github_client=second_github,
        state_path=state_path,
    )

    assert result["github"]["commitSha"] == "commit-2"
    assert result["github"]["branch"] == "main"
    assert result["github"]["pullRequestUrl"] == ""
    assert result["runtimeId"] == "rt-created"
    assert second_github.committed_files == PROJECT["files"]
    assert second_github.pull_request is None


def test_sync_github_cicd_runtime_preserves_cicd_binding(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        attach_github_delivery_cicd_pipeline,
        create_github_cicd_pipeline,
        sync_github_cicd_runtime,
    )

    state_path = tmp_path / "state.json"
    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=FakeGitHubClient(),
        state_path=state_path,
    )
    attach_github_delivery_cicd_pipeline(
        pipeline_id="github-acme-demo-main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        project_path=".",
        **VOLCENGINE_CREDENTIALS,
        github_client=FakeGitHubClient(commit_sha="workflow-commit"),
        state_path=state_path,
    )

    result = sync_github_cicd_runtime(
        runtime_id="rt-created",
        project=PROJECT,
        github_client=FakeGitHubClient(commit_sha="source-commit"),
        state_path=state_path,
    )

    assert result["runtimeId"] == "rt-created"
    assert result["github"]["commitSha"] == "source-commit"
    assert result["github"]["branch"] == "main"
    assert result["github"]["pullRequestUrl"] == ""
    assert result["cicd"]["enabled"] is True
    assert result["cicd"]["workflowPath"] == ".github/workflows/publish-agentkit.yml"


def test_sync_github_cicd_runtime_submits_code_when_cicd_bound(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import (
        initialize_github_delivery_main,
        sync_github_cicd_runtime,
    )

    state_path = tmp_path / "state.json"
    initialize_github_delivery_main(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        runtime_name="demo-agent",
        runtime_id="rt-created",
        region="cn-beijing",
        **VOLCENGINE_CREDENTIALS,
        github_client=FakeMainDeliveryGitHubClient(),
        state_path=state_path,
    )
    github = FakeAutoMergeGitHubClient(commit_sha="source-commit")

    result = sync_github_cicd_runtime(
        runtime_id="rt-created",
        project=PROJECT,
        github_client=github,
        state_path=state_path,
    )

    assert result["runtimeId"] == "rt-created"
    assert result["status"] == "submitted"
    assert result["github"]["branch"] == "main"
    assert result["github"]["commitSha"] == "source-commit"
    assert result["github"]["pullRequestUrl"] == ""
    assert github.pull_request is None
    assert github.merged_pull_request is None

    state = json.loads(state_path.read_text(encoding="utf-8"))
    record = state["github-acme-demo-main"]
    assert record["latestCommitSha"] == "source-commit"
    assert record["versions"][0]["commitSha"] == "source-commit"
    assert record["versions"][0]["status"] == "submitted"
    assert record["versions"][0]["source"] == "github-cicd"


def test_sync_github_cicd_runtime_requires_bound_runtime(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import GitHubCicdError, sync_github_cicd_runtime

    with pytest.raises(GitHubCicdError) as exc:
        sync_github_cicd_runtime(
            runtime_id="rt-missing",
            project=PROJECT,
            state_path=tmp_path / "state.json",
        )

    assert exc.value.phase == "binding"
    assert "not bound" in str(exc.value)


def test_github_cicd_pipeline_cli_reads_project_json_and_runs_github_cicd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_github_cicd_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        kwargs["progress"]("Testing progress output...")
        return {
            "pipelineId": "github-acme-demo-studio-demo-agent",
            "status": "succeeded",
            "phase": "ready",
            "github": {"pullRequestUrl": "https://github.com/acme/demo/pull/1"},
        }

    monkeypatch.setattr(
        "veadk.cli.cli_github_cicd_pipeline.create_github_cicd_pipeline",
        fake_create_github_cicd_pipeline,
    )
    project_json = tmp_path / "agent-project.json"
    project_json.write_text(json.dumps(PROJECT), encoding="utf-8")

    result = CliRunner().invoke(
        veadk,
        [
            "github-cicd-pipeline",
            "--github-url",
            "https://github.com/acme/demo",
            "--github-token",
            "ghp_secret",
            "--github-branch",
            "main",
            "--project-json",
            str(project_json),
            "--region",
            "cn-beijing",
        ],
    )

    assert result.exit_code == 0
    assert captured["project"] == PROJECT
    assert captured["github_url"] == "https://github.com/acme/demo"
    assert captured["github_token"] == "ghp_secret"
    assert captured["base_branch"] == "main"
    assert captured["region"] == "cn-beijing"
    assert callable(captured["progress"])
    assert "[github-cicd] Testing progress output..." in result.output
    assert "ghp_secret" not in result.output
    assert "github-acme-demo-studio-demo-agent" in result.output
    assert '"status": "succeeded"' in result.output


def test_studio_endpoint_creates_github_cicd_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_create_github_cicd_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "pipelineId": "github-acme-demo-studio-demo-agent",
            "status": "succeeded",
            "phase": "ready",
            "github": {"branch": "studio/demo-agent"},
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.create_github_cicd_pipeline",
        fake_create_github_cicd_pipeline,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/source-sync",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "region": "cn-beijing",
            },
        )

    assert response.status_code == 200
    assert response.json()["pipelineId"] == "github-acme-demo-studio-demo-agent"
    assert response.json()["status"] == "succeeded"
    assert captured["project"] == PROJECT
    assert captured["github_url"] == "https://github.com/acme/demo"
    assert captured["github_token"] == "ghp_secret"
    assert captured["base_branch"] == "main"
    assert captured["region"] == "cn-beijing"


def test_studio_legacy_github_cicd_pipeline_endpoint_is_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        response = client.post(
            "/web/github-cicd/pipelines",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "region": "cn-beijing",
            },
        )

    assert response.status_code == 404


def test_studio_source_pr_endpoint_is_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/source-pr",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "region": "cn-beijing",
            },
        )

    assert response.status_code == 404


def test_studio_endpoint_creates_github_delivery_cicd_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_create_github_delivery_cicd_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "pipelineId": "github-acme-demo-cicd-rt-1",
            "status": "cicd-bound",
            "phase": "ready",
            "runtimeId": "rt-1",
            "github": {
                "branch": "studio/cicd-rt-1",
                "pullRequestUrl": "https://github.com/acme/demo/pull/2",
            },
            "cicd": {
                "enabled": True,
                "workflowPath": ".github/workflows/publish-agentkit.yml",
            },
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.create_github_delivery_cicd_pipeline",
        fake_create_github_delivery_cicd_pipeline,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/cicd-pipeline",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "runtimeName": "demo-agent",
                "runtimeId": "rt-1",
                "region": "cn-beijing",
                "cloudProvider": "byteplus",
                "projectPath": ".",
                "volcengineAccessKey": "ak_test",
                "volcengineSecretKey": "sk_test",
                "volcengineSessionToken": "token_test",
            },
        )

    assert response.status_code == 200
    assert response.json()["pipelineId"] == "github-acme-demo-cicd-rt-1"
    assert response.json()["cicd"]["enabled"] is True
    assert captured["github_url"] == "https://github.com/acme/demo"
    assert captured["github_token"] == "ghp_secret"
    assert captured["base_branch"] == "main"
    assert captured["runtime_name"] == "demo-agent"
    assert captured["runtime_id"] == "rt-1"
    assert captured["region"] == "cn-beijing"
    assert captured["cloud_provider"] == "byteplus"
    assert captured["project_path"] == "."
    assert captured["volcengine_access_key"] == "ak_test"
    assert captured["volcengine_secret_key"] == "sk_test"
    assert captured["volcengine_session_token"] == "token_test"


def test_studio_endpoint_initializes_github_delivery_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_initialize_github_delivery_main(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "pipelineId": "github-acme-demo-main",
            "status": "cicd-bound",
            "phase": "ready",
            "runtimeId": "rt-1",
            "github": {"branch": "main", "pullRequestUrl": ""},
            "cicd": {
                "enabled": True,
                "workflowPath": ".github/workflows/publish-agentkit.yml",
            },
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.initialize_github_delivery_main",
        fake_initialize_github_delivery_main,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/init-main",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "runtimeName": "demo-agent",
                "runtimeId": "rt-1",
                "region": "cn-beijing",
                "cloudProvider": "byteplus",
                "projectPath": ".",
                "volcengineAccessKey": "ak_test",
                "volcengineSecretKey": "sk_test",
                "volcengineSessionToken": "token_test",
            },
        )

    assert response.status_code == 200
    assert response.json()["pipelineId"] == "github-acme-demo-main"
    assert response.json()["github"]["branch"] == "main"
    assert captured["project"] == PROJECT
    assert captured["github_url"] == "https://github.com/acme/demo"
    assert captured["github_token"] == "ghp_secret"
    assert captured["base_branch"] == "main"
    assert captured["runtime_name"] == "demo-agent"
    assert captured["runtime_id"] == "rt-1"
    assert captured["region"] == "cn-beijing"
    assert captured["cloud_provider"] == "byteplus"
    assert captured["project_path"] == "."
    assert captured["volcengine_access_key"] == "ak_test"
    assert captured["volcengine_secret_key"] == "sk_test"
    assert captured["volcengine_session_token"] == "token_test"


def test_studio_endpoint_lists_github_delivery_versions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_list_github_delivery_versions(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "runtimeId": "rt-1",
            "currentCommitSha": "abc123",
            "github": {"branch": "main"},
            "versions": [{"version": "v1", "commitSha": "abc123"}],
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.list_github_delivery_versions",
        fake_list_github_delivery_versions,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/github-delivery/versions?runtimeId=rt-1",
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert response.status_code == 200
    assert response.json()["runtimeId"] == "rt-1"
    assert captured["runtime_id"] == "rt-1"


def test_studio_endpoint_creates_github_delivery_rollback_pr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_create_github_delivery_rollback_pr(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "runtimeId": "rt-1",
            "status": "rollback-pr-created",
            "github": {"pullRequestUrl": "https://github.com/acme/demo/pull/9"},
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.create_github_delivery_rollback_pr",
        fake_create_github_delivery_rollback_pr,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/rollback-pr",
            headers={"X-VeADK-Local-User": "developer"},
            json={"runtimeId": "rt-1", "targetCommitSha": "abc123"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rollback-pr-created"
    assert captured["runtime_id"] == "rt-1"
    assert captured["target_commit_sha"] == "abc123"


def test_studio_endpoint_attaches_github_delivery_cicd_to_source_sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_attach_github_delivery_cicd_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "pipelineId": "github-acme-demo-studio-demo-agent",
            "status": "cicd-bound",
            "phase": "ready",
            "runtimeId": "rt-1",
            "github": {
                "branch": "studio/demo-agent",
                "pullRequestUrl": "https://github.com/acme/demo/pull/1",
            },
            "cicd": {
                "enabled": True,
                "workflowPath": ".github/workflows/publish-agentkit.yml",
            },
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.attach_github_delivery_cicd_pipeline",
        fake_attach_github_delivery_cicd_pipeline,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/source-sync/cicd",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "pipelineId": "github-acme-demo-studio-demo-agent",
                "runtimeName": "demo-agent",
                "runtimeId": "rt-1",
                "region": "cn-beijing",
                "projectPath": ".",
            },
        )

    assert response.status_code == 200
    assert response.json()["pipelineId"] == "github-acme-demo-studio-demo-agent"
    assert response.json()["cicd"]["enabled"] is True
    assert captured["pipeline_id"] == "github-acme-demo-studio-demo-agent"
    assert captured["runtime_name"] == "demo-agent"
    assert captured["runtime_id"] == "rt-1"
    assert captured["region"] == "cn-beijing"
    assert captured["project_path"] == "."


def test_studio_endpoint_syncs_bound_github_cicd_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_sync_github_cicd_runtime(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "pipelineId": "github-acme-demo-studio-demo-agent",
            "status": "succeeded",
            "phase": "ready",
            "runtimeId": "rt-1",
            "github": {"branch": "studio/demo-agent"},
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.sync_github_cicd_runtime",
        fake_sync_github_cicd_runtime,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-cicd/runtime-sync",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "runtimeId": "rt-1",
                "project": PROJECT,
            },
        )

    assert response.status_code == 200
    assert response.json()["runtimeId"] == "rt-1"
    assert captured["runtime_id"] == "rt-1"
    assert captured["project"] == PROJECT


def test_studio_endpoint_returns_structured_github_cicd_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import GitHubCicdError

    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    def fake_create_github_cicd_pipeline(**_kwargs: Any) -> dict[str, Any]:
        raise GitHubCicdError(
            "GitHub token cannot create branches",
            phase="github",
        )

    monkeypatch.setattr(
        "veadk.cli.github_cicd.create_github_cicd_pipeline",
        fake_create_github_cicd_pipeline,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-delivery/source-sync",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "region": "cn-beijing",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "status": "failed",
        "phase": "github",
        "message": "GitHub token cannot create branches",
    }


class FakeGitHubClient:
    def __init__(self, commit_sha: str = "commit-1") -> None:
        self.commit_sha = commit_sha
        self.created_branch: tuple[str, str] | None = None
        self.committed_files: list[dict[str, str]] = []
        self.commit_message = ""
        self.pull_request: tuple[str, str] | None = None
        self.actions_secrets: dict[str, str] = {}

    def ensure_repository_access(self, owner: str, repo: str) -> None:
        assert (owner, repo) == ("acme", "demo")

    def get_branch_head(self, owner: str, repo: str, branch: str) -> str:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        return "main-sha"

    def ensure_branch(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        source_sha: str,
    ) -> None:
        assert (owner, repo) == ("acme", "demo")
        self.created_branch = (source_sha, branch)

    def commit_files(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        assert (owner, repo) == ("acme", "demo")
        assert branch in {"main", "studio/demo-agent"}
        assert "Studio" in message
        self.committed_files = files
        self.commit_message = message
        return self.commit_sha

    def ensure_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> SimpleNamespace:
        assert (owner, repo) == ("acme", "demo")
        assert title
        assert body
        self.pull_request = (head_branch, base_branch)
        return SimpleNamespace(number=1, url="https://github.com/acme/demo/pull/1")

    def set_actions_secret(
        self,
        owner: str,
        repo: str,
        *,
        name: str,
        value: str,
    ) -> None:
        assert (owner, repo) == ("acme", "demo")
        self.actions_secrets[name] = value


class FakeCicdGitHubClient(FakeGitHubClient):
    def commit_files(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        assert "GitHub Actions" in message
        self.committed_files = files
        self.commit_message = message
        return self.commit_sha

    def ensure_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> SimpleNamespace:
        assert (owner, repo) == ("acme", "demo")
        assert "持续交付" in title
        assert "GitHub Actions" in body
        self.pull_request = (head_branch, base_branch)
        return SimpleNamespace(number=2, url="https://github.com/acme/demo/pull/2")


class FakeMainDeliveryGitHubClient(FakeGitHubClient):
    def __init__(self, commit_sha: str = "main-init-commit") -> None:
        super().__init__(commit_sha=commit_sha)

    def commit_files(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        self.committed_files = files
        self.commit_message = message
        return self.commit_sha


class FakeRollbackGitHubClient(FakeGitHubClient):
    def __init__(self) -> None:
        super().__init__(commit_sha="rollback-commit")
        self.rollback_request: tuple[str, str, str] | None = None
        self.merged_pull_request: int | None = None

    def create_rollback_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        base_branch: str,
        target_commit_sha: str,
        rollback_branch: str,
        title: str,
        body: str,
    ) -> SimpleNamespace:
        assert (owner, repo) == ("acme", "demo")
        assert title
        assert body
        self.rollback_request = (base_branch, target_commit_sha, rollback_branch)
        return SimpleNamespace(
            number=9,
            url="https://github.com/acme/demo/pull/9",
            commit_sha="rollback-commit",
        )

    def merge_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        pull_request_number: int,
        commit_title: str,
    ) -> str:
        assert (owner, repo) == ("acme", "demo")
        assert commit_title
        self.merged_pull_request = pull_request_number
        return "rollback-merge-commit"


class FakeAutoMergeGitHubClient(FakeGitHubClient):
    def __init__(self, commit_sha: str = "source-commit") -> None:
        super().__init__(commit_sha=commit_sha)
        self.merged_pull_request: int | None = None

    def merge_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        pull_request_number: int,
        commit_title: str,
    ) -> str:
        assert (owner, repo) == ("acme", "demo")
        assert commit_title
        self.merged_pull_request = pull_request_number
        return "merge-commit"


class FakeVersionGitHubClient(FakeGitHubClient):
    def list_branch_commits(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        assert limit > 0
        return [
            {
                "sha": "github-commit-3",
                "commit": {
                    "message": "feat: add pending tool\n\nmore details",
                    "author": {"date": "2026-08-13T07:49:24Z", "name": "Catherine"},
                },
                "author": {"login": "CatherineKu"},
            },
            {
                "sha": "github-commit-2",
                "commit": {
                    "message": "feat: add version probe\n\nmore details",
                    "author": {"date": "2026-08-13T06:49:24Z", "name": "Catherine"},
                },
                "author": {"login": "CatherineKu"},
            },
            {
                "sha": "main-init-commit",
                "commit": {
                    "message": "Studio: initialize demo_agent delivery [skip runtime]",
                    "author": {"date": "2026-08-13T05:49:24Z", "name": "Studio"},
                },
                "author": None,
            },
        ]

    def list_commit_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        commit_sha: str,
    ) -> list[SimpleNamespace]:
        assert (owner, repo) == ("acme", "demo")
        if commit_sha == "github-commit-3":
            return [
                SimpleNamespace(number=8, url="https://github.com/acme/demo/pull/8")
            ]
        if commit_sha != "github-commit-2":
            return []
        return [SimpleNamespace(number=7, url="https://github.com/acme/demo/pull/7")]

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        workflow_path: str,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert (owner, repo, workflow_path, branch) == (
            "acme",
            "demo",
            ".github/workflows/publish-agentkit.yml",
            "main",
        )
        assert limit > 0
        return [
            {
                "head_sha": "github-commit-3",
                "status": "in_progress",
                "conclusion": None,
                "html_url": "https://github.com/acme/demo/actions/runs/3",
                "updated_at": "2026-08-13T07:50:24Z",
            },
            {
                "head_sha": "github-commit-2",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/acme/demo/actions/runs/2",
                "updated_at": "2026-08-13T06:50:24Z",
            },
        ]


class FakeSourceOnlyVersionGitHubClient(FakeGitHubClient):
    def __init__(self) -> None:
        super().__init__()
        self.workflow_runs_called = False

    def list_branch_commits(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        assert limit > 0
        return [
            {
                "sha": "source-commit",
                "commit": {
                    "message": "Studio: sync demo_agent Agent source",
                    "author": {"date": "2026-08-13T05:49:24Z", "name": "Studio"},
                },
                "author": None,
            }
        ]

    def list_commit_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        commit_sha: str,
    ) -> list[SimpleNamespace]:
        assert (owner, repo, commit_sha) == ("acme", "demo", "source-commit")
        return []

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        workflow_path: str,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        from veadk.cli.github_cicd import GitHubCicdError

        self.workflow_runs_called = True
        raise GitHubCicdError(
            "GitHub API GET /actions/workflows/publish-agentkit.yml/runs failed: 404"
        )


class FakeRollbackVersionGitHubClient(FakeVersionGitHubClient):
    def list_branch_commits(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        assert limit > 0
        return [
            {
                "sha": "rollback-merge-commit",
                "commit": {
                    "message": "Studio: rollback Agent Runtime to main-init-co",
                    "author": {"date": "2026-08-13T08:49:24Z", "name": "Studio"},
                },
                "author": {"login": "CatherineKu"},
            },
            {
                "sha": "main-init-commit",
                "commit": {
                    "message": "Studio: initialize demo_agent delivery [skip runtime]",
                    "author": {"date": "2026-08-13T05:49:24Z", "name": "Studio"},
                },
                "author": None,
            },
        ]

    def list_commit_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        commit_sha: str,
    ) -> list[SimpleNamespace]:
        assert (owner, repo) == ("acme", "demo")
        if commit_sha != "rollback-merge-commit":
            return []
        return [SimpleNamespace(number=9, url="https://github.com/acme/demo/pull/9")]

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        workflow_path: str,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert (owner, repo, workflow_path, branch) == (
            "acme",
            "demo",
            ".github/workflows/publish-agentkit.yml",
            "main",
        )
        assert limit > 0
        return [
            {
                "head_sha": "rollback-merge-commit",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/acme/demo/actions/runs/9",
                "updated_at": "2026-08-13T08:50:24Z",
            }
        ]


class FakeGithubResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        *,
        reason: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.reason = reason
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class FakeEmptyRepoSession:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self._blob_index = 0

    def request(self, method: str, url: str, **kwargs: Any) -> FakeGithubResponse:
        path = url.removeprefix("https://api.github.com")
        self.requests.append((method, path, kwargs))
        if method == "GET" and path == "/repos/acme/demo/git/ref/heads/main":
            return FakeGithubResponse(
                409,
                {"message": "Git Repository is empty."},
                reason="Conflict",
            )
        if method == "POST" and path == "/repos/acme/demo/git/blobs":
            self._blob_index += 1
            return FakeGithubResponse(201, {"sha": f"blob-{self._blob_index}"})
        if method == "POST" and path == "/repos/acme/demo/git/trees":
            return FakeGithubResponse(201, {"sha": "empty-tree"})
        if method == "POST" and path == "/repos/acme/demo/git/commits":
            return FakeGithubResponse(201, {"sha": "empty-commit"})
        if method == "POST" and path == "/repos/acme/demo/git/refs":
            return FakeGithubResponse(201, {"ref": "refs/heads/main"})
        return FakeGithubResponse(500, {"message": f"unexpected {method} {path}"})

    def request_json(self, method: str, path: str) -> dict[str, Any]:
        for request_method, request_path, kwargs in self.requests:
            if request_method == method and request_path == path:
                payload = kwargs.get("json")
                assert isinstance(payload, dict)
                return payload
        raise AssertionError(f"request not found: {method} {path}")

    def has_request(self, method: str, path: str) -> bool:
        return any(
            request_method == method and request_path == path
            for request_method, request_path, _kwargs in self.requests
        )


def _create_studio_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    developers: str,
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda *args, **kwargs: "")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        site_logo=None,
        site_title=None,
        host="127.0.0.1",
        port=8765,
        dev=True,
        vite=True,
        oauth2_user_pool=None,
        oauth2_user_pool_client=None,
        oauth2_user_pool_uid=None,
        oauth2_user_pool_client_uid=None,
        oauth2_redirect_uri=None,
        oauth2_provider=None,
        oauth2_provider_label=None,
        auth_mode="frontend",
        generated_agent_test_run_ttl=60,
        studio_admins=None,
        studio_developers=developers,
        open_browser=False,
        studio=True,
    )
    return captured["app"]
