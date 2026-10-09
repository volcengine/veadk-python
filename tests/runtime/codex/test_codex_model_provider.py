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

"""Codex model routing: transport choice, route shape, lean thread config.

The last test drives the real Codex binary against a stub Responses model
(opt in with ``CODEX_RUN_SMOKE=1``) to prove the thread-level config actually
reaches the wire.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from veadk.runtime.codex.config import CodexRuntimeConfig
from veadk.runtime.codex.model_provider import (
    DIRECT_KEY_ENV,
    CodexModelRoute,
    direct_route,
    lean_codex_config,
    resolve_transport,
    shim_route,
)

_SECRET = "sk-test-secret-value-0123456789"


# --------------------------------------------------------------- transport


@pytest.mark.parametrize(
    "api_base",
    [
        "https://ark.cn-beijing.volces.com/api/v3",
        "https://ARK.CN-BEIJING.VOLCES.COM/api/v3/",
        "https://ark.cn-beijing.volces.com:443/api/v3/responses",
        "ark.cn-beijing.volces.com/api/v3",
        "https://volces.com/api/v3",
        "https://ark.ap-southeast.bytepluses.com/api/v3",
        "https://ark.ap-southeast.BytePlusES.com:8443",
        "https://api.openai.com/v1",
        "https://API.OPENAI.COM",
    ],
)
def test_auto_picks_direct_for_responses_hosts(api_base: str) -> None:
    assert resolve_transport(CodexRuntimeConfig(), api_base) == "direct"


@pytest.mark.parametrize(
    "api_base",
    [
        "https://example.com/v1",
        "http://127.0.0.1:8000/v1",
        "https://evilvolces.com/api/v3",
        "https://volces.com.evil.io/api/v3",
        "https://api.openai.com.evil.io/v1",
        "https://proxy.example.com/ark.cn-beijing.volces.com/api/v3",
        "https://notapi.openai.com/v1",
        "",
    ],
)
def test_auto_picks_shim_for_unknown_hosts(api_base: str) -> None:
    assert resolve_transport(CodexRuntimeConfig(), api_base) == "shim"


@pytest.mark.parametrize(
    ("configured", "api_base", "expected"),
    [
        ("direct", "https://example.com/v1", "direct"),
        ("shim", "https://ark.cn-beijing.volces.com/api/v3", "shim"),
        ("auto", "https://ark.cn-beijing.volces.com/api/v3", "direct"),
        ("auto", "https://example.com/v1", "shim"),
    ],
)
def test_explicit_transport_wins(configured: str, api_base: str, expected: str) -> None:
    config = CodexRuntimeConfig(model_transport=configured)
    assert resolve_transport(config, api_base) == expected


def test_model_transport_defaults_to_auto_and_rejects_unknown() -> None:
    assert CodexRuntimeConfig().model_transport == "auto"
    with pytest.raises(ValidationError):
        CodexRuntimeConfig(model_transport="bogus")


@pytest.mark.parametrize(
    ("env_value", "api_base", "expected"),
    [
        ("shim", "https://ark.cn-beijing.volces.com/api/v3", "shim"),
        (" DIRECT ", "https://example.com/v1", "direct"),
        ("auto", "https://example.com/v1", "shim"),
    ],
)
def test_env_override_reaches_resolution(
    monkeypatch: pytest.MonkeyPatch, env_value: str, api_base: str, expected: str
) -> None:
    monkeypatch.setenv("VEADK_CODEX_MODEL_TRANSPORT", env_value)
    agent = SimpleNamespace(codex_runtime_config={"model_transport": "direct"})
    config = CodexRuntimeConfig.from_agent(agent)
    assert resolve_transport(config, api_base) == expected


def test_env_override_absent_keeps_agent_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEADK_CODEX_MODEL_TRANSPORT", raising=False)
    agent = SimpleNamespace(codex_runtime_config={"model_transport": "shim"})
    assert CodexRuntimeConfig.from_agent(agent).model_transport == "shim"


def test_env_override_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEADK_CODEX_MODEL_TRANSPORT", "sideways")
    with pytest.raises(ValidationError):
        CodexRuntimeConfig.from_agent(SimpleNamespace())


# ----------------------------------------------- thread mode and turn bounds


def test_thread_mode_defaults_to_resume_and_rejects_unknown() -> None:
    """``thread_mode`` is a closed set; a typo must fail at config time.

    Accepting an unknown value would leave the runtime's
    ``thread_mode == "resume"`` check false, silently turning a misspelt
    ``"resume"`` into ephemeral threads that forget every earlier turn.
    """
    assert CodexRuntimeConfig().thread_mode == "resume"
    assert CodexRuntimeConfig(thread_mode="ephemeral").thread_mode == "ephemeral"
    with pytest.raises(ValidationError):
        CodexRuntimeConfig(thread_mode="persistent")


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [("ephemeral", "ephemeral"), (" RESUME ", "resume"), ("Ephemeral\n", "ephemeral")],
)
def test_thread_mode_env_override(
    monkeypatch: pytest.MonkeyPatch, env_value: str, expected: str
) -> None:
    """``VEADK_CODEX_THREAD_MODE`` overrides the agent, case/space-insensitively.

    It is the deployment-level switch (e.g. to fall back to ephemeral threads
    without a code change), so it must win over the agent's own setting.
    """
    monkeypatch.setenv("VEADK_CODEX_THREAD_MODE", env_value)
    other = "resume" if expected == "ephemeral" else "ephemeral"
    agent = SimpleNamespace(codex_runtime_config={"thread_mode": other})
    assert CodexRuntimeConfig.from_agent(agent).thread_mode == expected


def test_thread_mode_env_absent_keeps_agent_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEADK_CODEX_THREAD_MODE", raising=False)
    agent = SimpleNamespace(codex_runtime_config={"thread_mode": "ephemeral"})
    assert CodexRuntimeConfig.from_agent(agent).thread_mode == "ephemeral"


def test_thread_mode_env_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEADK_CODEX_THREAD_MODE", "forever")
    with pytest.raises(ValidationError):
        CodexRuntimeConfig.from_agent(SimpleNamespace())


@pytest.mark.parametrize("field", ["turn_timeout_seconds", "auto_compact_token_limit"])
@pytest.mark.parametrize("value", [0, -1])
def test_turn_bounds_reject_non_positive(field: str, value: int) -> None:
    """Zero is not "no bound"; ``None`` is.

    A zero turn timeout would fail every turn the moment it starts, and a zero
    compaction limit would make Codex compact on every turn. Both read
    like "off" to a user, so they are rejected rather than applied.
    """
    with pytest.raises(ValidationError):
        CodexRuntimeConfig(**{field: value})
    assert getattr(CodexRuntimeConfig(**{field: None}), field) is None
    assert getattr(CodexRuntimeConfig(**{field: 1}), field) == 1


# ------------------------------------------------------------------- routes


@pytest.mark.parametrize(
    "api_base",
    [
        "https://ark.cn-beijing.volces.com/api/v3",
        "https://ark.cn-beijing.volces.com/api/v3/",
        "https://ark.cn-beijing.volces.com/api/v3/responses",
        "https://ark.cn-beijing.volces.com/api/v3/responses/",
    ],
)
def test_direct_route_normalizes_base_url(api_base: str) -> None:
    route = direct_route(api_base, _SECRET)
    assert route.provider_config["base_url"] == (
        "https://ark.cn-beijing.volces.com/api/v3"
    )


def test_direct_route_shape_keeps_key_out_of_config_and_repr() -> None:
    route = direct_route(
        "https://ark.cn-beijing.volces.com/api/v3",
        _SECRET,
        extra_headers={"X-Client": "veadk"},
    )
    assert route.transport == "direct"
    assert route.provider_config == {
        "name": route.provider_id,
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "env_key": DIRECT_KEY_ENV,
        "wire_api": "responses",
        "request_max_retries": 2,
        "stream_max_retries": 2,
        "http_headers": {"X-Client": "veadk"},
    }
    assert route.env == {DIRECT_KEY_ENV: _SECRET}
    # The key may live only in env: not in any config Codex is handed, and
    # not in anything a log line would render.
    assert _SECRET not in json.dumps(route.provider_config)
    assert _SECRET not in json.dumps(route.thread_config())
    assert _SECRET not in repr(route)
    assert _SECRET not in str(route)
    # The env var is named like a credential, so `codex_subprocess_env` masks
    # any value inherited from the host.
    assert "API_KEY" in DIRECT_KEY_ENV


def test_direct_route_without_headers_omits_header_key() -> None:
    route = direct_route("https://api.openai.com/v1", _SECRET)
    assert "http_headers" not in route.provider_config


@pytest.mark.parametrize(
    ("api_base", "api_key"),
    [
        ("https://api.openai.com/v1", ""),
        ("ftp://api.openai.com/v1", _SECRET),
        ("api.openai.com/v1", _SECRET),
        ("", _SECRET),
    ],
)
def test_direct_route_rejects_bad_input(api_base: str, api_key: str) -> None:
    with pytest.raises(ValueError) as exc:
        direct_route(api_base, api_key)
    assert _SECRET not in str(exc.value)


def test_shim_route_matches_prepared_codex_home() -> None:
    route = shim_route("http://127.0.0.1:4321/", "turn-token-xyz")
    assert route.transport == "shim"
    assert route.provider_id == "veadk"
    assert route.provider_config == {
        "name": "veadk",
        "base_url": "http://127.0.0.1:4321/v1",
        "env_key": "VEADK_CODEX_API_KEY",
        "wire_api": "responses",
    }
    assert route.env == {"VEADK_CODEX_API_KEY": "turn-token-xyz"}
    assert "turn-token-xyz" not in repr(route)


def test_shim_provider_id_matches_runtime() -> None:
    runtime = pytest.importorskip("veadk.runtime.codex.runtime")
    assert shim_route("http://x", "t").provider_id == runtime._PROVIDER_ID


# -------------------------------------------------------------- lean config


def test_lean_codex_config_contents() -> None:
    assert lean_codex_config() == {
        "model_reasoning_summary": "none",
        "web_search": "disabled",
        "features": {
            "unbounded_connection_retries": False,
            "goals": False,
            "multi_agent": False,
            "view_image": False,
        },
        "tools": {"experimental_request_user_input": {"enabled": False}},
        "shell_environment_policy": {
            "exclude": ["VEADK_CODEX_*", "*API_KEY*", "*SECRET*", "*TOKEN*"]
        },
    }


def test_thread_config_merges_provider_and_is_fresh() -> None:
    route = direct_route("https://api.openai.com/v1", _SECRET)
    config = route.thread_config()
    assert config["model_providers"] == {route.provider_id: route.provider_config}
    for key, value in lean_codex_config().items():
        assert config[key] == value
    # Mutating one result must not leak into the route or the next result.
    config["features"]["goals"] = True
    config["model_providers"][route.provider_id]["base_url"] = "mutated"
    again = route.thread_config()
    assert again["features"]["goals"] is False
    assert route.provider_config["base_url"] == "https://api.openai.com/v1"


def test_route_is_frozen() -> None:
    route = shim_route("http://x", "t")
    assert isinstance(route, CodexModelRoute)
    with pytest.raises(Exception):
        route.transport = "direct"  # type: ignore[misc]


# ------------------------------------------------------------ real binary


_TRIMMED_TOOLS = {
    "multi_agent_v1",
    "web_search",
    "view_image",
    "create_goal",
    "get_goal",
    "update_goal",
    "request_user_input",
}


def _tool_names(body: dict[str, Any]) -> set[str]:
    return {
        str(tool.get("name") or tool.get("type"))
        for tool in body.get("tools") or []
        if isinstance(tool, dict)
    }


def _sse(body: dict[str, Any]):
    base = {
        "id": f"resp_{uuid.uuid4().hex[:12]}",
        "object": "response",
        "created_at": int(time.time()),
        "model": body.get("model", "stub"),
        "status": "in_progress",
        "output": [],
    }
    item = {
        "type": "message",
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "done", "annotations": []}],
    }
    usage = {
        "input_tokens": 1,
        "output_tokens": 1,
        "total_tokens": 2,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }

    def event(kind: str, **data: Any) -> str:
        return f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n"

    yield event("response.created", response=base)
    yield event("response.output_item.added", output_index=0, item=item)
    yield event("response.output_item.done", output_index=0, item=item)
    yield event(
        "response.completed",
        response=dict(base, status="completed", output=[item], usage=usage),
    )


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_codex_honours_direct_route_thread_config() -> None:
    """The thread-level route config must reach the wire, not just parse.

    Codex silently ignores unknown or misplaced keys, so the only proof that
    the lean settings work as a ``thread_start(config=...)`` override is the
    request the real binary sends: no reasoning summary, no trimmed tools, and
    the route's key as the bearer token.
    """
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip("set CODEX_RUN_SMOKE=1 to spawn the real Codex binary")
    from tests.runtime.codex.test_codex_runtime_smoke import _skip_reason

    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)

    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import StreamingResponse
    from starlette.routing import Route
    from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox

    from veadk.runtime.codex.config import codex_subprocess_env

    captured: list[dict[str, Any]] = []

    # Plain Starlette: FastAPI cannot resolve a locally imported `Request`
    # annotation under `from __future__ import annotations`.
    async def responses(request):
        body = await request.json()
        captured.append(
            {
                "authorization": request.headers.get("authorization"),
                "x_client": request.headers.get("x-client"),
                "body": body,
            }
        )
        return StreamingResponse(_sse(body), media_type="text/event-stream")

    app = Starlette(routes=[Route("/v1/responses", responses, methods=["POST"])])
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    )
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    serve_task = asyncio.create_task(server.serve())
    home = tempfile.mkdtemp(prefix="veadk-codex-route-home-")
    workspace = tempfile.mkdtemp(prefix="veadk-codex-route-ws-")
    try:
        while not server.started:
            if serve_task.done():
                serve_task.result()
            await asyncio.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]

        route = direct_route(
            f"http://127.0.0.1:{port}/v1/",
            _SECRET,
            extra_headers={"X-Client": "veadk"},
        )
        env = codex_subprocess_env(home, "unused-turn-token")
        env.update(route.env)

        async def _run() -> Any:
            async with AsyncCodex(config=CodexConfig(cwd=workspace, env=env)) as codex:
                thread = await codex.thread_start(
                    model="stub-model",
                    model_provider=route.provider_id,
                    config=route.thread_config(),
                    approval_mode=ApprovalMode.deny_all,
                    sandbox=Sandbox.read_only,
                    ephemeral=True,
                    cwd=workspace,
                )
                turn = await thread.turn("hello")
                status = None
                async for note in turn.stream():
                    if note.method == "turn/completed":
                        status = note.payload.turn.status
                return getattr(status, "value", status)

        status = await asyncio.wait_for(_run(), 90)
    finally:
        server.should_exit = True
        await asyncio.gather(serve_task, return_exceptions=True)
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(workspace, ignore_errors=True)

    assert status == "completed", status
    assert captured, "Codex never reached the stub model"
    for request in captured:
        body = request["body"]
        assert request["authorization"] == f"Bearer {_SECRET}"
        assert request["x_client"] == "veadk"
        assert "summary" not in (body.get("reasoning") or {}), body.get("reasoning")
        tools = _tool_names(body)
        assert not tools & _TRIMMED_TOOLS, sorted(tools & _TRIMMED_TOOLS)
        assert "exec_command" in tools, sorted(tools)


def test_sensitive_headers_travel_by_env_not_in_the_config() -> None:
    """Credentials in extra headers must not land in Codex's config file."""
    route = direct_route(
        "https://ark.cn-beijing.volces.com/api/v3",
        _SECRET,
        extra_headers={
            "Authorization": "Bearer hdr-secret-1",
            "X-Api-Key": "hdr-secret-2",
            "x-is-encrypted": "true",
        },
    )

    config = route.provider_config
    assert config["http_headers"] == {"x-is-encrypted": "true"}
    names = config["env_http_headers"]
    assert set(names) == {"Authorization", "X-Api-Key"}
    assert {route.env[var] for var in names.values()} == {
        "Bearer hdr-secret-1",
        "hdr-secret-2",
    }
    assert all(var.startswith("VEADK_CODEX_") for var in names.values())
    assert "hdr-secret" not in repr(route.thread_config())


@pytest.mark.parametrize(
    ("name", "sensitive"),
    [
        ("Authorization", True),
        ("proxy-authorization", True),
        ("Cookie", True),
        ("X-Api-Key", True),
        ("x-session-token", True),
        ("X-Client-Secret", True),
        ("x-password", True),
        ("X-Signature", True),
        ("x-is-encrypted", False),
        ("veadk-source", False),
        ("User-Agent", False),
    ],
)
def test_is_sensitive_header(name: str, sensitive: bool) -> None:
    from veadk.runtime.codex.model_provider import is_sensitive_header

    assert is_sensitive_header(name) is sensitive
