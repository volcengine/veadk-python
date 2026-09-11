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

"""Tests for the mpa Codex worker Tool orchestration (FR-12/13, AC-11)."""

from types import SimpleNamespace

import pytest

from veadk.integrations.mpa.mpa_tool import (
    CODEX_WORKER_TOOL_DEFAULTS,
    MpaToolError,
    ensure_codex_worker_tool,
)


class _FakeToolsClient:
    """Minimal stub of AgentkitToolsClient recording calls."""

    def __init__(self, *, existing=None, reference_envs=None, create_status="Ready"):
        self._existing = existing or []
        self._reference_envs = reference_envs or []
        self._create_status = create_status
        self.created = None
        self.create_calls = 0

    def list_tools(self, request):
        # Filter by name if provided.
        wanted = None
        for f in getattr(request, "filters", None) or []:
            wanted = getattr(f, "name", None)
        tools = [t for t in self._existing if wanted is None or t.name == wanted]
        return SimpleNamespace(tools=tools, next_token=None)

    def get_tool(self, request):
        for t in self._existing:
            if t.tool_id == request.tool_id:
                return SimpleNamespace(
                    tool_id=t.tool_id,
                    name=t.name,
                    status=(self._create_status if t.status != "Ready" else t.status),
                    envs=[
                        SimpleNamespace(key=k, value=v) for k, v in self._reference_envs
                    ],
                )
        raise KeyError(request.tool_id)

    def create_tool(self, request):
        self.create_calls += 1
        self.created = request
        # Register the created tool so a subsequent get_tool sees it Ready.
        self._existing.append(
            SimpleNamespace(
                tool_id="t-new",
                name=request.name,
                tool_type="Private",
                status="Creating",
            )
        )
        return SimpleNamespace(tool_id="t-new")


def _reference_tool():
    return SimpleNamespace(
        tool_id="t-ref", name="ref-codex", tool_type="Private", status="Ready"
    )


def test_reuse_existing_ready_tool_by_name() -> None:
    """AC-11: a Ready tool with the target name is reused; CreateTool not called."""
    existing = [
        SimpleNamespace(
            tool_id="t-existing",
            name="mpa-agent-e2e-worker",
            tool_type="Private",
            status="Ready",
        )
    ]
    client = _FakeToolsClient(existing=existing)
    tool_id = ensure_codex_worker_tool(
        client,
        name="mpa-agent-e2e-worker",
        image="registry.example.com/mpa_codex_worker:tag",
    )
    assert tool_id == "t-existing"
    assert client.create_calls == 0


def test_create_tool_uses_verified_contract_and_clones_reference_env() -> None:
    """AC-11: CreateTool uses the codex worker contract and clones reference env."""
    ref_envs = [("WAIT_PORTS", "8091"), ("USER", "gem"), ("PUBLIC_PORT", "8000")]
    client = _FakeToolsClient(existing=[_reference_tool()], reference_envs=ref_envs)

    tool_id = ensure_codex_worker_tool(
        client,
        name="mpa-agent-e2e-worker",
        image="registry.example.com/mpa_codex_worker:tag",
        reference_tool_id="t-ref",
        role_name="CustomMpaRole",
        wait_ready=True,
        poll_interval=0,
    )
    assert tool_id == "t-new"
    assert client.create_calls == 1

    req = client.created
    assert req.image_url == "registry.example.com/mpa_codex_worker:tag"
    assert req.tool_type == CODEX_WORKER_TOOL_DEFAULTS["tool_type"] == "Private"
    assert req.command == CODEX_WORKER_TOOL_DEFAULTS["command"] == "/opt/gem/run.sh"
    assert req.port == CODEX_WORKER_TOOL_DEFAULTS["port"] == 8000
    assert req.cpu_milli == CODEX_WORKER_TOOL_DEFAULTS["cpu_milli"]
    assert req.memory_mb == CODEX_WORKER_TOOL_DEFAULTS["memory_mb"]
    assert req.role_name == "CustomMpaRole"
    # Reference env cloned.
    env_keys = {e.key for e in (req.envs or [])}
    assert {"WAIT_PORTS", "USER", "PUBLIC_PORT"}.issubset(env_keys)
    # Key auth authorizer present.
    assert req.authorizer_configuration is not None


def test_create_tool_waits_until_ready_then_returns_id() -> None:
    """AC-11: creation waits for Ready before returning the id."""
    client = _FakeToolsClient(existing=[_reference_tool()], create_status="Ready")
    tool_id = ensure_codex_worker_tool(
        client,
        name="w",
        image="img:tag",
        reference_tool_id="t-ref",
        wait_ready=True,
        poll_interval=0,
    )
    assert tool_id == "t-new"


def test_missing_image_when_creating_raises() -> None:
    """A create path without an image is a clear error."""
    client = _FakeToolsClient(existing=[])
    with pytest.raises(MpaToolError, match="image"):
        ensure_codex_worker_tool(client, name="w", image="")


def test_existing_non_ready_tool_is_awaited_not_duplicated() -> None:
    existing = [SimpleNamespace(tool_id="t-existing", name="worker", status="Creating")]
    client = _FakeToolsClient(existing=existing, create_status="Ready")

    tool_id = ensure_codex_worker_tool(
        client, name="worker", image="img:tag", poll_interval=0
    )

    assert tool_id == "t-existing"
    assert client.create_calls == 0


def test_duplicate_tool_names_fail_instead_of_reusing_arbitrarily() -> None:
    existing = [
        SimpleNamespace(tool_id="t-one", name="worker", status="Ready"),
        SimpleNamespace(tool_id="t-two", name="worker", status="Ready"),
    ]
    client = _FakeToolsClient(existing=existing)

    with pytest.raises(MpaToolError, match="multiple tools.*worker"):
        ensure_codex_worker_tool(client, name="worker", image="img:tag")
    assert client.create_calls == 0
