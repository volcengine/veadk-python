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

"""Tests for AgentKit CreateRuntime orchestration (FR-15/16, AC-13)."""

from types import SimpleNamespace

import pytest

from veadk.integrations.mpa.mpa_runtime import (
    MpaRuntimeError,
    provision_runtime,
)


class _FakeRuntimeClient:
    def __init__(self, *, ready_after=1, api_key="rk-1", existing=None):
        self.create_calls = 0
        self.release_calls = 0
        self.update_calls = 0
        self._ready_after = ready_after
        self._get_calls = 0
        self._api_key = api_key
        self.create_request = None
        self.release_request = None
        self.update_request = None
        self.updated = False
        self.post_update_get_calls = 0
        self.current_version = 1
        self.existing = existing
        self.list_calls = 0

    def list_runtimes(self, request):
        self.list_calls += 1
        return SimpleNamespace(
            agent_kit_runtimes=[self.existing] if self.existing else [],
            next_token=None,
        )

    def create_runtime(self, request):
        self.create_calls += 1
        self.create_request = request
        return SimpleNamespace(runtime_id="r-new")

    def release_runtime(self, request):
        self.release_calls += 1
        self.release_request = request
        return SimpleNamespace()

    def update_runtime(self, request):
        self.update_calls += 1
        self.update_request = request
        self.updated = True
        return SimpleNamespace()

    def get_runtime(self, request):
        self._get_calls += 1
        if self.updated:
            self.post_update_get_calls += 1
            if self.post_update_get_calls == 1:
                status = "Ready"
                version = self.current_version
            else:
                status = "Ready"
                version = self.current_version + 1
        else:
            # First read (release-gating) sees Creating; then progress to Ready.
            status = "Ready" if self._get_calls >= self._ready_after else "Creating"
            version = self.current_version
        return SimpleNamespace(
            runtime_id="r-new",
            status=status,
            current_version_number=version,
            network_configurations=[
                SimpleNamespace(
                    network_type="public",
                    endpoint="https://gw123.apigateway-cn-beijing.volceapi.com",
                ),
            ],
            authorizer_configuration=SimpleNamespace(
                key_auth=SimpleNamespace(api_key=self._api_key)
            ),
        )


def _params():
    return {
        "name": "mpa-agent-e2e",
        "artifact_url": "registry.example.com/agentkit/mpa_agent:tag",
        "tool_id": "t-1",
        "role_name": "AgentKit_Runtime_Default_ServiceRole",
        "envs": {"MPA_AGENT_ID": "mi-x", "PGHOST": "pg"},
    }


def test_create_runtime_auto_release_skips_explicit_release() -> None:
    """AC-13: CreateRuntime auto-releases (status Creating) -> no explicit release.

    Verified live: an explicit ReleaseRuntime while Creating/Releasing returns
    InvalidResourceStatus, so provision_runtime must not call it in that state.
    """
    client = _FakeRuntimeClient(ready_after=2)
    result = provision_runtime(
        client,
        **_params(),
        resolve_apig_instance_id=lambda ep: "gw-123",
        poll_interval=0,
    )
    assert client.create_calls == 1
    assert client.release_calls == 0  # auto-released; no explicit release
    assert result["runtime_id"] == "r-new"
    assert (
        result["public_endpoint"] == "https://gw123.apigateway-cn-beijing.volceapi.com"
    )
    assert result["runtime_api_key"] == "rk-1"
    assert result["apig_instance_id"] == "gw-123"


def test_create_runtime_passes_envs_and_tool_id_never_to_release() -> None:
    """AC-13: envs + tool_id go to CreateRuntime; release is not called while
    the runtime auto-releases (Creating)."""
    client = _FakeRuntimeClient(ready_after=1)
    provision_runtime(
        client,
        **_params(),
        resolve_apig_instance_id=lambda ep: "gw-1",
        poll_interval=0,
    )
    req = client.create_request
    assert req.tool_id == "t-1"
    env_keys = {e.key for e in (req.envs or [])}
    assert {"MPA_AGENT_ID", "PGHOST"}.issubset(env_keys)
    # No explicit release while auto-release is in progress.
    assert client.release_calls == 0
    assert client.release_request is None


def test_update_public_url_uses_update_runtime_not_release() -> None:
    """A2A_PUBLIC_URL update is released and awaited before returning."""
    client = _FakeRuntimeClient(ready_after=1)
    provision_runtime(
        client,
        **_params(),
        resolve_apig_instance_id=lambda ep: "gw-1",
        poll_interval=0,
        reinject_public_url=True,
    )
    assert client.update_calls == 1
    assert client.update_request.release_enable is True
    assert client.post_update_get_calls >= 2
    upd_keys = {e.key for e in (client.update_request.envs or [])}
    assert "A2A_PUBLIC_URL" in upd_keys


def test_runtime_never_ready_raises() -> None:
    """AC-13 negative: a runtime that never readies fails with its id/status."""
    client = _FakeRuntimeClient(ready_after=999)
    with pytest.raises(MpaRuntimeError, match="r-new"):
        provision_runtime(
            client,
            **_params(),
            resolve_apig_instance_id=lambda ep: "gw-1",
            poll_interval=0,
            ready_timeout=0.0,
        )


def test_create_runtime_defaults_to_key_auth_authorizer() -> None:
    """AgentKit requires an authorizer; provision_runtime defaults to key auth."""
    client = _FakeRuntimeClient(ready_after=1)
    provision_runtime(
        client,
        **_params(),
        resolve_apig_instance_id=lambda ep: "gw-1",
        poll_interval=0,
    )
    assert client.create_request.authorizer_configuration is not None


def test_existing_runtime_with_exact_name_is_reused() -> None:
    """FR-13: an explicit same agent/runtime name makes retries idempotent."""
    existing = SimpleNamespace(name="mpa-agent-e2e", runtime_id="r-existing")
    client = _FakeRuntimeClient(ready_after=1, existing=existing)

    result = provision_runtime(
        client,
        **_params(),
        resolve_apig_instance_id=lambda ep: "gw-1",
        poll_interval=0,
    )

    assert client.list_calls == 1
    assert client.create_calls == 0
    assert result["runtime_id"] == "r-existing"


def test_duplicate_runtime_names_fail_instead_of_reusing_arbitrarily() -> None:
    """Ambiguous retries must not bind mpa_meta to an arbitrary Runtime."""
    client = _FakeRuntimeClient(ready_after=1)

    def _duplicates(_request):
        return SimpleNamespace(
            agent_kit_runtimes=[
                SimpleNamespace(name="mpa-agent-e2e", runtime_id="r-one"),
                SimpleNamespace(name="mpa-agent-e2e", runtime_id="r-two"),
            ],
            next_token=None,
        )

    client.list_runtimes = _duplicates
    with pytest.raises(MpaRuntimeError, match="multiple runtimes.*mpa-agent-e2e"):
        provision_runtime(
            client,
            **_params(),
            resolve_apig_instance_id=lambda ep: "gw-1",
            poll_interval=0,
        )
    assert client.create_calls == 0
