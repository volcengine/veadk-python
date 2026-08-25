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

from __future__ import annotations

import py_compile
import socket

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    DeploymentConfig,
    GeneratedAgentProjectRequest,
    GeneratedAgentTestRunRequest,
    GeneratedFile,
    GeneratedProject,
    SelectedSkill,
    generate_project_from_draft,
)
from veadk.cli.generated_agent_security import (
    DebugPolicyError,
    validate_debug_policy,
    validate_project_policy,
    validate_url_not_private,
)
from veadk.cli.generated_agent_skills import materialize_selected_skills


def test_old_files_request_shape_is_rejected() -> None:
    payload = {
        "name": "demo",
        "files": [{"path": "agents/demo/agent.py", "content": "root_agent = None"}],
    }
    with pytest.raises(ValidationError):
        GeneratedAgentProjectRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        GeneratedAgentTestRunRequest.model_validate(payload)


def test_minimal_codegen_agent_py_compiles(tmp_path) -> None:
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction='Say "hello" and handle """triple""" quotes \\ safely.',
    )
    project = generate_project_from_draft(draft)

    assert project.name == "demo_agent"
    paths = {file.path for file in project.files}
    assert "app.py" in paths
    assert "agents/demo_agent/agent.py" in paths
    assert "agents/demo_agent/__init__.py" in paths
    assert ".env.example" in paths
    assert "requirements.txt" in paths
    assert "Dockerfile" not in paths
    requirements = next(
        file.content for file in project.files if file.path == "requirements.txt"
    )
    assert requirements == (
        "veadk-python==1.1.5\n"
        "agentkit-sdk-python==0.8.4\n"
        "google-adk==2.1.0\n"
        "starlette==0.52.1\n"
    )

    for file in project.files:
        if file.path.endswith(".py"):
            target = tmp_path / file.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content, encoding="utf-8")
            py_compile.compile(str(target), doraise=True)


@pytest.mark.parametrize(
    ("cloud_provider", "base_image"),
    [
        pytest.param(
            "volcengine",
            "agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest",
            id="volcengine",
        ),
        pytest.param(
            "byteplus",
            "agentkit-prod-public-ap-southeast-1.cr.bytepluses.com/base/py-simple:python3.12-bookworm-slim-latest",
            id="byteplus",
        ),
    ],
)
def test_codegen_cloud_environment_uses_provider_base_image(
    cloud_provider: str,
    base_image: str,
) -> None:
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "instruction": "You are helpful.",
                "cloudProvider": cloud_provider,
                "cloudEnvironment": {"cliTools": ["lark-cli"]},
            }
        )
    )
    files = {file.path: file.content for file in project.files}

    assert files["Dockerfile"].startswith(f"FROM {base_image}\n")
    assert "lark-cli-1.0.87-linux-${arch}.tar.gz" in files["Dockerfile"]
    assert (
        "6027b1ddc12440400581bbdf9554850d8e119c7dd400439b1220e7a87b9673c5"
        in files["Dockerfile"]
    )
    assert (
        "fade9a22d363172a9c18a8287c99c80d6d106a2900f3fce4015e4e156c5fc776"
        in files["Dockerfile"]
    )
    assert "--connect-timeout 10" in files["Dockerfile"]
    assert (
        "https://ghfast.top/https://github.com/larksuite/cli/releases/download"
        in files["Dockerfile"]
    )
    assert 'CMD ["python", "-m", "app"]' in files["Dockerfile"]


def test_codegen_cloud_environment_installs_github_cli_for_both_architectures() -> None:
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "instruction": "You are helpful.",
                "cloudEnvironment": {"cliTools": ["github-cli"]},
            }
        )
    )
    dockerfile = {file.path: file.content for file in project.files}["Dockerfile"]

    assert "gh_2.97.0_linux_${arch}.tar.gz" in dockerfile
    assert (
        "a2c9b8497e1f85b1ad0dfcb78b5a622e098801b8e461e459e88e1ee12f018112" in dockerfile
    )
    assert (
        "73ea440ecad9c9e284429997ee6f93577bc6f7bc6fba357ef62c53ad8fb641a5" in dockerfile
    )
    assert (
        "https://ghfast.top/https://github.com/cli/cli/releases/download" in dockerfile
    )
    assert (
        "apt-get install -y --no-install-recommends ca-certificates curl git"
        in dockerfile
    )
    assert "# Install GitHub CLI (gh)" in dockerfile


def test_codegen_cloud_environment_installs_pandoc_from_system_packages() -> None:
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "instruction": "You are helpful.",
                "cloudEnvironment": {"cliTools": ["pandoc"]},
            }
        )
    )
    dockerfile = {file.path: file.content for file in project.files}["Dockerfile"]

    assert (
        "apt-get install -y --no-install-recommends ca-certificates curl pandoc"
        in dockerfile
    )


def test_codegen_cloud_environment_can_install_both_clis_without_credentials() -> None:
    secret = "must-not-leak"
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "instruction": "You are helpful.",
                "cloudEnvironment": {
                    "cliTools": ["lark-cli", "github-cli"],
                },
                "deployment": {"envValues": {"GITHUB_TOKEN": secret}},
            }
        )
    )
    dockerfile = {file.path: file.content for file in project.files}["Dockerfile"]

    assert "lark-cli" in dockerfile
    assert "gh_2.97.0" in dockerfile
    assert "ca-certificates curl git" in dockerfile
    assert "# Configure AgentKit runtime defaults." in dockerfile
    assert "# Install system dependencies" in dockerfile
    assert "# Install Lark CLI" in dockerfile
    assert "# Install GitHub CLI (gh)" in dockerfile
    assert "# Install Python dependencies" in dockerfile
    assert "# Copy the Agent application" in dockerfile
    assert secret not in dockerfile
    assert "GITHUB_TOKEN" not in dockerfile


def test_codegen_cloud_environment_uses_custom_dockerfile_verbatim() -> None:
    custom_dockerfile = "FROM example.invalid/custom\nRUN echo ready\n"
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "instruction": "You are helpful.",
                "cloudEnvironment": {
                    "cliTools": ["lark-cli"],
                    "dockerfile": custom_dockerfile,
                },
            }
        )
    )

    dockerfile = {file.path: file.content for file in project.files}["Dockerfile"]
    assert dockerfile == custom_dockerfile
    assert "lark-cli-1.0.87" not in dockerfile


def test_codegen_cloud_environment_allows_custom_dockerfile_without_cli_tools() -> None:
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "cloudEnvironment": {
                    "dockerfile": "FROM example.invalid/base\n",
                },
            }
        )
    )

    dockerfile = {file.path: file.content for file in project.files}["Dockerfile"]
    assert dockerfile == "FROM example.invalid/base\n"


def test_codegen_cloud_environment_rejects_blank_custom_dockerfile() -> None:
    with pytest.raises(ValidationError):
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "cloudEnvironment": {"dockerfile": "  \n"},
            }
        )


def test_codegen_cloud_environment_rejects_oversized_custom_dockerfile() -> None:
    with pytest.raises(ValidationError):
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "cloudEnvironment": {"dockerfile": "x" * 65_537},
            }
        )


def test_codegen_cloud_environment_rejects_unknown_cli() -> None:
    with pytest.raises(ValidationError):
        AgentDraft.model_validate(
            {
                "name": "Cloud Agent",
                "cloudEnvironment": {"cliTools": ["curl"]},
            }
        )


@pytest.mark.parametrize(
    ("cloud_provider", "model_api_base"),
    [
        pytest.param(
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3/",
            id="volcengine",
        ),
        pytest.param(
            "byteplus",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            id="byteplus",
        ),
    ],
)
def test_codegen_official_model_endpoint_does_not_require_custom_agent_key(
    cloud_provider: str,
    model_api_base: str,
) -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="Official Agent",
            instruction="You are helpful.",
            cloudProvider=cloud_provider,
            modelApiBase=model_api_base,
        )
    )
    files = {file.path: file.content for file in project.files}
    agent_py = files["agents/official_agent/agent.py"]

    assert "model_api_key=" not in agent_py
    assert "CUSTOM_MODEL_OFFICIAL_AGENT_API_KEY" not in agent_py
    assert "CUSTOM_MODEL_OFFICIAL_AGENT_API_KEY" not in files[".env.example"]


def test_codegen_custom_model_endpoint_reads_agent_specific_key() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="Custom Agent",
            instruction="You are helpful.",
            modelProvider="openai",
            modelApiBase="https://models.example.com/v1",
        )
    )
    files = {file.path: file.content for file in project.files}
    agent_py = files["agents/custom_agent/agent.py"]

    assert 'model_provider=os.environ["CUSTOM_MODEL_CUSTOM_AGENT_PROVIDER"]' in agent_py
    assert 'model_api_base=os.environ["CUSTOM_MODEL_CUSTOM_AGENT_API_BASE"]' in agent_py
    assert 'model_api_key=os.environ["CUSTOM_MODEL_CUSTOM_AGENT_API_KEY"]' in agent_py
    assert "CUSTOM_MODEL_CUSTOM_AGENT_PROVIDER=openai" in files[".env.example"]
    assert (
        "CUSTOM_MODEL_CUSTOM_AGENT_API_BASE=https://models.example.com/v1"
        in files[".env.example"]
    )
    assert (
        "CUSTOM_MODEL_CUSTOM_AGENT_API_KEY=replace-with-your-own-model-api-key"
        in files[".env.example"]
    )


def test_codegen_custom_model_agents_use_distinct_key_env_names() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="Model Workflow",
            instruction="Coordinate specialists.",
            agentType="sequential",
            subAgents=[
                AgentDraft(
                    name="Research Agent",
                    instruction="Research the topic.",
                    modelApiBase="https://research-model.example.com/v1",
                ),
                AgentDraft(
                    name="Writer Agent",
                    instruction="Write the answer.",
                    modelApiBase="https://writer-model.example.com/v1",
                ),
            ],
        )
    )
    files = {file.path: file.content for file in project.files}
    agent_py = files["agents/model_workflow/agent.py"]
    env_example = files[".env.example"]

    assert 'model_api_key=os.environ["CUSTOM_MODEL_RESEARCH_AGENT_API_KEY"]' in agent_py
    assert 'model_api_key=os.environ["CUSTOM_MODEL_WRITER_AGENT_API_KEY"]' in agent_py
    assert (
        "CUSTOM_MODEL_RESEARCH_AGENT_API_KEY=replace-with-your-own-model-api-key"
        in env_example
    )
    assert (
        "CUSTOM_MODEL_WRITER_AGENT_API_KEY=replace-with-your-own-model-api-key"
        in env_example
    )


def test_codegen_custom_model_env_example_never_contains_secret() -> None:
    secret = "sk-user-provided-secret-that-must-not-leak"
    project = generate_project_from_draft(
        AgentDraft(
            name="Private Model",
            instruction="You are helpful.",
            modelApiBase="https://private-model.example.com/v1",
            deployment=DeploymentConfig(
                envValues={"CUSTOM_MODEL_PRIVATE_MODEL_API_KEY": secret}
            ),
        )
    )
    files = {file.path: file.content for file in project.files}
    env_example = files[".env.example"]

    assert (
        "CUSTOM_MODEL_PRIVATE_MODEL_API_KEY=replace-with-your-own-model-api-key"
        in env_example
    )
    assert secret not in env_example
    assert all(secret not in content for content in files.values())


def test_codegen_agent_named_agent_cannot_reuse_studio_managed_model_key() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="Agent",
            instruction="You are helpful.",
            modelApiBase="https://custom-model.example.com/v1",
        )
    )
    files = {file.path: file.content for file in project.files}
    agent_py = files["agents/agent/agent.py"]
    env_example = files[".env.example"]

    assert 'model_api_key=os.environ["CUSTOM_MODEL_AGENT_API_KEY"]' in agent_py
    assert 'model_api_key=os.environ["MODEL_AGENT_API_KEY"]' not in agent_py
    assert (
        "CUSTOM_MODEL_AGENT_API_KEY=replace-with-your-own-model-api-key" in env_example
    )


def test_security_rejects_unsupported_builtin_tool() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        builtinTools=["not_a_tool"],
    )
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft)


def test_security_rejects_mcp_stdio() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        mcpTools=[{"transport": "stdio", "command": "npx"}],
    )
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft)


def test_project_policy_allows_mcp_stdio_but_debug_rejects_it() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        mcpTools=[{"transport": "stdio", "command": "npx", "args": ["-y", "mcp"]}],
    )

    validate_project_policy(draft)
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft, allow_local_runtime_resources=True)


@pytest.mark.parametrize(
    ("cloud_provider", "model_api_base"),
    [
        pytest.param("volcengine", "", id="volcengine-default"),
        pytest.param(
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3/",
            id="volcengine-official",
        ),
        pytest.param("byteplus", "", id="byteplus-default"),
        pytest.param(
            "byteplus",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            id="byteplus-official",
        ),
    ],
)
def test_debug_policy_allows_default_and_official_model_api_bases(
    cloud_provider: str,
    model_api_base: str,
) -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        cloudProvider=cloud_provider,
        modelApiBase=model_api_base,
    )

    validate_debug_policy(draft, managed_cloud_provider=cloud_provider)


@pytest.mark.parametrize(
    ("cloud_provider", "model_api_base"),
    [
        pytest.param(
            "volcengine",
            "https://example.com/api/v3",
            id="custom-domain",
        ),
        pytest.param(
            "volcengine",
            "https://ark.cn-beijing.volces.com.evil.example/api/v3",
            id="lookalike-subdomain",
        ),
        pytest.param(
            "volcengine",
            "http://ark.cn-beijing.volces.com/api/v3",
            id="http",
        ),
        pytest.param(
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3?target=evil",
            id="query",
        ),
        pytest.param(
            "volcengine",
            "https://attacker@ark.cn-beijing.volces.com/api/v3",
            id="userinfo",
        ),
        pytest.param(
            "volcengine",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            id="volcengine-with-byteplus-base",
        ),
        pytest.param(
            "byteplus",
            "https://ark.cn-beijing.volces.com/api/v3/",
            id="byteplus-with-volcengine-base",
        ),
    ],
)
def test_debug_policy_rejects_untrusted_model_api_bases(
    cloud_provider: str,
    model_api_base: str,
) -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        cloudProvider=cloud_provider,
        modelApiBase=model_api_base,
    )

    with pytest.raises(DebugPolicyError, match="自定义模型地址"):
        validate_debug_policy(draft, managed_cloud_provider=cloud_provider)


def test_debug_policy_rejects_nested_subagent_custom_model_api_base() -> None:
    draft = AgentDraft(
        name="workflow",
        instruction="Coordinate the sub-agent.",
        agentType="sequential",
        cloudProvider="volcengine",
        subAgents=[
            AgentDraft(
                name="custom-model-agent",
                instruction="You are helpful.",
                modelApiBase="https://example.com/api/v3",
            )
        ],
    )

    with pytest.raises(DebugPolicyError, match="自定义模型地址"):
        validate_debug_policy(draft, managed_cloud_provider="volcengine")


def test_project_policy_still_allows_custom_model_api_base() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        modelApiBase="https://example.com/api/v3",
    )

    validate_project_policy(draft)


def test_security_rejects_enabled_a2a_registry_without_space_id() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        a2aRegistry={"enabled": True},
    )
    with pytest.raises(DebugPolicyError, match="A2A registry space id is required"):
        validate_project_policy(draft)


def test_security_allows_registry_backed_remote_agent_without_url() -> None:
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        agentType="sequential",
        subAgents=[
            AgentDraft(
                agentType="a2a",
                a2aRegistry={
                    "enabled": True,
                    "registrySpaceId": "space-test",
                },
            )
        ],
    )

    validate_project_policy(draft)
    validate_debug_policy(draft)


def test_url_policy_rejects_private_literal_ip() -> None:
    with pytest.raises(DebugPolicyError):
        validate_url_not_private("http://127.0.0.1:8000", field_name="url")
    with pytest.raises(DebugPolicyError):
        validate_url_not_private("http://169.254.169.254/latest", field_name="url")


def test_url_policy_rejects_dns_to_private_ip(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.8", 443),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(DebugPolicyError):
        validate_url_not_private("https://example.com", field_name="url")


@pytest.mark.asyncio
async def test_local_skill_materialization_accepts_safe_skill() -> None:
    skill_md = "---\nname: local-skill\ndescription: Local skill.\n---\n\n# Local\n"
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        selectedSkills=[
            SelectedSkill(
                source="local",
                folder="local-skill",
                name="local-skill",
                localFiles=[
                    GeneratedFile(
                        path="skills/local-skill/SKILL.md",
                        content=skill_md,
                    )
                ],
            )
        ],
    )
    project = GeneratedProject(name="demo", files=[])

    await materialize_selected_skills(draft, project)

    assert project.files == [
        GeneratedFile(path="skills/local-skill/SKILL.md", content=skill_md)
    ]


@pytest.mark.asyncio
async def test_local_skill_materialization_keeps_validation_minimal() -> None:
    skill_md = "---\nname: Display Skill\n---\n\n# Local\n"
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        selectedSkills=[
            SelectedSkill(
                source="local",
                folder="local-folder",
                name="Display Skill",
                localFiles=[
                    GeneratedFile(
                        path="skills/local-folder/SKILL.md",
                        content=skill_md,
                    )
                ],
            )
        ],
    )
    project = GeneratedProject(name="demo", files=[])

    await materialize_selected_skills(draft, project)

    assert project.files == [
        GeneratedFile(path="skills/local-folder/SKILL.md", content=skill_md)
    ]


@pytest.mark.asyncio
async def test_local_skill_materialization_rejects_path_escape() -> None:
    skill_md = "---\nname: local-skill\ndescription: Local skill.\n---\n"
    draft = AgentDraft(
        name="demo",
        instruction="You are helpful.",
        selectedSkills=[
            SelectedSkill(
                source="local",
                folder="local-skill",
                name="local-skill",
                localFiles=[
                    GeneratedFile(
                        path="skills/local-skill/SKILL.md",
                        content=skill_md,
                    ),
                    GeneratedFile(path="../evil.py", content="print('bad')"),
                ],
            )
        ],
    )
    project = GeneratedProject(name="demo", files=[])

    with pytest.raises(DebugPolicyError):
        await materialize_selected_skills(draft, project)
