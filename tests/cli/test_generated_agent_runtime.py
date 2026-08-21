from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import pytest

from veadk.cli.generated_agent_codegen import GeneratedFile, GeneratedProject
from veadk.cli.generated_agent_runtime import (
    GeneratedAgentRuntimeError,
    GeneratedAgentRuntimeManager,
    GeneratedProjectAttestor,
    _parse_sse,
)


class _Response:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        chunks: tuple[bytes, ...] = (),
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._chunks = chunks
        self.text = b"".join(chunks).decode("utf-8", "replace")

    def json(self) -> Any:
        return self._json_data

    async def aread(self) -> bytes:
        return b"".join(self._chunks)

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _HttpClient:
    run_payloads: ClassVar[list[dict[str, Any]]] = []
    session_requests: ClassVar[list[tuple[str, dict[str, Any]]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def __aenter__(self) -> _HttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str) -> _Response:
        if url.endswith("/list-apps"):
            return _Response(json_data=["demo_agent"])
        assert url.endswith("/debug/trace/session/evaluation-session-1")
        return _Response(
            json_data=[
                {
                    "name": "call_llm",
                    "trace_id": "trace-1",
                    "span_id": "span-1",
                }
            ]
        )

    async def post(self, url: str, *, json: dict[str, Any]) -> _Response:
        self.session_requests.append((url, json))
        return _Response(json_data={"id": "runner-session-1"})

    def stream(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any],
        **kwargs: Any,
    ) -> _Response:
        del kwargs
        assert method == "POST"
        assert url.endswith("/run_sse")
        self.run_payloads.append(json)
        return _Response(
            chunks=(
                b'data: {"partial":true,"content":{"parts":[{"text":"par',
                b'tial"}]}}\n\n',
                b'data: {"content":{"parts":[{"text":"final answer"}]}}\n\n',
            )
        )


class _Process:
    created: ClassVar[list[_Process]] = []

    def __init__(self, cmd: list[str], *, cwd: str, **kwargs: Any) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.environment = dict(kwargs["env"])
        self.returncode: int | None = None
        self.terminated = False
        self.created.append(self)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return self.returncode or 0

    def kill(self) -> None:
        self.returncode = -9


class _NeverReadyHttpClient(_HttpClient):
    async def get(self, url: str) -> _Response:
        assert url.endswith("/list-apps")
        return _Response(status_code=503, json_data=[])


def test_project_attestation_binds_owner_source_and_expiry() -> None:
    now = [100.0]
    attestor = GeneratedProjectAttestor(
        ttl_seconds=10,
        secret=b"test-attestation-key-material",
        clock=lambda: now[0],
    )
    project = GeneratedProject(
        name="demo_agent",
        files=[
            GeneratedFile(path="app.py", content="app = object()\n"),
            GeneratedFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            ),
        ],
    )
    proof = attestor.attest(project, owner_id="developer-1")

    attestor.verify(
        GeneratedProject(name=project.name, files=list(reversed(project.files))),
        owner_id="developer-1",
        attestation=proof,
    )
    with pytest.raises(GeneratedAgentRuntimeError):
        attestor.verify(
            project.model_copy(
                update={
                    "files": [
                        GeneratedFile(
                            path="agents/demo_agent/agent.py",
                            content="raise RuntimeError('tampered')\n",
                        )
                    ]
                }
            ),
            owner_id="developer-1",
            attestation=proof,
        )
    with pytest.raises(GeneratedAgentRuntimeError):
        attestor.verify(
            project,
            owner_id="developer-2",
            attestation=proof,
        )
    now[0] = 111.0
    with pytest.raises(GeneratedAgentRuntimeError):
        attestor.verify(
            project,
            owner_id="developer-1",
            attestation=proof,
        )


def test_project_attestation_accepts_rotated_verification_key() -> None:
    project = GeneratedProject(
        name="demo_agent",
        files=[GeneratedFile(path="app.py", content="app = object()\n")],
    )
    previous = GeneratedProjectAttestor(secret=b"previous-secret")
    proof = previous.attest(project, owner_id="developer-1")
    current = GeneratedProjectAttestor(
        secret=b"current-secret",
        verification_secrets=(b"previous-secret",),
    )

    current.verify(project, owner_id="developer-1", attestation=proof)


def test_agent_identity_attestation_binds_owner_name_and_region() -> None:
    attestor = GeneratedProjectAttestor(secret=b"identity-secret")
    proof = attestor.attest_identity(
        owner_id="developer-1",
        agent_id="runtime-one",
        region="cn-beijing",
    )

    attestor.verify_identity(
        owner_id="developer-1",
        agent_id="runtime-one",
        region="cn-beijing",
        attestation=proof,
    )
    with pytest.raises(GeneratedAgentRuntimeError):
        attestor.verify_identity(
            owner_id="developer-1",
            agent_id="runtime-two",
            region="cn-beijing",
            attestation=proof,
        )


@pytest.mark.asyncio
async def test_runtime_executes_case_and_removes_owned_project_on_close(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    _Process.created.clear()
    _HttpClient.run_payloads.clear()
    _HttpClient.session_requests.clear()
    monkeypatch.setattr("subprocess.Popen", _Process)
    monkeypatch.setattr("httpx.AsyncClient", _HttpClient)
    monkeypatch.setattr(
        "veadk.cli.generated_agent_runtime.tempfile.mkdtemp",
        lambda **_: str(runtime_dir),
    )
    monkeypatch.setattr(
        "veadk.cli.generated_agent_runtime._free_local_port",
        lambda: 54321,
    )
    manager = GeneratedAgentRuntimeManager(
        ttl_seconds=60,
        id_factory=lambda: "runtime-1",
        clock=lambda: 100.0,
    )
    project = GeneratedProject(
        name="demo_agent",
        files=[
            GeneratedFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            )
        ],
    )

    handle = await manager.create(
        project,
        environment={"SAFE_RUNTIME_VALUE": "enabled"},
        owner_id="developer-1",
        plan_hash="sha256:test-plan",
    )
    created_session_id = await manager.create_session(
        handle,
        user_id="evaluation user",
    )
    evidence = await manager.run_case(
        handle,
        user_id="evaluation-user",
        session_id="evaluation-session-1",
        prompt="where is my order?",
    )

    assert handle.runtime_id == "runtime-1"
    assert handle.plan_hash == "sha256:test-plan"
    assert manager.base_url(handle) == "http://127.0.0.1:54321"
    assert handle.app_name == "demo_agent"
    assert (runtime_dir / "agents/demo_agent/agent.py").read_text() == (
        "root_agent = object()\n"
    )
    assert _Process.created[0].environment["SAFE_RUNTIME_VALUE"] == "enabled"
    assert _Process.created[0].environment["HOME"] == str(runtime_dir)
    assert _Process.created[0].environment["TMPDIR"] == str(runtime_dir)
    assert created_session_id == "runner-session-1"
    assert _HttpClient.session_requests == [
        (
            "http://127.0.0.1:54321/apps/demo_agent/users/evaluation%20user/sessions",
            {},
        )
    ]
    assert _HttpClient.run_payloads == [
        {
            "app_name": "demo_agent",
            "user_id": "evaluation-user",
            "session_id": "evaluation-session-1",
            "new_message": {
                "role": "user",
                "parts": [{"text": "where is my order?"}],
            },
            "streaming": True,
        }
    ]
    assert evidence.output == "final answer"
    assert evidence.trace == (
        {
            "name": "call_llm",
            "trace_id": "trace-1",
            "span_id": "span-1",
        },
    )
    assert evidence.trace_ref == (
        "generated-agent-runtime://runtime-1/trace/evaluation-session-1"
    )

    await manager.close(handle)

    assert _Process.created[0].terminated is True
    assert not runtime_dir.exists()


@pytest.mark.asyncio
async def test_readiness_timeout_does_not_depend_on_expiry_clock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "never-ready-runtime"
    monkeypatch.setattr("subprocess.Popen", _Process)
    monkeypatch.setattr("httpx.AsyncClient", _NeverReadyHttpClient)
    monkeypatch.setattr(
        "veadk.cli.generated_agent_runtime.tempfile.mkdtemp",
        lambda **_: str(runtime_dir),
    )
    monkeypatch.setattr(
        "veadk.cli.generated_agent_runtime._free_local_port",
        lambda: 54322,
    )
    manager = GeneratedAgentRuntimeManager(
        ttl_seconds=60,
        id_factory=lambda: "runtime-never-ready",
        clock=lambda: 100.0,
        ready_timeout_seconds=0.01,
    )

    with pytest.raises(
        GeneratedAgentRuntimeError,
        match="did not become ready",
    ):
        await asyncio.wait_for(
            manager.create(
                GeneratedProject(
                    name="demo_agent",
                    files=[
                        GeneratedFile(
                            path="agents/demo_agent/agent.py",
                            content="root_agent = object()\n",
                        )
                    ],
                ),
                environment={"SAFE_RUNTIME_VALUE": "enabled"},
                owner_id="developer-1",
            ),
            timeout=2.0,
        )

    assert not runtime_dir.exists()


@pytest.mark.asyncio
async def test_runtime_concurrency_limit_is_owner_scoped_while_creating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_owner_started = asyncio.Event()
    release_first_owner = asyncio.Event()

    class _OwnerScopedReadinessHttpClient(_HttpClient):
        async def get(self, url: str) -> _Response:
            assert url.endswith("/list-apps")
            if ":54321/" in url:
                first_owner_started.set()
                await release_first_owner.wait()
            return _Response(json_data=["demo_agent"])

    _Process.created.clear()
    monkeypatch.setattr("subprocess.Popen", _Process)
    monkeypatch.setattr("httpx.AsyncClient", _OwnerScopedReadinessHttpClient)
    ports = iter((54321, 54322))
    monkeypatch.setattr(
        "veadk.cli.generated_agent_runtime._free_local_port",
        lambda: next(ports),
    )
    manager = GeneratedAgentRuntimeManager(
        ttl_seconds=60,
        max_active_per_owner=1,
    )
    project = GeneratedProject(
        name="demo_agent",
        files=[
            GeneratedFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            )
        ],
    )

    first_owner_task = asyncio.create_task(
        manager.create(project, environment={}, owner_id="developer-1")
    )
    await asyncio.wait_for(first_owner_started.wait(), timeout=0.5)
    second_owner_handle = None
    try:
        with pytest.raises(GeneratedAgentRuntimeError) as error:
            await manager.create(
                project,
                environment={},
                owner_id="developer-1",
            )
        assert error.value.status_code == 429

        second_owner_handle = await manager.create(
            project,
            environment={},
            owner_id="developer-2",
        )
    finally:
        release_first_owner.set()

    first_owner_handle = await first_owner_task
    await manager.close(first_owner_handle)
    if second_owner_handle is not None:
        await manager.close(second_owner_handle)


@pytest.mark.asyncio
async def test_sse_parser_preserves_multibyte_text_split_across_chunks() -> None:
    encoded = 'data: {"content":{"parts":[{"text":"中文回答"}]}}\n\n'.encode()

    async def chunks():
        for byte in encoded:
            yield bytes((byte,))

    events = [event async for event in _parse_sse(chunks())]

    assert events == [{"content": {"parts": [{"text": "中文回答"}]}}]
