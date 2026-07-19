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
import socket
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from veadk.cli.cli_frontend import _run_frontend_server, _studio_deploy_run_script
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


# These hashes were produced from the legacy frontend generator before backend
# codegen became the trusted implementation. They intentionally lock the full
# generated file contents, not just Python syntax or selected snippets.
_MINIMAL_FRONTEND_GOLDEN = {
    "app.py": "76fb40c6016bf2b70e35012d050b6a0e5be36233b6044e83e1002a3f71150bfb",
    "agents/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "agents/demo_agent/agent.py": "6e5bbd448439c7f50f5400227680130e897dd71e8251cb4eb4594c98f4889589",
    "agents/demo_agent/__init__.py": "acb6368da255ff70d6760c00085c893aa0b2d973768d293a22bb7181fb1e3448",
    ".env.example": "1cdb6e1bfe38616d5d46095ba88ba76a0c189f3d2999bf0dd23b7145ce103ab2",
    "requirements.txt": "a7bb29cb47b916a81b626907fcdf84eed525ca22b4214ddc82f96a5ba87c8cc8",
    "README.md": "16cbec845b595949c071f3bcf4c056d862b9e2277c00e5d23649b5540dfde83e",
}

_FULL_FRONTEND_GOLDEN = {
    "app.py": "bce061ef2a9db0ba8fa2c82c94ae682f166d96bca4d580e99fcaacca71b9a682",
    "agents/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "agents/full_agent/agent.py": "d77ee467c4895b1a160927fb551a65d424b68319fc2941014dc5d499edbace68",
    "agents/full_agent/__init__.py": "acb6368da255ff70d6760c00085c893aa0b2d973768d293a22bb7181fb1e3448",
    ".env.example": "cb35eed98b4155c755df934f61ca6760293d59508de0a6090632e44501f82748",
    "requirements.txt": "5230e5c9a20b97dc95cc753247b4240d7401d9f9b46aa62da851c91552061ba7",
    "README.md": "ce6e5ada2031657b5de320465a34cb8c066c6c4181ab111dfb40299d3ec0bcd0",
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
        enableA2ui=True,
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
    project = generate_project_from_draft(_full_draft())

    assert project.name == "full_agent"
    assert _content_hashes(project) == _FULL_FRONTEND_GOLDEN


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
    assert '"id": agent_id' in app_py
    assert '"name": AGENT_DISPLAY_NAMES.get(agent_id, agent_id)' in app_py


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


class _FakeProcess:
    created: list["_FakeProcess"] = []

    def __init__(self, cmd: list[str], *, cwd: str, **kwargs: Any) -> None:
        self.cmd = cmd
        self.cwd = cwd
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


def test_generated_project_and_debug_run_api_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    _FakeProcess.created.clear()
    _FakeAsyncClient.streamed_payloads.clear()

    monkeypatch.setattr("dotenv.find_dotenv", lambda: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )

    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
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
    run_script = _studio_deploy_run_script()

    assert "HOST=0.0.0.0" in run_script
    assert "studio --auth-mode frontend" in run_script
    assert "--allow-remote-generated-agent-test-run" not in run_script
