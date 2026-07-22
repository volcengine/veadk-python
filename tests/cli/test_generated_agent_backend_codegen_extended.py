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

import hashlib
import io
import json
import secrets
import socket
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from veadk.cli.cli_frontend import (
    _redact_debug_text,
    _run_frontend_server,
    _studio_deploy_run_script,
)
from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    GeneratedAgentProjectRequest,
    GeneratedProject,
    generate_project_from_draft,
)
from veadk.cli.generated_agent_security import (
    DebugPolicyError,
    MAX_DEPTH,
    MAX_ITERATIONS,
    validate_debug_policy,
    validate_project_policy,
    validate_url_not_private,
)
from veadk.cli.generated_agent_skills import (
    _files_from_zip,
    materialize_selected_skills,
)


# These hashes lock the complete generated project contents, not just Python
# syntax or selected snippets.
_MINIMAL_FRONTEND_GOLDEN = {
    "app.py": "c7807c570167793fc8c5a8a72e9f3c32aac0820db3098cb52edb1488c34a8e5f",
    "agents/__init__.py": "a6449a6cac3bfda8b834ea39ea95ca2f8d0471ac480e1e876313d7398eea59ba",
    "agents/demo_agent/agent.py": "b2d22094a8ea61e8ab6e2b633d7695c5fa5e883f03516cb8771e7ec00be0fe1f",
    "agents/demo_agent/__init__.py": "62d651c229ddd771cf0cc0a8b0e05e96b739a737fe71e41fe8bf1df484150c36",
    ".env.example": "ec3258da9bef4e74333376d8554c265ccb12a4a1e5d4e1e1b0acdf5c9ae93ab6",
    "requirements.txt": "9a04e5f16e94d5e751681082776f1c99f13da7a577c8753c3835e0ea507245e4",
    "README.md": "a34208314cf9061c02662028d7a9dd97448e6b73c1d732cb4aeaa8f70dbbc684",
}

_FULL_FRONTEND_GOLDEN = {
    "app.py": "a9903cf7e095733e9b8658182a0954a81d8a98b431f8ab995ce3818950127006",
    "agents/__init__.py": "a6449a6cac3bfda8b834ea39ea95ca2f8d0471ac480e1e876313d7398eea59ba",
    "agents/full_agent/agent.py": "1bc030b7aaafa29bbb673e4a67bd51a1a209dd1f0377206b0ca35252c82c5822",
    "agents/full_agent/__init__.py": "62d651c229ddd771cf0cc0a8b0e05e96b739a737fe71e41fe8bf1df484150c36",
    ".env.example": "054a10f8bc0e046158349ebccdc67a1182c22c4c63ee5b51bf7c2c1674abe052",
    "requirements.txt": "4a941e1bf7efb43d57f608649ac238f2e5ea833f9e0aae92f8bc3fef67b8874e",
    "README.md": "1bf4dc889c7d1076f50784d253b53412ba7c49bcb69a5d948f9092dbbecb18ac",
}


def _file_map(project: GeneratedProject) -> dict[str, str]:
    return {file.path: file.content for file in project.files}


def _content_hashes(project: GeneratedProject) -> dict[str, str]:
    return {
        path: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for path, content in _file_map(project).items()
    }


def _full_draft() -> AgentDraft:
    skill_md = "---\nname: local-skill\ndescription: Local.\n---\n"
    return AgentDraft(
        name="Full Agent",
        description="Everything enabled",
        instruction='Use "tools".\nHandle """ safely and \\ paths.',
        modelName="doubao-test",
        modelProvider="openai",
        modelApiBase="https://ark.example.com/v3",
        tools=["legacy helper"],
        builtinTools=["web_search", "video_generate"],
        customTools=[
            {"name": "lookup-order", "description": 'Lookup "order".\nReturn details.'}
        ],
        mcpTools=[
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/api",
                "authToken": "secret-token",
            }
        ],
        memory={"shortTerm": True, "longTerm": True},
        shortTermBackend="sqlite",
        longTermBackend="redis",
        autoSaveSession=True,
        knowledgebase=True,
        knowledgebaseBackend="context_search",
        tracing=True,
        tracingExporters=["apmplus", "cozeloop", "tls"],
        selectedSkills=[
            {
                "source": "local",
                "folder": "local-skill",
                "name": "local-skill",
                "description": "Local",
                "localFiles": [
                    {
                        "path": "skills/local-skill/SKILL.md",
                        "content": skill_md,
                    }
                ],
            }
        ],
        subAgents=[
            AgentDraft(
                name="loop-child",
                description="Loop",
                agentType="loop",
                maxIterations=4,
                subAgents=[
                    AgentDraft(
                        name="worker",
                        instruction="Work",
                        builtinTools=["link_reader"],
                    )
                ],
            ),
            AgentDraft(
                name="remote",
                agentType="a2a",
                a2aUrl="https://agent.example.com",
            ),
        ],
        deployment={"feishuEnabled": True},
    )


def test_minimal_project_matches_frontend_codegen_golden() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="demo-agent",
            description="Demo agent",
            instruction='Say "hello" and handle """triple""" quotes \\ safely.',
        )
    )

    assert project.name == "demo_agent"
    assert _content_hashes(project) == _MINIMAL_FRONTEND_GOLDEN


def test_full_project_matches_frontend_codegen_golden() -> None:
    draft = _full_draft()
    project = generate_project_from_draft(draft)
    files = _file_map(project)

    assert project.name == "full_agent"
    assert "enableA2ui" not in draft.model_dump()
    assert "enable_a2ui" not in files["agents/full_agent/agent.py"]
    assert "[a2ui]" not in files["requirements.txt"]
    assert _content_hashes(project) == _FULL_FRONTEND_GOLDEN


def test_retired_a2ui_option_is_accepted_but_not_generated() -> None:
    draft = AgentDraft.model_validate({"name": "legacy", "enableA2ui": True})
    files = _file_map(generate_project_from_draft(draft))

    assert "enableA2ui" not in draft.model_dump()
    assert "enable_a2ui" not in files["agents/legacy/agent.py"]
    assert "[a2ui]" not in files["requirements.txt"]


def test_codegen_preserves_agent_display_names_for_topology() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="客服智能体",
            subAgents=[AgentDraft(name="订单助手", instruction="处理订单")],
        )
    )
    files = _file_map(project)
    agent_py = files["agents/my_agent/agent.py"]
    app_py = files["app.py"]

    assert "'agent': '客服智能体'" in agent_py
    assert "'agent_sub_1': '订单助手'" in agent_py
    assert "create_agentkit_app(" in app_py
    assert "AGENT_DISPLAY_NAMES" in app_py
    assert 'app.get("/web/agent-info' not in app_py
    assert len(app_py.splitlines()) == 25


def test_codegen_enables_feishu_without_exposing_lifecycle_code() -> None:
    project = generate_project_from_draft(
        AgentDraft(name="demo", deployment={"feishuEnabled": True})
    )
    files = _file_map(project)
    app_py = files["app.py"]

    assert "enable_feishu=True" in app_py
    assert "FeishuChannelExtension" not in app_py
    assert "asynccontextmanager" not in app_py
    assert "veadk-python[extensions]" in files["requirements.txt"]
    assert "FEISHU_APP_ID=" in files[".env.example"]
    assert "FEISHU_APP_SECRET=" in files[".env.example"]


def test_frontend_complete_shape_is_accepted_and_unknown_field_is_rejected() -> None:
    payload = json.loads(_full_draft().model_dump_json(by_alias=True))
    payload["workflow"] = {
        "type": "custom",
        "nodes": [{"id": "n1", "agent": {}, "position": {"x": 1, "y": 2}}],
        "edges": [{"from": "n1", "to": "n2", "animated": True}],
    }

    request = GeneratedAgentProjectRequest.model_validate({"draft": payload})
    assert request.draft.workflow is not None
    assert request.draft.workflow.edges[0].from_ == "n1"

    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        GeneratedAgentProjectRequest.model_validate({"draft": payload})


@pytest.mark.parametrize(
    ("agent_type", "class_name", "extra"),
    [
        ("sequential", "SequentialAgent", ""),
        ("parallel", "ParallelAgent", ""),
        ("loop", "LoopAgent", "max_iterations=7"),
    ],
)
def test_orchestrator_codegen(agent_type: str, class_name: str, extra: str) -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name=f"{agent_type}-root",
            agentType=agent_type,
            maxIterations=7,
            subAgents=[AgentDraft(name="worker", instruction="Work")],
        )
    )
    agent_py = _file_map(project)[f"agents/{agent_type}_root/agent.py"]

    assert f"from google.adk.agents import {class_name}" in agent_py
    assert f"agent = {class_name}(" in agent_py
    assert "sub_agents=[agent_sub_1]" in agent_py
    if extra:
        assert extra in agent_py


@pytest.mark.parametrize(
    "draft",
    [
        AgentDraft(name="demo", shortTermBackend="unknown"),
        AgentDraft(name="demo", longTermBackend="unknown"),
        AgentDraft(name="demo", knowledgebaseBackend="unknown"),
        AgentDraft(name="demo", tracingExporters=["unknown"]),
        AgentDraft(name="demo", agentType="loop", maxIterations=MAX_ITERATIONS + 1),
    ],
)
def test_security_rejects_unsupported_component_configuration(
    draft: AgentDraft,
) -> None:
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(draft)


def test_security_rejects_agent_tree_beyond_depth_limit() -> None:
    root = AgentDraft(name="level-0")
    node = root
    for depth in range(1, MAX_DEPTH + 2):
        child = AgentDraft(name=f"level-{depth}")
        node.subAgents.append(child)
        node = child

    with pytest.raises(DebugPolicyError, match="too deep"):
        validate_debug_policy(root)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost:8000",
        "http://[::1]:8000",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_url_policy_rejects_non_http_and_local_targets(url: str) -> None:
    with pytest.raises(DebugPolicyError):
        validate_url_not_private(url, field_name="url")


def test_url_policy_rejects_dns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_resolution(*args: Any, **kwargs: Any) -> Any:
        raise socket.gaierror("not found")

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)
    with pytest.raises(DebugPolicyError, match="cannot be resolved"):
        validate_url_not_private("https://missing.example", field_name="url")


def test_project_allows_stdio_mcp_but_debug_rejects_it() -> None:
    project_draft = AgentDraft(
        name="demo",
        instruction="Use local MCP.",
        mcpTools=[
            {"transport": "stdio", "command": "npx", "args": ["-y", "mcp"]},
            {"transport": "http", "url": "http://127.0.0.1:9000/mcp"},
        ],
        subAgents=[
            AgentDraft(
                name="local-a2a",
                agentType="a2a",
                a2aUrl="http://localhost:9001",
            )
        ],
    )

    validate_project_policy(project_draft)
    with pytest.raises(DebugPolicyError):
        validate_debug_policy(project_draft, allow_local_runtime_resources=True)

    debug_draft = AgentDraft(
        name="demo",
        instruction="Use local MCP.",
        mcpTools=[{"transport": "http", "url": "http://127.0.0.1:9000/mcp"}],
        subAgents=[
            AgentDraft(
                name="local-a2a",
                agentType="a2a",
                a2aUrl="http://localhost:9001",
            )
        ],
    )
    validate_debug_policy(debug_draft, allow_local_runtime_resources=True)


@pytest.mark.asyncio
async def test_skillspace_materialization_deduplicates_nested_selection() -> None:
    skill = {
        "source": "skillspace",
        "folder": "shared-skill",
        "name": "shared-skill",
        "skillSpaceId": "space-1",
        "skillId": "skill-1",
        "version": "v1",
    }
    draft = AgentDraft(
        name="root",
        selectedSkills=[skill],
        subAgents=[AgentDraft(name="child", selectedSkills=[skill])],
    )
    project = GeneratedProject(name="root", files=[])
    calls: list[tuple[str, str, str | None]] = []

    async def resolve(space_id: str, skill_id: str, version: str | None) -> str:
        calls.append((space_id, skill_id, version))
        return "---\nname: shared-skill\ndescription: Shared.\n---\n"

    await materialize_selected_skills(
        draft,
        project,
        resolve_skillspace_detail=resolve,
    )

    assert calls == [("space-1", "skill-1", "v1")]
    assert [file.path for file in project.files] == ["skills/shared-skill/SKILL.md"]


def _skill_zip(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def test_skillhub_zip_accepts_safe_files_and_rejects_path_escape() -> None:
    skill_md = "---\nname: demo-skill\ndescription: Demo.\n---\n"
    files = _files_from_zip(
        _skill_zip({"SKILL.md": skill_md, "scripts/run.py": "print('ok')\n"}),
        "demo-skill",
        "test skill",
    )
    assert [file.path for file in files] == [
        "skills/demo-skill/SKILL.md",
        "skills/demo-skill/scripts/run.py",
    ]

    with pytest.raises(DebugPolicyError, match="Illegal skill file path"):
        _files_from_zip(
            _skill_zip({"SKILL.md": skill_md, "../evil.py": "bad"}),
            "demo-skill",
            "test skill",
        )


def test_skillhub_zip_accepts_gb18030_text_files() -> None:
    skill_md = "---\nname: demo-skill\ndescription: 数据处理。\n---\n".encode("gb18030")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("SKILL.md", skill_md)
        archive.writestr("references/readme.md", "说明：￥\n".encode("gb18030"))

    files = _files_from_zip(output.getvalue(), "demo-skill", "test skill")

    assert files[0].content.startswith("---")
    assert "数据处理" in files[0].content
    assert "说明：￥" in files[1].content


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        body: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._body = body
        self.text = body.decode("utf-8", "replace")

    def json(self) -> Any:
        return self._json_data

    async def aread(self) -> bytes:
        return self._body

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def aiter_bytes(self):
        yield self._body


class _FakeAsyncClient:
    streamed_payloads: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        assert url.endswith("/list-apps")
        return _FakeResponse(json_data=["demo_agent"])

    async def post(self, url: str, json: Any) -> _FakeResponse:
        assert "/sessions" in url
        return _FakeResponse(json_data={"id": "session-1"})

    def stream(self, method: str, url: str, json: dict[str, Any], **kwargs: Any):
        assert method == "POST"
        assert url.endswith("/run_sse")
        self.streamed_payloads.append(json)
        return _FakeResponse(body=b'data: {"content":{"parts":[{"text":"hello"}]}}\n\n')


class _FakeRunnerErrorAsyncClient(_FakeAsyncClient):
    async def post(self, url: str, json: Any) -> _FakeResponse:
        assert "/sessions" in url
        return _FakeResponse(status_code=500, body=b"Internal Server Error")

    def stream(self, method: str, url: str, json: dict[str, Any], **kwargs: Any):
        assert method == "POST"
        assert url.endswith("/run_sse")
        return _FakeResponse(status_code=500, body=b"Internal Server Error")


class _FakeProcess:
    created: list["_FakeProcess"] = []

    def __init__(self, cmd: list[str], *, cwd: str, **kwargs: Any) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.env = kwargs.get("env", {})
        self.returncode: int | None = None
        self.terminated = False
        self.created.append(self)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0

    def kill(self) -> None:
        self.returncode = -9


class _FakeSocket:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def bind(self, address: tuple[str, int]) -> None:
        assert address == ("127.0.0.1", 0)

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", 54321)


def test_debug_text_redacts_environment_and_inline_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_marker = "public-environment-marker-123"
    inline_marker = "public-inline-marker-456"
    bearer_marker = "public-bearer-marker-789"
    monkeypatch.setenv("SMOKEY_REDACTION_PROBE", environment_marker)

    redacted = _redact_debug_text(
        f"env={environment_marker}\n"
        f"authToken={inline_marker}\n"
        f"Authorization: Bearer {bearer_marker}"
    )

    assert environment_marker not in redacted
    assert inline_marker not in redacted
    assert bearer_marker not in redacted
    assert "authToken=***" in redacted
    assert "Bearer ***" in redacted


def test_generated_project_and_debug_run_api_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    _FakeProcess.created.clear()
    _FakeAsyncClient.streamed_payloads.clear()
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")

    monkeypatch.setattr("dotenv.find_dotenv", lambda: "")
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
        open_browser=False,
    )

    monkeypatch.setattr("subprocess.Popen", _FakeProcess)
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    real_socket = socket.socket
    monkeypatch.setattr(
        "socket.socket",
        lambda *args, **kwargs: (
            real_socket(*args, **kwargs)
            if len(args) >= 4 or "fileno" in kwargs
            else _FakeSocket(*args, **kwargs)
        ),
    )

    draft = {
        "name": "demo-agent",
        "description": "Demo agent",
        "instruction": "Always answer with hello.",
    }
    with TestClient(captured["app"]) as client:
        project_response = client.post(
            "/web/generated-agent-projects",
            json={"draft": draft},
        )
        assert project_response.status_code == 200
        project = project_response.json()

        old_shape_response = client.post(
            "/web/generated-agent-test-runs",
            json={"name": "demo", "files": []},
        )
        assert old_shape_response.status_code == 422

        run_response = client.post(
            "/web/generated-agent-test-runs",
            json={"draft": draft},
        )
        assert run_response.status_code == 200
        run = run_response.json()
        assert run["appName"] == "demo_agent"
        assert run["runId"].startswith("tr_")

        process = _FakeProcess.created[-1]
        assert process.env["VOLCENGINE_ACCESS_KEY"] == "test-ak"
        assert process.env["VOLCENGINE_SECRET_KEY"] == "test-sk"
        generated_files = {
            str(path.relative_to(process.cwd)): path.read_text(encoding="utf-8")
            for path in Path(process.cwd).rglob("*")
            if path.is_file() and not path.name.startswith("runner.")
        }
        assert generated_files == {
            file["path"]: file["content"] for file in project["files"]
        }

        session_response = client.post(
            f"/web/generated-agent-test-runs/{run['runId']}/sessions",
            json={"userId": "test_user"},
        )
        assert session_response.status_code == 200
        assert session_response.json() == {"id": "session-1"}

        sse_response = client.post(
            f"/web/generated-agent-test-runs/{run['runId']}/run_sse",
            json={
                "user_id": "test_user",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hi"}]},
                "streaming": True,
            },
        )
        assert sse_response.status_code == 200
        assert '"text":"hello"' in sse_response.text
        assert _FakeAsyncClient.streamed_payloads[-1]["app_name"] == "demo_agent"

        runner_error = "RuntimeError: tenant model credential is unavailable"
        runner_marker = secrets.token_urlsafe(24)
        inline_marker = secrets.token_urlsafe(24)
        monkeypatch.setenv("MODEL_AGENT_API_KEY", runner_marker)
        (Path(process.cwd) / "runner.stderr.log").write_text(
            # lgtm[py/clear-text-storage-sensitive-data]
            f"{runner_error}\napi_key={runner_marker}\nauthToken={inline_marker}",
            encoding="utf-8",
        )
        monkeypatch.setattr("httpx.AsyncClient", _FakeRunnerErrorAsyncClient)

        session_error_response = client.post(
            f"/web/generated-agent-test-runs/{run['runId']}/sessions",
            json={"userId": "test_user"},
        )
        assert session_error_response.status_code == 500
        assert runner_error in session_error_response.json()["detail"]
        assert runner_marker not in session_error_response.json()["detail"]
        assert inline_marker not in session_error_response.json()["detail"]
        assert "api_key=***" in session_error_response.json()["detail"]
        assert "authToken=***" in session_error_response.json()["detail"]
        assert session_error_response.json()["detail"] != "Internal Server Error"

        sse_error_response = client.post(
            f"/web/generated-agent-test-runs/{run['runId']}/run_sse",
            json={
                "user_id": "test_user",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hi"}]},
                "streaming": True,
            },
        )
        assert sse_error_response.status_code == 200
        assert runner_error in sse_error_response.text
        assert runner_marker not in sse_error_response.text
        assert '"status_code": 500' in sse_error_response.text

        def _raise_process_error(*args: Any, **kwargs: Any) -> None:
            raise OSError("tenant debug process quota exhausted")

        monkeypatch.setattr("subprocess.Popen", _raise_process_error)
        create_error_response = client.post(
            "/web/generated-agent-test-runs",
            json={"draft": draft},
        )
        assert create_error_response.status_code == 500
        create_error_detail = create_error_response.json()["detail"]
        assert "创建调试环境失败" in create_error_detail
        assert "异常类型：OSError" in create_error_detail
        assert "错误 ID" in create_error_detail
        assert "tenant debug process quota exhausted" not in create_error_detail

        delete_response = client.delete(
            f"/web/generated-agent-test-runs/{run['runId']}"
        )
        assert delete_response.status_code == 200
        assert process.terminated
        assert not Path(process.cwd).exists()

        missing_response = client.post(
            f"/web/generated-agent-test-runs/{run['runId']}/sessions",
            json={"userId": "test_user"},
        )
        assert missing_response.status_code == 404


def test_generated_agent_debug_omits_stdio_mcp_on_remote_bind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    _FakeProcess.created.clear()
    monkeypatch.setattr("dotenv.find_dotenv", lambda: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )

    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        site_logo=None,
        site_title=None,
        host="0.0.0.0",
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
        open_browser=False,
    )

    monkeypatch.setattr("subprocess.Popen", _FakeProcess)
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    real_socket = socket.socket
    monkeypatch.setattr(
        "socket.socket",
        lambda *args, **kwargs: (
            real_socket(*args, **kwargs)
            if len(args) >= 4 or "fileno" in kwargs
            else _FakeSocket(*args, **kwargs)
        ),
    )

    draft = {
        "name": "demo-agent",
        "description": "Demo agent",
        "instruction": "Always answer with hello.",
        "mcpTools": [{"transport": "stdio", "command": "npx"}],
    }
    with TestClient(captured["app"]) as client:
        config_response = client.get("/web/ui-config")
        assert config_response.status_code == 200
        features = config_response.json()["features"]
        assert features["generatedAgentTestRun"] is True
        assert features["generatedAgentTestRunDisabledReason"] == ""

        project_response = client.post(
            "/web/generated-agent-projects",
            json={"draft": draft},
        )
        assert project_response.status_code == 200
        project_agent_py = next(
            file["content"]
            for file in project_response.json()["files"]
            if file["path"] == "agents/demo_agent/agent.py"
        )
        assert "StdioConnectionParams" in project_agent_py

        run_response = client.post(
            "/web/generated-agent-test-runs",
            json={"draft": draft},
        )
        assert run_response.status_code == 200
        run = run_response.json()
        assert run["appName"] == "demo_agent"
        assert run["runId"].startswith("tr_")

        process = _FakeProcess.created[-1]
        debug_agent_py = (
            Path(process.cwd) / "agents" / "demo_agent" / "agent.py"
        ).read_text(encoding="utf-8")
        assert "StdioConnectionParams" not in debug_agent_py
        assert "npx" not in debug_agent_py

        delete_response = client.delete(
            f"/web/generated-agent-test-runs/{run['runId']}"
        )
        assert delete_response.status_code == 200


def test_studio_deploy_run_script_allows_generated_agent_debug() -> None:
    run_script = _studio_deploy_run_script("site-logo.png")

    assert "HOST=0.0.0.0" in run_script
    assert "studio --auth-mode frontend" in run_script
    assert '--site-logo "$ROOT_DIR/site-logo.png"' in run_script
    assert "--allow-remote-generated-agent-test-run" not in run_script


def test_agentkit_app_adds_dynamic_a2a_tools_per_run() -> None:
    source = Path("veadk/integrations/agentkit/app.py").read_text()

    assert "build_remote_a2a_agent_tools(prompt, registry_config)" in source
    assert "def _spawn_dynamic_a2a_agent(" in source
    assert "def _configure_dynamic_a2a_routes(" in source
    assert "def _run_request_custom_metadata(" in source
    assert 'getattr(req, "custom_metadata", None)' in source
    assert "req.custom_metadata" not in source
    assert '@app.post("/run_sse")' in source
    assert '@app.post("/invoke")' in source
    assert "types.UserContent" in source
    assert '@app.post("/run", response_model=None)' in source


def test_frontend_deploy_forwards_a2a_registry_runtime_env_prefixes() -> None:
    source = Path("veadk/cli/cli_frontend.py").read_text()

    assert '"REGISTRY_",' in source
    assert '"A2A_REGISTRY_",' in source


def test_generated_agent_test_runner_enables_dynamic_a2a_helper() -> None:
    source = Path("veadk/cli/generated_agent_test_runner.py").read_text()

    assert "get_fast_api_app" in source
    assert "_bind_adk_server_services(app)" in source
    assert "_veadk_adk_server" in source
    assert "dynamic_a2a" in source
    assert "helper.enable_dynamic_a2a_tools(app, root_agent)" in source


def test_agentkit_dynamic_a2a_tools_use_user_prompt_once(monkeypatch) -> None:
    from veadk import Agent
    from veadk.a2a.registry_client import AgentKitA2ARegistryConfig
    from veadk.integrations.agentkit import app as agentkit_app
    from veadk.tools.builtin_tools import a2a_registry

    calls: list[str] = []

    def fake_build_remote_a2a_agent_tools(prompt, config):
        calls.append(prompt)
        assert config.space_id == "space-test"

        def remote_a2a_reliability_review(input: str):
            return {"input": input}

        return [remote_a2a_reliability_review]

    monkeypatch.setattr(
        a2a_registry,
        "build_remote_a2a_agent_tools",
        fake_build_remote_a2a_agent_tools,
    )
    agent = Agent(name="demo", instruction="x", model_api_key="fake")
    setattr(
        agent,
        "_veadk_a2a_registry_config",
        AgentKitA2ARegistryConfig(space_id="space-test"),
    )

    cloned = agentkit_app._spawn_dynamic_a2a_agent(
        agent,
        "你是否拥有 remote_a2a 开头的工具？",
    )

    assert calls == [
        "你是否拥有 remote_a2a 开头的工具？",
    ]
    assert "remote_a2a_reliability_review" in {
        getattr(tool, "__name__", "") for tool in cloned.tools
    }
